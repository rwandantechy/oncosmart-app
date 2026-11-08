"""Request and response shapes for accounts and sessions.

Length limits come from configuration so the API, the sign-up form, and the
documentation cannot drift apart.
"""

from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field

from ..core import settings

Name = Field(min_length=settings.NAME_MIN_LENGTH, max_length=settings.NAME_MAX_LENGTH)
Password = Field(
    min_length=settings.PASSWORD_MIN_LENGTH, max_length=settings.PASSWORD_MAX_LENGTH
)


class RegisterRequest(BaseModel):
    name: str = Name
    email: EmailStr
    password: str = Password


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=settings.PASSWORD_MAX_LENGTH)


class ProfileRequest(BaseModel):
    """The only profile field a researcher may change themselves."""

    name: str = Name


class PasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=settings.PASSWORD_MAX_LENGTH)
    new_password: str = Password


class SessionUser(BaseModel):
    """The signed-in researcher, as carried by the access token."""

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    email: EmailStr
    role: str = Field(min_length=1)


class AccessToken(BaseModel):
    """What the client stores after signing in or changing credentials."""

    access_token: str
    token_type: str = settings.TOKEN_TYPE
    expires_at: str
    user: SessionUser
