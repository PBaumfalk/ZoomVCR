"""Database backed authentication, RBAC, revocable sessions and local TOTP MFA."""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from cryptography.fernet import Fernet
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings, normalize_origin
from .db import db_session
from .models import AuditEvent, LoginSession, User

COOKIE = "zoomvcr_session"
ROLES = {"viewer": 1, "recorder": 2, "admin": 3}
_hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)


@dataclass(frozen=True)
class Principal:
    id: str | None
    username: str
    role: str
    mode: str
    session_id: str | None = None


def normalize_username(value: str) -> str:
    value = value.strip().lower()
    if not (3 <= len(value) <= 64) or not all(ch.isascii() and (ch.isalnum() or ch in "._-") for ch in value):
        raise ValueError("Username must be 3–64 ASCII letters, digits, dots, underscores or hyphens")
    return value


def validate_password(value: str) -> None:
    if not (14 <= len(value) <= 256):
        raise ValueError("Password must contain 14–256 characters")


def hash_password(password: str) -> str:
    validate_password(password)
    return _hasher.hash(password)


def verify_password(password: str, encoded: str | None) -> bool:
    if not encoded:
        return False
    try:
        return bool(_hasher.verify(encoded, password))
    except (VerificationError, InvalidHashError, ValueError):
        return False


def _fernet() -> Fernet:
    digest = hashlib.sha256(settings().secret_key.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def seal_secret(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def unseal_secret(value: str) -> str:
    return _fernet().decrypt(value.encode()).decode()


def generate_totp_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def totp_code(secret: str, step: int) -> str:
    pad = "=" * (-len(secret) % 8)
    key = base64.b32decode(secret + pad, casefold=True)
    digest = hmac.new(key, struct.pack(">Q", step), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    number = struct.unpack(">I", digest[offset:offset+4])[0] & 0x7FFFFFFF
    return f"{number % 1000000:06d}"


def verify_totp(secret: str, code: str, last_step: int = -1, at: int | None = None) -> int | None:
    if not (len(code) == 6 and code.isascii() and code.isdigit()):
        return None
    step = int((at if at is not None else time.time()) // 30)
    for candidate in (step-1, step, step+1):
        if candidate > last_step and hmac.compare_digest(totp_code(secret, candidate), code):
            return candidate
    return None


def log_event(db: Session, actor: Principal | None, action: str,
              target_type: str = "", target_id: str = "", request: Request | None = None,
              details: dict | None = None) -> None:
    # Older in-process test/CLI integrations may supply a plain actor label.
    # This only affects the log label, never authorization (which uses Principal).
    actor_id = getattr(actor, "id", None)
    actor_name = getattr(actor, "username", None) or (actor if isinstance(actor, str) else "anonymous")
    db.add(AuditEvent(actor_id=actor_id,
                      actor_username=actor_name,
                      action=action, target_type=target_type, target_id=target_id,
                      ip_address=(request.client.host[:64] if request and request.client else None),
                      details=details or {}))


def bootstrap_admin(db: Session) -> None:
    # Run only at first installation. Existing accounts are never reset by environment variables.
    if db.scalar(select(User.id).limit(1)) is not None:
        return
    config = settings()
    if not config.admin_password or config.admin_password == "CHANGE_TO_A_LONG_UNIQUE_PASSWORD":
        raise RuntimeError("First start requires a unique ZOOMVCR_ADMIN_PASSWORD, not the example placeholder")
    admin = User(username=normalize_username(config.bootstrap_admin_username),
                 email=None, role="admin", provider="local", active=True,
                 password_hash=hash_password(config.admin_password))
    db.add(admin)
    db.flush()
    log_event(db, None, "admin.bootstrap", "user", admin.id)
    db.commit()


def create_session(db: Session, user: User) -> str:
    config = settings()
    if len(config.secret_key) < 32:
        raise RuntimeError("ZOOMVCR_SECRET_KEY must contain at least 32 characters")
    now = datetime.now(timezone.utc)
    expires = now + timedelta(hours=8)
    sid = str(uuid.uuid4())
    db.add(LoginSession(id=sid, user_id=user.id, expires_at=expires))
    return jwt.encode({"iss": "zoomvcr", "aud": "zoomvcr-web", "sub": user.id,
                       "sid": sid, "ver": user.session_version,
                       "iat": now, "exp": expires}, config.secret_key, algorithm="HS256")


def _valid_session(token: str, db: Session) -> Principal | None:
    try:
        claims = jwt.decode(token, settings().secret_key, algorithms=["HS256"],
                            issuer="zoomvcr", audience="zoomvcr-web", options={"require": ["exp", "sub", "sid", "ver"]})
        user = db.get(User, claims["sub"])
        if not user or not user.active or user.session_version != claims["ver"]:
            return None
        session = db.get(LoginSession, claims["sid"])
        if not session or session.user_id != user.id or session.revoked_at is not None:
            return None
        end = session.expires_at
        if end.replace(tzinfo=timezone.utc) <= datetime.now(timezone.utc):
            return None
        return Principal(user.id, user.username, user.role, "web", session.id)
    except (jwt.PyJWTError, KeyError, TypeError, ValueError):
        return None


def require_auth(request: Request, db: Session = Depends(db_session)) -> Principal:
    config = settings()
    supplied = request.headers.get("authorization", "")
    if supplied.startswith("Bearer ") and len(config.api_token) >= 24:
        if hmac.compare_digest(supplied.removeprefix("Bearer "), config.api_token):
            # Privileged legacy CLI credential: never exposed to the browser.
            return Principal(None, "system-cli", "admin", "cli")
    cookie = request.cookies.get(COOKIE)
    actor = _valid_session(cookie, db) if cookie else None
    if actor:
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            if request.headers.get("origin") != normalize_origin(config.public_origin):
                raise HTTPException(status_code=403, detail="Invalid request origin")
        return actor
    raise HTTPException(status_code=401, detail="Login required")


def require_role(role: str):
    if role not in ROLES:
        raise ValueError(role)
    def guard(actor: Principal = Depends(require_auth)) -> Principal:
        if ROLES[actor.role] < ROLES[role]:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return actor
    return guard


def revoke_session(db: Session, actor: Principal) -> None:
    if actor.session_id:
        current = db.get(LoginSession, actor.session_id)
        if current:
            current.revoked_at = datetime.now(timezone.utc)


def user_public(user: User) -> dict:
    return {"id": user.id, "username": user.username, "email": user.email,
            "role": user.role, "provider": user.provider, "active": user.active,
            "mfa_enabled": bool(user.mfa_secret), "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
            "created_at": user.created_at.isoformat() if user.created_at else None}
