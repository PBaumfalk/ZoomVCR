"""Optional OpenID Connect login (e.g. authentik, Keycloak), authorization-code/PKCE, no implicit account creation."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .db import db_session
from .models import User
from .security import Principal, create_session, log_event
from .users_api import _cookie

router = APIRouter(prefix="/api/auth/oidc")


def _provider():
    config = settings()
    url = config.oidc_discovery_url
    if not (url.startswith("https://") and config.oidc_client_id and config.oidc_client_secret):
        raise HTTPException(503, "OIDC is not configured with an HTTPS discovery URL")
    # Lazy import: the base recorder can run without an identity provider.
    from authlib.integrations.starlette_client import OAuth
    oauth = OAuth()
    oauth.register("oidc", client_id=config.oidc_client_id,
                   client_secret=config.oidc_client_secret, server_metadata_url=url,
                   client_kwargs={"scope": "openid profile email", "code_challenge_method": "S256"})
    return oauth.oidc


@router.get("/start")
async def start(request: Request):
    provider = _provider()
    callback = settings().public_origin.rstrip("/") + "/api/auth/oidc/callback"
    return await provider.authorize_redirect(request, callback)


@router.get("/callback")
async def callback(request: Request, db: Session = Depends(db_session)):
    provider = _provider()
    try:
        token = await provider.authorize_access_token(request)
        identity = token.get("userinfo") or {}
        subject = identity.get("sub")
        email = str(identity.get("email") or "").strip().lower()
        email_verified = identity.get("email_verified") is True
        if not subject or not email_verified or not email:
            raise ValueError("Verified email address required")
    except Exception as exc:
        # Never expose sensitive ID tokens, authorization codes or provider responses.
        raise HTTPException(401, "SSO authentication failed") from exc
    user = db.scalar(select(User).where(User.provider == "oidc", User.oidc_subject == subject))
    if not user:
        user = db.scalar(select(User).where(User.provider == "oidc", User.email == email,
                                           User.oidc_subject.is_(None)))
        if not user:
            raise HTTPException(403, "SSO account not pre-approved by an administrator")
        user.oidc_subject = subject
    if not user.active or user.email != email:
        raise HTTPException(403, "SSO account is disabled or email does not match")
    user.last_login_at = datetime.now(timezone.utc)
    encoded = create_session(db, user)
    actor = Principal(user.id, user.username, user.role, "web")
    log_event(db, actor, "auth.oidc_login", "user", user.id, request)
    db.commit()
    response = RedirectResponse(url="/", status_code=303)
    _cookie(response, encoded)
    return response
