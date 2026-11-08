"""Account operations backed by the Atlas user store.

The stored password hash never leaves this module, and no handler reads the
users collection directly.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import HTTPException, status
from pymongo import ASCENDING
from pymongo.collection import Collection
from pymongo.errors import DuplicateKeyError, PyMongoError

from ..core import content, security, settings
from ..db import mongo
from ..schemas.auth import (
    AccessToken,
    LoginRequest,
    PasswordRequest,
    ProfileRequest,
    RegisterRequest,
    SessionUser,
)

NAME_FIELD = "name"
ROLE_FIELD = "role"
PASSWORD_FIELD = "password_hash"
CREATED_FIELD = "created_at"
UPDATED_FIELD = "updated_at"

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _accounts() -> Collection:
    """The users collection, with the unique email index applied once."""
    accounts = mongo.collection(settings.USERS_COLLECTION)
    accounts.create_index([(settings.EMAIL_FIELD, ASCENDING)], unique=True)
    return accounts


def _unavailable(error: BaseException | None = None) -> HTTPException:
    """503 with copy that does not describe the account store."""
    if error is not None:
        logger.warning("Sign-in store unreachable (%s)", type(error).__name__)
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=content.ERRORS["auth_store_unavailable"],
    )


def _store() -> Collection:
    """The users collection, or a 503 the client can act on."""
    try:
        return _accounts()
    except (mongo.NotConfigured, PyMongoError) as error:
        raise _unavailable(error) from error


def _session_user(document: dict[str, Any]) -> SessionUser:
    return SessionUser(
        id=str(document["_id"]),
        name=document.get(NAME_FIELD) or document[settings.EMAIL_FIELD],
        email=document[settings.EMAIL_FIELD],
        role=document.get(ROLE_FIELD) or settings.DEFAULT_USER_ROLE,
    )


def _find(user: SessionUser) -> dict[str, Any]:
    """Re-read the account a token refers to, for operations that must be current."""
    try:
        document = _store().find_one({"_id": ObjectId(user.id)})
    except InvalidId as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=content.ERRORS["session_expired"],
        ) from error
    except PyMongoError as error:
        raise _unavailable(error) from error
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=content.ERRORS["account_not_found"],
        )
    return document


def register(payload: RegisterRequest) -> AccessToken:
    document = {
        NAME_FIELD: payload.name.strip(),
        settings.EMAIL_FIELD: str(payload.email).lower(),
        PASSWORD_FIELD: security.hash_password(payload.password),
        ROLE_FIELD: settings.DEFAULT_USER_ROLE,
        CREATED_FIELD: datetime.now(timezone.utc),
    }
    try:
        result = _store().insert_one(document)
    except DuplicateKeyError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=content.ERRORS["email_taken"],
        ) from error
    return security.issue(_session_user({**document, "_id": result.inserted_id}))


def authenticate(payload: LoginRequest) -> AccessToken:
    try:
        document = _store().find_one({settings.EMAIL_FIELD: str(payload.email).lower()})
    except PyMongoError as error:
        raise _unavailable(error) from error
    # The same message for an unknown email and a wrong password, so the
    # response cannot be used to discover which accounts exist.
    if not document or not security.verify_password(
        payload.password, document[PASSWORD_FIELD]
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=content.ERRORS["bad_credentials"],
        )
    return security.issue(_session_user(document))


def update_profile(user: SessionUser, payload: ProfileRequest) -> AccessToken:
    """Change the display name and re-issue the token that carries it."""
    document = _find(user)
    name = payload.name.strip()
    if len(name) < settings.NAME_MIN_LENGTH:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=content.ERRORS["name_too_short"].format(minimum=settings.NAME_MIN_LENGTH),
        )
    _store().update_one(
        {"_id": document["_id"]},
        {"$set": {NAME_FIELD: name, UPDATED_FIELD: datetime.now(timezone.utc)}},
    )
    return security.issue(_session_user({**document, NAME_FIELD: name}))


def change_password(user: SessionUser, payload: PasswordRequest) -> AccessToken:
    """Replace the password after proving the current one is known."""
    document = _find(user)
    if not security.verify_password(payload.current_password, document[PASSWORD_FIELD]):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=content.ERRORS["wrong_password"],
        )
    if security.verify_password(payload.new_password, document[PASSWORD_FIELD]):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=content.ERRORS["password_unchanged"],
        )
    _store().update_one(
        {"_id": document["_id"]},
        {
            "$set": {
                PASSWORD_FIELD: security.hash_password(payload.new_password),
                UPDATED_FIELD: datetime.now(timezone.utc),
            }
        },
    )
    return security.issue(_session_user(document))
