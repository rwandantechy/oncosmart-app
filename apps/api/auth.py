"""Compatibility exports for the session dependency and account shapes.

New code should import from :mod:`apps.api.dependencies` and
:mod:`apps.api.schemas.auth`.
"""

from .dependencies import current_user
from .schemas.auth import LoginRequest, RegisterRequest, SessionUser
from .services.users import authenticate as login_user
from .services.users import register as register_user

__all__ = [
    "LoginRequest",
    "RegisterRequest",
    "SessionUser",
    "current_user",
    "login_user",
    "register_user",
]
