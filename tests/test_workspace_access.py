"""The boundary between public medicine search and the research workspace."""

import jwt
import pytest
from pymongo.errors import ServerSelectionTimeoutError

from apps.api.core import content, settings
from apps.api.services import users
from tests.accounts import ACCOUNT

STORE_LEAKS = ("Mongo", "Atlas", "MONGODB", "URI", "SECRET", "pymongo")


def _assert_client_safe(detail: str) -> None:
    """Infrastructure names stay in logs, not in the body the browser shows."""
    for leak in STORE_LEAKS:
        assert leak not in detail

WORKSPACE_PATHS = (
    ("GET", "/api/dataset"),
    ("GET", "/api/insights/summary"),
    ("GET", "/api/insights/sources"),
    ("GET", "/api/insights/timeline"),
    ("GET", "/api/insights/completeness"),
    ("GET", "/api/insights/research"),
    ("GET", "/api/insights/report.csv"),
    ("POST", "/api/research/ask"),
)

PUBLIC_PATHS = (
    "/api/health",
    "/api/alerts",
    "/api/alerts/does-not-exist",
)

QUESTION = {"question": "latest"}


def bearer(token: str) -> dict:
    return {"Authorization": f"{settings.AUTH_SCHEME} {token}"}


@pytest.mark.parametrize(("method", "path"), WORKSPACE_PATHS)
def test_workspace_endpoints_refuse_anonymous_requests(api_client, auth_env, method, path):
    response = api_client.request(method, path, json=QUESTION)

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == settings.AUTH_SCHEME


@pytest.mark.parametrize(("method", "path"), WORKSPACE_PATHS)
def test_workspace_endpoints_accept_a_signed_token(workspace_client, method, path):
    assert workspace_client.request(method, path, json=QUESTION).status_code == 200


@pytest.mark.parametrize("path", PUBLIC_PATHS)
def test_public_endpoints_stay_open(api_client, path):
    assert api_client.get(path).status_code != 401


def test_public_alert_explanation_stays_open(api_client):
    """Someone reading a notice must never be asked to sign in."""
    record_id = api_client.get("/api/alerts").json()["items"][0]["record_id"]

    assert api_client.post(f"/api/alerts/{record_id}/explain").status_code == 200


def test_an_expired_token_is_refused(api_client, access_token):
    response = api_client.get("/api/dataset", headers=bearer(access_token(-1)))

    assert response.status_code == 401


def test_a_token_signed_with_another_secret_is_refused(api_client, auth_env):
    forged = jwt.encode(
        {"sub": ACCOUNT["id"], "exp": 9999999999},
        "not-our-secret",
        algorithm=settings.JWT_ALGORITHM,
    )

    assert api_client.get("/api/dataset", headers=bearer(forged)).status_code == 401


def test_a_token_without_an_identity_is_refused(api_client, access_token):
    """Our own signature is not enough; the claims have to describe a user."""
    response = api_client.get("/api/dataset", headers=bearer(access_token(name="", email="")))

    assert response.status_code == 401


def test_the_session_endpoint_returns_the_signed_in_researcher(workspace_client):
    body = workspace_client.get("/api/auth/me").json()

    assert body == {
        "id": ACCOUNT["id"],
        "name": ACCOUNT["name"],
        "email": ACCOUNT["email"],
        "role": settings.DEFAULT_USER_ROLE,
    }


def test_the_session_endpoint_refuses_anonymous_requests(api_client, auth_env):
    assert api_client.get("/api/auth/me").status_code == 401


def test_the_workspace_closes_when_authentication_is_unconfigured(
    api_client, access_token, monkeypatch
):
    """Missing credentials must lock the workspace, not leave it open."""
    token = access_token()
    monkeypatch.delenv("V2_AUTH_SECRET", raising=False)

    response = api_client.get("/api/dataset", headers=bearer(token))
    assert response.status_code == 503
    _assert_client_safe(response.json()["detail"])


def test_new_accounts_are_not_created(api_client):
    response = api_client.post(
        "/api/auth/register",
        json={
            "name": ACCOUNT["name"],
            "email": ACCOUNT["email"],
            "password": "long-enough",
        },
    )

    assert response.status_code == 403
    assert "Mongo" not in response.json()["detail"]


def test_sign_in_does_not_name_the_account_store(api_client, monkeypatch):
    def fail():
        raise ServerSelectionTimeoutError("timed out")

    monkeypatch.setattr(users, "_accounts", fail)
    response = api_client.post(
        "/api/auth/login",
        json={"email": ACCOUNT["email"], "password": "not-the-password"},
    )

    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail == content.ERRORS["auth_store_unavailable"]
    _assert_client_safe(detail)
