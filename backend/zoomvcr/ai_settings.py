"""AI provider settings (transcription + summary), editable by administrators in the web UI.

The API key is stored sealed in the database (Fernet key derived from ZOOMVCR_SECRET_KEY) and is
never returned by the API — only whether a key is set and its last four characters. Environment
variables (ZOOMVCR_AI_URL, ZOOMVCR_AI_API_KEY, ZOOMVCR_AI_MODEL, ZOOMVCR_ASR_PROVIDER) remain a
fallback for installations without UI configuration.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timezone
from typing import Literal
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from . import db as dbmod
from .config import settings
from .db import db_session
from .models import AppSetting
from .security import Principal, log_event, require_role, seal_secret, unseal_secret

DEFAULT_BASE_URL = "https://api.openai.com/v1"
DEFAULT_TRANSCRIPTION_MODEL = "gpt-4o-transcribe"  # whisper-1 hallucinates on leading silence (test 07.11.2026)
DEFAULT_SUMMARY_MODEL = "gpt-5-mini"
TranscriptionProvider = Literal["openai", "local", "off"]

_KEYS = ("ai.base_url", "ai.api_key", "ai.transcription_provider", "ai.transcription_model",
         "ai.summary_enabled", "ai.summary_model")


@dataclass(frozen=True)
class AIConfig:
    base_url: str
    api_key: str
    transcription_provider: str
    transcription_model: str
    summary_enabled: bool
    summary_model: str
    key_source: str  # "ui", "env" or "none"

    @property
    def has_key(self) -> bool:
        return bool(self.api_key)


def validate_base_url(value: str) -> str:
    value = value.strip().rstrip("/")
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password \
            or parsed.query or parsed.fragment:
        raise ValueError("Base URL must be a plain https:// URL without credentials, query or fragment")
    return value


def _rows(db: Session) -> dict[str, AppSetting]:
    return {row.key: row for row in db.query(AppSetting).filter(AppSetting.key.in_(_KEYS)).all()}


def resolve(db: Session) -> AIConfig:
    env = settings()
    rows = _rows(db)
    value = lambda key: rows[key].value if key in rows else None  # noqa: E731
    api_key, source = "", "none"
    if value("ai.api_key"):
        try:
            api_key, source = unseal_secret(value("ai.api_key")), "ui"
        except Exception:
            # Secret key changed or value damaged: behave as if no key were stored.
            api_key, source = "", "none"
    elif env.ai_api_key:
        api_key, source = env.ai_api_key, "env"
    base = value("ai.base_url") or env.ai_url or DEFAULT_BASE_URL
    provider = value("ai.transcription_provider") or env.asr_provider
    if provider not in ("openai", "local", "off"):
        provider = "openai"
    summary_enabled = (value("ai.summary_enabled") or "true") == "true"
    return AIConfig(base_url=base.rstrip("/"), api_key=api_key, transcription_provider=provider,
                    transcription_model=value("ai.transcription_model") or DEFAULT_TRANSCRIPTION_MODEL,
                    summary_enabled=summary_enabled,
                    summary_model=value("ai.summary_model") or env.ai_model or DEFAULT_SUMMARY_MODEL,
                    key_source=source)


def load_ai_config() -> AIConfig:
    """For worker jobs outside a request: opens its own DB session."""
    with dbmod.SessionLocal() as db:
        return resolve(db)


def public_view(cfg: AIConfig, rows: dict[str, AppSetting] | None = None) -> dict:
    updated = None
    if rows:
        stamp = lambda r: r.updated_at if r.updated_at.tzinfo else r.updated_at.replace(tzinfo=timezone.utc)  # noqa: E731
        latest = max(rows.values(), key=stamp)
        updated = {"at": stamp(latest).isoformat(), "by": latest.updated_by}
    return {"base_url": cfg.base_url, "api_key_set": cfg.has_key,
            "api_key_hint": ("…" + cfg.api_key[-4:]) if len(cfg.api_key) >= 12 else ("gesetzt" if cfg.api_key else ""),
            "api_key_source": cfg.key_source,
            "transcription_provider": cfg.transcription_provider,
            "transcription_model": cfg.transcription_model,
            "summary_enabled": cfg.summary_enabled, "summary_model": cfg.summary_model,
            "local_asr_available": _local_asr_available(), "updated": updated}


def _local_asr_available() -> bool:
    try:
        import importlib.util
        return importlib.util.find_spec("faster_whisper") is not None
    except Exception:
        return False


class AISettingsUpdate(BaseModel):
    base_url: str | None = Field(default=None, max_length=300)
    api_key: str | None = Field(default=None, max_length=400)
    clear_api_key: bool = False
    transcription_provider: TranscriptionProvider | None = None
    transcription_model: str | None = Field(default=None, min_length=1, max_length=100)
    summary_enabled: bool | None = None
    summary_model: str | None = Field(default=None, min_length=1, max_length=100)

    @field_validator("base_url")
    @classmethod
    def check_base(cls, v):
        return None if v is None else validate_base_url(v)

    @field_validator("api_key")
    @classmethod
    def check_key(cls, v):
        if v is None or not v.strip():
            return None
        v = v.strip()
        if len(v) < 20 or any(ch.isspace() for ch in v) or not v.isascii():
            raise ValueError("API key looks invalid")
        return v

    @field_validator("transcription_model", "summary_model")
    @classmethod
    def check_model(cls, v):
        if v is None:
            return None
        v = v.strip()
        if not all(ch.isascii() and (ch.isalnum() or ch in "._-:/") for ch in v):
            raise ValueError("Model name contains invalid characters")
        return v


router = APIRouter(prefix="/api/settings/ai")


def _put(db: Session, rows: dict, key: str, value: str, actor: Principal) -> None:
    row = rows.get(key)
    if row is None:
        row = AppSetting(key=key, value=value, updated_by=actor.username)
        db.add(row)
        rows[key] = row
    else:
        row.value = value
        row.updated_by = actor.username


@router.get("")
def get_ai_settings(db: Session = Depends(db_session), actor: Principal = Depends(require_role("admin"))):
    return public_view(resolve(db), _rows(db))


@router.put("")
def update_ai_settings(data: AISettingsUpdate, request: Request, db: Session = Depends(db_session),
                       actor: Principal = Depends(require_role("admin"))):
    rows = _rows(db)
    before = resolve(db)
    changed: list[str] = []
    if data.base_url is not None and data.base_url != before.base_url:
        _put(db, rows, "ai.base_url", data.base_url, actor)
        changed.append("base_url")
        # A stored key must never silently follow a new endpoint: re-entry is required.
        if data.api_key is None and "ai.api_key" in rows and rows["ai.api_key"].value:
            _put(db, rows, "ai.api_key", "", actor)
            changed.append("api_key_cleared_by_endpoint_change")
    if data.clear_api_key:
        _put(db, rows, "ai.api_key", "", actor)
        changed.append("api_key_cleared")
    elif data.api_key is not None:
        _put(db, rows, "ai.api_key", seal_secret(data.api_key), actor)
        changed.append("api_key")
    for field, key in (("transcription_provider", "ai.transcription_provider"),
                       ("transcription_model", "ai.transcription_model"),
                       ("summary_model", "ai.summary_model")):
        val = getattr(data, field)
        if val is not None:
            _put(db, rows, key, val, actor)
            changed.append(field)
    if data.summary_enabled is not None:
        _put(db, rows, "ai.summary_enabled", "true" if data.summary_enabled else "false", actor)
        changed.append("summary_enabled")
    db.flush()
    log_event(db, actor, "settings.ai_update", "settings", "ai", request, {"changed": changed})
    db.commit()
    return public_view(resolve(db), _rows(db))


@router.post("/test")
def test_ai_settings(db: Session = Depends(db_session), actor: Principal = Depends(require_role("admin"))):
    cfg = resolve(db)
    if not cfg.has_key:
        raise HTTPException(409, "Kein API-Key hinterlegt")
    from .openai_api import list_models, ProviderError
    try:
        models = list_models(cfg)
    except ProviderError as exc:
        return {"ok": False, "detail": str(exc)}
    result = {"ok": True, "detail": f"Verbindung erfolgreich, {len(models)} Modelle verfügbar"}
    if models:
        result["transcription_model_available"] = cfg.transcription_model in models
        result["summary_model_available"] = cfg.summary_model in models
    return result
