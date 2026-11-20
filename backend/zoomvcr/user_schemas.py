from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Literal
from .security import normalize_username, validate_password

Role = Literal["admin", "recorder", "viewer"]
Provider = Literal["local", "oidc"]

class LoginRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str
    totp: str = ""

class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    email: str | None = Field(default=None, max_length=254)
    role: Role = "viewer"
    provider: Provider = "local"
    password: str | None = None

    @field_validator("username")
    @classmethod
    def clean_username(cls, v): return normalize_username(v)

    @field_validator("email")
    @classmethod
    def clean_email(cls, v):
        if v is None or not v.strip(): return None
        v = v.strip().lower()
        if v.count('@') != 1 or ' ' in v or len(v) > 254 or '.' not in v.split('@')[-1]:
            raise ValueError('Valid email address required')
        return v

    @model_validator(mode="after")
    def check_provider(self):
        if self.provider == "local":
            validate_password(self.password or "")
        elif not self.email:
            raise ValueError("Email required to pre-provision an OIDC account")
        return self

class UserUpdate(BaseModel):
    role: Role | None = None
    active: bool | None = None

class PasswordReset(BaseModel):
    new_password: str
    @field_validator("new_password")
    @classmethod
    def length(cls, v): validate_password(v); return v

class PasswordChange(PasswordReset):
    current_password: str

class TotpVerify(BaseModel):
    code: str = Field(min_length=6, max_length=6)

class TotpDisable(TotpVerify):
    current_password: str
