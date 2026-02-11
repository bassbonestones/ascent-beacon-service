from datetime import datetime
from pydantic import BaseModel, EmailStr


class GoogleAuthRequest(BaseModel):
    id_token: str
    device_id: str | None = None
    device_name: str | None = None


class AppleAuthRequest(BaseModel):
    id_token: str
    device_id: str | None = None
    device_name: str | None = None


class EmailAuthRequest(BaseModel):
    email: EmailStr


class EmailVerifyRequest(BaseModel):
    token: str
    email: EmailStr | None = None
    device_id: str | None = None
    device_name: str | None = None


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str


class UserResponse(BaseModel):
    id: str
    display_name: str | None
    primary_email: str | None
    is_email_verified: bool
    created_at: datetime
    
    model_config = {"from_attributes": True}


class AuthResponse(BaseModel):
    access_token: str
    refresh_token: str
    user: UserResponse


class RefreshResponse(BaseModel):
    access_token: str
    refresh_token: str


class SetDisplayNameRequest(BaseModel):
    display_name: str


class UpdatePrimaryEmailRequest(BaseModel):
    primary_email: EmailStr
    force_verification: bool = False  # If True, always require verification


class OnboardingStatusResponse(BaseModel):
    user: UserResponse
    needs_display_name: bool
    needs_email_verification: bool

