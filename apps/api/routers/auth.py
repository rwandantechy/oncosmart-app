"""Account and session routes. Register and login are public; the rest are not."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from ..core import content, settings
from ..dependencies import current_user
from ..schemas.auth import (
    AccessToken,
    LoginRequest,
    PasswordRequest,
    ProfileRequest,
    RegisterRequest,
    SessionUser,
)
from ..services import users

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register")
def register(payload: RegisterRequest) -> AccessToken:
    if not settings.signup_open():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=content.ERRORS["signup_closed"],
        )
    return users.register(payload)


@router.post("/login")
def login(payload: LoginRequest) -> AccessToken:
    return users.authenticate(payload)


@router.get("/me")
def session(user: Annotated[SessionUser, Depends(current_user)]) -> SessionUser:
    return user


@router.patch("/me")
def update_profile(
    payload: ProfileRequest,
    user: Annotated[SessionUser, Depends(current_user)],
) -> AccessToken:
    return users.update_profile(user, payload)


@router.post("/password")
def change_password(
    payload: PasswordRequest,
    user: Annotated[SessionUser, Depends(current_user)],
) -> AccessToken:
    return users.change_password(user, payload)
