"""Password hashing and access-token issuing.

Deliberately free of FastAPI: HTTP status codes and headers are applied in
:mod:`apps.api.dependencies`, so these functions can also be used from a
command-line task without pulling in the web layer.

Tokens are verified statelessly. The signed claims are trusted for the lifetime
of the token rather than re-read from Atlas on every request, which keeps the
snapshot serving while the user store is unreachable. The trade-off is that an
account removed from Atlas keeps access until its token expires, so the
lifetime is kept short through ``V2_TOKEN_TTL_HOURS``.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import jwt
from pwdlib import PasswordHash
from pydantic import ValidationError

from ..db import mongo
from ..schemas.auth import AccessToken, SessionUser
from . import settings

_PASSWORD_HASH = PasswordHash.recommended()


class NotConfigured(RuntimeError):
    """Atlas or the signing secret is missing, so no session can be trusted."""


class InvalidToken(RuntimeError):
    """The presented token was absent, expired, forged, or incomplete."""


def signing_secret() -> str:
    """The HMAC secret, present only when the user store is configured too."""
    secret = os.getenv("V2_AUTH_SECRET")
    if not mongo.uri() or not secret:
        raise NotConfigured("MONGODB_URI and V2_AUTH_SECRET must both be set")
    return secret


def hash_password(raw: str) -> str:
    return _PASSWORD_HASH.hash(raw)


def verify_password(raw: str, hashed: str) -> bool:
    return _PASSWORD_HASH.verify(raw, hashed)


def issue(user: SessionUser) -> AccessToken:
    """Mint a token for ``user`` and return it with the identity it carries."""
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(hours=settings.TOKEN_TTL_HOURS)
    token = jwt.encode(
        {
            "sub": user.id,
            "email": str(user.email),
            "name": user.name,
            "role": user.role,
            "iat": now,
            "exp": expires_at,
        },
        signing_secret(),
        algorithm=settings.JWT_ALGORITHM,
    )
    return AccessToken(
        access_token=token,
        expires_at=expires_at.isoformat(),
        user=user,
    )


def read(token: str) -> SessionUser:
    """Verify a token and return who it belongs to."""
    try:
        claims = jwt.decode(
            token,
            signing_secret(),
            algorithms=[settings.JWT_ALGORITHM],
            options={"require": ["exp", "sub"]},
        )
        return SessionUser(
            id=claims.get("sub", ""),
            name=claims.get("name", ""),
            email=claims.get("email", ""),
            role=claims.get("role", settings.DEFAULT_USER_ROLE),
        )
    except (jwt.PyJWTError, ValidationError) as error:
        raise InvalidToken(str(error)) from error
