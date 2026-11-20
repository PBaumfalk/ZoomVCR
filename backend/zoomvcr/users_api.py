"""Local user management, audit log and optional TOTP for ZoomVCR."""
from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from redis import Redis
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .config import settings, normalize_origin
from .db import db_session
from .models import AuditEvent, User
from .security import (COOKIE, Principal, ROLES, create_session, generate_totp_secret,
                       hash_password, log_event, require_auth, require_role,
                       revoke_session, seal_secret, unseal_secret, user_public,
                       verify_password, verify_totp)
from .user_schemas import (LoginRequest, PasswordChange, PasswordReset,
                           TotpDisable, TotpVerify, UserCreate, UserUpdate)

router = APIRouter(prefix="/api")


def _cookie(response: Response, token: str) -> None:
    response.set_cookie(COOKIE, token, httponly=True,
                        secure=settings().public_origin.startswith("https://"),
                        samesite="strict", max_age=8 * 3600, path="/")


def _login_rate_limit(redis: Redis, request: Request, username: str) -> tuple[str, str]:
    from hashlib import sha256
    client = request.client.host if request.client else "unknown"
    key = "zoomvcr:login-fail:" + sha256((client + ":" + username).encode()).hexdigest()
    ip_key = "zoomvcr:login-ip:" + sha256(client.encode()).hexdigest()
    try:
        if int(redis.get(key) or 0) >= 10 or int(redis.get(ip_key) or 0) >= 25:
            raise HTTPException(429, "Too many attempts. Try again later")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(503, "Login rate limiter unavailable") from exc
    return key, ip_key


@router.post("/login")
def login(data: LoginRequest, request: Request, response: Response, db: Session = Depends(db_session)):
    origin = request.headers.get("origin")
    if origin and origin != normalize_origin(settings().public_origin):
        raise HTTPException(403, "Invalid request origin")
    try:
        redis = Redis.from_url(settings().redis_url, socket_connect_timeout=2)
        key, ip_key = _login_rate_limit(redis, request, data.username.lower())
    except HTTPException:
        raise
    user = db.scalar(select(User).where(User.username == data.username.strip().lower()))
    ok = bool(user and user.provider == "local" and user.active and verify_password(data.password, user.password_hash))
    if ok and user.mfa_secret:
        try:
            step = verify_totp(unseal_secret(user.mfa_secret), data.totp, user.mfa_last_step)
        except Exception:
            step = None
        if step is None:
            ok = False
        else:
            user.mfa_last_step = step
    if not ok:
        try:
            redis.incr(key)
            redis.expire(key, 900)
            redis.incr(ip_key)
            redis.expire(ip_key, 900)
        except Exception as exc:
            raise HTTPException(503, "Login rate limiter unavailable") from exc
        raise HTTPException(401, "Invalid credentials or verification code")
    redis.delete(key)
    redis.delete(ip_key)
    user.last_login_at = datetime.now(timezone.utc)
    token = create_session(db, user)
    principal = Principal(user.id, user.username, user.role, "web")
    log_event(db, principal, "auth.login", "user", user.id, request)
    db.commit()
    _cookie(response, token)
    return {"authenticated": True, "user": user_public(user)}


@router.post("/logout")
def logout(response: Response, request: Request, db: Session = Depends(db_session),
           actor: Principal = Depends(require_auth)):
    revoke_session(db, actor)
    log_event(db, actor, "auth.logout", "user", actor.id or "", request)
    db.commit()
    response.delete_cookie(COOKIE, path="/")
    return {"authenticated": False}


@router.get("/me")
def me(actor: Principal = Depends(require_auth), db: Session = Depends(db_session)):
    if actor.mode == "cli":
        return {"authenticated": True, "user": {"id": None, "username": actor.username,
                "role": "admin", "provider": "token", "active": True, "mfa_enabled": False}}
    return {"authenticated": True, "user": user_public(db.get(User, actor.id))}


@router.get("/auth/config")
def auth_config():
    config = settings()
    return {"oidc_enabled": bool(config.oidc_discovery_url and config.oidc_client_id and config.oidc_client_secret)}


@router.get("/users")
def users(db: Session = Depends(db_session), actor: Principal = Depends(require_role("admin"))):
    return [user_public(u) for u in db.scalars(select(User).order_by(User.username))]


@router.post("/users", status_code=201)
def create_user(data: UserCreate, request: Request, db: Session = Depends(db_session),
                actor: Principal = Depends(require_role("admin"))):
    obj = User(username=data.username, email=data.email, role=data.role,
               provider=data.provider, active=True,
               password_hash=hash_password(data.password) if data.provider == "local" else None)
    db.add(obj)
    try:
        db.flush()
        log_event(db, actor, "user.create", "user", obj.id, request,
                  {"role": obj.role, "provider": obj.provider})
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Username or email is already registered") from exc
    return user_public(obj)


def _another_admin(db: Session, user_id: str) -> bool:
    return bool(db.scalar(select(func.count()).select_from(User).where(
        User.role == "admin", User.active.is_(True), User.id != user_id)))


