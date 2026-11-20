from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field, model_validator, field_validator
from .display_name import DEFAULT_NAME, check_display_name

class CreateRecording(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    source: Literal["synthetic", "desktop_manual"] = "synthetic"
    meeting_url: str | None = Field(default=None, max_length=1000)
    participant_name: str | None = Field(default=None, max_length=80)
    scheduled_at: datetime
    duration_minutes: int = Field(ge=1, le=480)
    permission_confirmed: bool = False
    disclosure_acknowledged: bool = False
    authorization_basis: Literal["host", "written_consent", "other"] | None = None
    authorization_reference: str | None = Field(default=None, max_length=500)

    @field_validator("participant_name")
    @classmethod
    def normalize_participant_name(cls, value: str | None) -> str | None:
        return check_display_name(value) if value is not None else None

    @model_validator(mode="after")
    def validate_schedule(self):
        if self.scheduled_at.tzinfo is None or self.scheduled_at.utcoffset() is None:
            raise ValueError("scheduled_at requires a timezone offset")
        if self.source != "synthetic":
            if self.participant_name is None:
                raise ValueError("For Zoom recordings a participant_name is required")
            if not self.meeting_url or not self.meeting_url.startswith("https://"):
                raise ValueError("desktop_manual requires an HTTPS Zoom meeting link")
            from urllib.parse import urlparse
            parsed = urlparse(self.meeting_url)
            import re
            if not (parsed.hostname == "zoom.us" or (parsed.hostname or "").endswith(".zoom.us")) or parsed.username or parsed.password or parsed.port:
                raise ValueError("The meeting link must belong to zoom.us")
            if not re.fullmatch(r"/(?:j|w)/[0-9]{9,13}/?", parsed.path):
                raise ValueError("A Zoom join link with a numeric meeting ID is required")
            if not (self.disclosure_acknowledged and self.permission_confirmed):
                raise ValueError("Both authorization and participant information must be confirmed")
            if self.authorization_basis not in {"host", "written_consent", "other"}:
                raise ValueError("Select the basis for recording authorization")
            if self.authorization_basis != "host" and not (self.authorization_reference or "").strip():
                raise ValueError("A reference to the written or other permission is required")
        return self


class UpdateParticipantName(BaseModel):
    participant_name: str = Field(min_length=1, max_length=80)

    @field_validator("participant_name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return check_display_name(value)
