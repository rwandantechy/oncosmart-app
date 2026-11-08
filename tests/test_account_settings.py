"""Account settings stay behind a session and return a rotated token."""

from datetime import datetime, timezone

from apps.api.core import settings
from apps.api.schemas.auth import AccessToken, SessionUser
from apps.api.services import users
from tests.accounts import ACCOUNT

NEW_NAME = "Updated Researcher"
NEW_PASSWORD = "replacement-password"


def _token(user: SessionUser, access_token: str) -> AccessToken:
    return AccessToken(
        access_token=access_token,
        expires_at=datetime.now(timezone.utc).isoformat(),
        user=user,
    )


def test_profile_updates_require_a_session(api_client, auth_env):
    assert api_client.patch("/api/auth/me", json={"name": NEW_NAME}).status_code == 401


def test_password_changes_require_a_session(api_client, auth_env):
    response = api_client.post(
        "/api/auth/password",
        json={"current_password": "current-password", "new_password": NEW_PASSWORD},
    )
    assert response.status_code == 401


def test_a_signed_in_researcher_can_rename(workspace_client, monkeypatch):
    def rename(user, payload):
        return _token(user.model_copy(update={"name": payload.name}), "rotated-profile-token")

    monkeypatch.setattr(users, "update_profile", rename)
    body = workspace_client.patch("/api/auth/me", json={"name": NEW_NAME}).json()

    assert body["access_token"] == "rotated-profile-token"
    assert body["token_type"] == settings.TOKEN_TYPE
    assert body["user"]["name"] == NEW_NAME
    assert body["user"]["email"] == ACCOUNT["email"]


def test_a_signed_in_researcher_can_change_password(workspace_client, monkeypatch):
    def rotate(user, payload):
        assert payload.current_password
        assert payload.new_password == NEW_PASSWORD
        return _token(user, "rotated-password-token")

    monkeypatch.setattr(users, "change_password", rotate)
    body = workspace_client.post(
        "/api/auth/password",
        json={"current_password": "current-password", "new_password": NEW_PASSWORD},
    ).json()

    assert body["access_token"] == "rotated-password-token"
    assert body["user"]["id"] == ACCOUNT["id"]