@router.patch("/users/{user_id}")
def edit_user(user_id: str, data: UserUpdate, request: Request,
              db: Session = Depends(db_session), actor: Principal = Depends(require_role("admin"))):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "User not found")
    role = data.role if data.role is not None else user.role
    active = data.active if data.active is not None else user.active
    if user.active and user.role == "admin" and (role != "admin" or not active):
        if not _another_admin(db, user.id):
            raise HTTPException(409, "The last active administrator cannot be disabled or demoted")
    if user.id == actor.id and (role != "admin" or not active):
        raise HTTPException(409, "You cannot disable or demote your own account")
    old = {"role": user.role, "active": user.active}
    user.role, user.active = role, active
    if old != {"role": role, "active": active}:
        user.session_version += 1  # Revoke all existing sessions immediately.
        log_event(db, actor, "user.update", "user", user.id, request,
                  {"before": old, "after": {"role": role, "active": active}})
    db.commit()
    return user_public(user)


@router.post("/users/{user_id}/reset-password")
def admin_reset_password(user_id: str, data: PasswordReset, request: Request,
                         db: Session = Depends(db_session), actor: Principal = Depends(require_role("admin"))):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404)
    if user.provider != "local":
        raise HTTPException(409, "OIDC passwords are managed in the identity provider")
    user.password_hash = hash_password(data.new_password)
    user.session_version += 1
    user.mfa_secret, user.mfa_pending, user.mfa_last_step = None, None, -1
    log_event(db, actor, "user.password_reset", "user", user.id, request)
    db.commit()
    return {"ok": True, "sessions_revoked": True, "mfa_reset": True}


@router.post("/me/change-password")
def change_password(data: PasswordChange, request: Request, response: Response,
                    db: Session = Depends(db_session), actor: Principal = Depends(require_auth)):
    if not actor.id:
        raise HTTPException(403)
    user = db.get(User, actor.id)
    if user.provider != "local":
        raise HTTPException(409, "Password is managed through SSO")
    if not verify_password(data.current_password, user.password_hash):
        raise HTTPException(401, "Incorrect current password")
    user.password_hash = hash_password(data.new_password)
    user.session_version += 1
    log_event(db, actor, "user.password_change", "user", actor.id, request)
    db.commit()
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True, "relogin_required": True}


@router.post("/me/mfa/setup")
def totp_setup(request: Request, db: Session = Depends(db_session),
               actor: Principal = Depends(require_auth)):
    if not actor.id:
        raise HTTPException(403)
    user = db.get(User, actor.id)
    if user.provider != "local":
        raise HTTPException(409, "Configure MFA at your OIDC provider for SSO accounts")
    if user.mfa_secret:
        raise HTTPException(409, "MFA is already enabled")
    secret = generate_totp_secret()
    user.mfa_pending = seal_secret(secret)
    log_event(db, actor, "mfa.setup_requested", "user", user.id, request)
    db.commit()
    label = quote("ZoomVCR:" + user.username, safe="")
    uri = f"otpauth://totp/{label}?secret={secret}&issuer=ZoomVCR&algorithm=SHA1&digits=6&period=30"
    return {"secret": secret, "otpauth_uri": uri,
            "notice": "Add to an authenticator and verify a six-digit code; this secret is shown only now"}


@router.post("/me/mfa/verify")
def totp_activate(data: TotpVerify, request: Request, db: Session = Depends(db_session),
                  actor: Principal = Depends(require_auth)):
    if not actor.id:
        raise HTTPException(403)
    user = db.get(User, actor.id)
    if not user.mfa_pending or user.mfa_secret:
        raise HTTPException(409, "No MFA setup is pending")
    step = verify_totp(unseal_secret(user.mfa_pending), data.code)
    if step is None:
        raise HTTPException(400, "Invalid verification code")
    user.mfa_secret, user.mfa_pending, user.mfa_last_step = user.mfa_pending, None, step
    # All prior sessions were authenticated without the newly enabled factor.
    user.session_version += 1
    log_event(db, actor, "mfa.enabled", "user", user.id, request)
    db.commit()
    return {"enabled": True, "relogin_required": True}


@router.post("/me/mfa/disable")
def totp_disable(data: TotpDisable, request: Request, db: Session = Depends(db_session),
                 actor: Principal = Depends(require_auth)):
    if not actor.id:
        raise HTTPException(403)
    user = db.get(User, actor.id)
    if not user.mfa_secret or not verify_password(data.current_password, user.password_hash):
        raise HTTPException(401, "Incorrect credentials")
    step = verify_totp(unseal_secret(user.mfa_secret), data.code, user.mfa_last_step)
    if step is None:
        raise HTTPException(401, "Incorrect verification code")
    user.mfa_secret, user.mfa_pending, user.mfa_last_step = None, None, -1
    user.session_version += 1
    log_event(db, actor, "mfa.disabled", "user", user.id, request)
    db.commit()
    return {"enabled": False, "relogin_required": True}


@router.get("/audit")
def audit(offset: int = 0, limit: int = 100, db: Session = Depends(db_session),
          actor: Principal = Depends(require_role("admin"))):
    if not (0 <= offset <= 100000 and 1 <= limit <= 200):
        raise HTTPException(422, "Invalid pagination")
    rows = db.scalars(select(AuditEvent).order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
                      .offset(offset).limit(limit)).all()
    return [{"id": e.id, "created_at": e.created_at.isoformat(), "actor": e.actor_username,
             "action": e.action, "target_type": e.target_type, "target_id": e.target_id,
             "ip_address": e.ip_address, "details": e.details or {}} for e in rows]
