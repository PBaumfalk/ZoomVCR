from functools import lru_cache
import re
from pathlib import Path
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ZOOMVCR_", extra="ignore")
    database_url: str = "sqlite:////tmp/zoomvcr-local.db"
    redis_url: str = "redis://localhost:6379/0"
    storage_root: Path = Path("/tmp/zoomvcr-recordings")
    admin_password: str = ""
    bootstrap_admin_username: str = "admin"
    oidc_discovery_url: str = ""
    oidc_client_id: str = ""
    oidc_client_secret: str = ""
    secret_key: str = ""
    api_token: str = ""
    public_origin: str = "http://localhost:8000"
    timezone: str = "Europe/Berlin"
    asr_enabled: bool = False
    # Default transcription provider until set in the UI: openai | local | off
    asr_provider: str = "openai"
    asr_model: str = "small"
    ocr_lang: str = "deu+eng"
    ai_url: str = ""
    ai_model: str = ""
    ai_api_key: str = ""
    enable_desktop: bool = False
    desktop_agent_url: str = "http://desktop:8765"
    join_timeout_seconds: int = 180
    join_grace_seconds: int = 12
    assume_joined_after_seconds: int = 0
    # false = do not block the recording when the Zoom display name cannot be verified by OCR;
    # the status is recorded as "unverified_accepted" instead (operator decision).
    require_name_confirmation: bool = True
    # Zoom recordings join this many minutes before the planned start (waiting time is recorded;
    # silent parts are skipped by the transcription).
    join_lead_minutes: int = 5
    # Zoom recordings run this many minutes past the entered duration (lectures overrun).
    end_buffer_minutes: int = 15
    record_segment_seconds: int = 60
    # Mail alerts. SMTP_URL/MAIL_FROM without prefix are accepted too (shared .env of several services).
    smtp_url: str = Field(default="", validation_alias=AliasChoices("ZOOMVCR_SMTP_URL", "SMTP_URL"))
    mail_from: str = Field(default="", validation_alias=AliasChoices("ZOOMVCR_MAIL_FROM", "MAIL_FROM"))
    alert_email: str = ""
    # Alert when Zoom has had no computer audio for this long during a recording.
    audio_alert_seconds: int = 120
    # Automatic cut of silent start, end and pauses (silence = below cut_silence_db).
    cut_enabled: bool = True
    cut_silence_db: float = -50.0
    cut_edge_seconds: float = 20.0
    cut_pause_seconds: float = 120.0
    cut_pad_seconds: float = 3.0
    synthetic_realtime: bool = True

@lru_cache
def settings() -> Settings:
    return Settings()


_LOCAL_HTTP = re.compile(r"http://(localhost|127\.0\.0\.1)(:\d{1,5})?")


def normalize_origin(value: str) -> str:
    """Origin as a browser sends it: no trailing slash, no default port (:80 for http, :443 for https)."""
    origin = (value or "").strip().rstrip("/")
    if origin.startswith("http://") and origin.endswith(":80"):
        origin = origin[:-3]
    elif origin.startswith("https://") and origin.endswith(":443"):
        origin = origin[:-4]
    return origin


def origin_allowed(value: str) -> bool:
    """HTTPS everywhere; plain HTTP only on this machine (localhost/127.0.0.1, with or without port)."""
    origin = normalize_origin(value)
    return (origin.startswith("https://") and len(origin) > len("https://")) or bool(_LOCAL_HTTP.fullmatch(origin))
