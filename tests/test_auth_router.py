"""Tests for OIDC auth router."""
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from jose import jwt
from datetime import datetime, timedelta, timezone

from app.config import get_settings

SECRET = "a" * 32
ACCURO_URL = "http://accuro.test"
LAUNCHPAD_BASE_URL = "http://launchpad.test"


def _make_settings(**kwargs):
    settings = MagicMock()
    settings.ACCURO_URL = ACCURO_URL
    settings.ACCURO_CLIENT_ID = "launchpad"
    settings.ACCURO_CLIENT_SECRET = "secret"
    settings.LAUNCHPAD_BASE_URL = LAUNCHPAD_BASE_URL
    settings.LAUNCHPAD_JWT_SECRET = SECRET
    for k, v in kwargs.items():
        setattr(settings, k, v)
    return settings


def _make_state_jwt(secret: str) -> str:
    now = datetime.now(tz=timezone.utc)
    payload = {
        "type": "oauth_state",
        "nonce": "test-nonce",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=10)).timestamp()),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def _make_app(settings=None):
    from app.routers.auth import router
    app = FastAPI()
    app.include_router(router)
    _settings = settings or _make_settings()
    app.dependency_overrides[get_settings] = lambda: _settings
    return app


class TestLoginRedirect:
    def test_login_redirects_to_accuro(self):
        """GET /auth/login should redirect to Accuro authorize endpoint."""
        client = TestClient(_make_app(), follow_redirects=False)
        response = client.get("/auth/login")

        assert response.status_code == 302
        location = response.headers["location"]
        assert f"{ACCURO_URL}/oauth/authorize" in location
        assert "client_id=launchpad" in location
        assert "state=" in location

    def test_login_redirect_contains_response_type_code(self):
        """Authorize URL must include response_type=code."""
        client = TestClient(_make_app(), follow_redirects=False)
        response = client.get("/auth/login")

        assert response.status_code == 302
        assert "response_type=code" in response.headers["location"]

    def test_login_redirect_contains_redirect_uri(self):
        """Authorize URL must include the Launchpad callback redirect_uri."""
        client = TestClient(_make_app(), follow_redirects=False)
        response = client.get("/auth/login")

        assert response.status_code == 302
        assert "redirect_uri=" in response.headers["location"]


class TestCallback:
    def test_callback_success_redirects_to_frontend(self):
        """Valid callback → redirect to /callback?token=..."""
        app = _make_app()
        state = _make_state_jwt(SECRET)

        mock_token_response = {
            "id_token": "fake-id-token",
            "access_token": "fake-access-token",
        }
        mock_claims = {
            "sub": "1",
            "email": "user@test.com",
            "name": "Test User",
            "role": "USER",
        }

        with patch("app.routers.auth.exchange_code", new_callable=AsyncMock) as mock_exchange, \
             patch("app.routers.auth.fetch_jwks", new_callable=AsyncMock) as mock_jwks, \
             patch("app.routers.auth.verify_id_token", return_value=mock_claims):
            mock_exchange.return_value = mock_token_response
            mock_jwks.return_value = {"keys": []}

            client = TestClient(app, follow_redirects=False)
            response = client.get(f"/auth/callback?code=mycode&state={state}")

        assert response.status_code == 302
        location = response.headers["location"]
        assert f"{LAUNCHPAD_BASE_URL}/callback" in location
        assert "token=" in location

    def test_callback_error_param_redirects_to_login(self):
        """Error param from Accuro → redirect to /login?error=auth_failed"""
        client = TestClient(_make_app(), follow_redirects=False)
        response = client.get("/auth/callback?error=access_denied")

        assert response.status_code == 302
        assert "error=auth_failed" in response.headers["location"]

    def test_callback_missing_code_redirects_to_login(self):
        """Missing code param → redirect to /login?error=auth_failed"""
        state = _make_state_jwt(SECRET)
        client = TestClient(_make_app(), follow_redirects=False)
        response = client.get(f"/auth/callback?state={state}")

        assert response.status_code == 302
        assert "error=auth_failed" in response.headers["location"]

    def test_callback_missing_state_redirects_to_login(self):
        """Missing state param → redirect to /login?error=auth_failed"""
        client = TestClient(_make_app(), follow_redirects=False)
        response = client.get("/auth/callback?code=mycode")

        assert response.status_code == 302
        assert "error=auth_failed" in response.headers["location"]

    def test_callback_invalid_state_redirects_to_login(self):
        """Invalid state JWT → redirect to /login?error=auth_failed"""
        client = TestClient(_make_app(), follow_redirects=False)
        response = client.get("/auth/callback?code=mycode&state=invalid-state")

        assert response.status_code == 302
        assert "error=auth_failed" in response.headers["location"]

    def test_callback_expired_state_redirects_to_login(self):
        """Expired state JWT → redirect to /login?error=auth_failed"""
        now = datetime.now(tz=timezone.utc)
        payload = {
            "type": "oauth_state",
            "nonce": "n",
            "iat": int((now - timedelta(minutes=20)).timestamp()),
            "exp": int((now - timedelta(minutes=10)).timestamp()),
        }
        expired_state = jwt.encode(payload, SECRET, algorithm="HS256")

        client = TestClient(_make_app(), follow_redirects=False)
        response = client.get(f"/auth/callback?code=mycode&state={expired_state}")

        assert response.status_code == 302
        assert "error=auth_failed" in response.headers["location"]

    def test_callback_exchange_failure_redirects_to_login(self):
        """Token exchange failure → redirect to /login?error=auth_failed"""
        from app.services.oidc_client import OIDCError
        app = _make_app()
        state = _make_state_jwt(SECRET)

        with patch("app.routers.auth.exchange_code", new_callable=AsyncMock) as mock_exchange:
            mock_exchange.side_effect = OIDCError("token exchange failed")

            client = TestClient(app, follow_redirects=False)
            response = client.get(f"/auth/callback?code=mycode&state={state}")

        assert response.status_code == 302
        assert "error=auth_failed" in response.headers["location"]

    def test_callback_missing_id_token_redirects_to_login(self):
        """Token response without id_token → redirect to /login?error=auth_failed"""
        app = _make_app()
        state = _make_state_jwt(SECRET)

        with patch("app.routers.auth.exchange_code", new_callable=AsyncMock) as mock_exchange:
            mock_exchange.return_value = {"access_token": "tok"}  # no id_token

            client = TestClient(app, follow_redirects=False)
            response = client.get(f"/auth/callback?code=mycode&state={state}")

        assert response.status_code == 302
        assert "error=auth_failed" in response.headers["location"]

    def test_callback_token_contains_user_claims(self):
        """Issued Launchpad token must contain the OIDC user claims."""
        app = _make_app()
        state = _make_state_jwt(SECRET)

        mock_claims = {
            "sub": "42",
            "email": "alice@example.com",
            "name": "Alice",
            "role": "ADMIN",
        }

        with patch("app.routers.auth.exchange_code", new_callable=AsyncMock) as mock_exchange, \
             patch("app.routers.auth.fetch_jwks", new_callable=AsyncMock) as mock_jwks, \
             patch("app.routers.auth.verify_id_token", return_value=mock_claims):
            mock_exchange.return_value = {"id_token": "fake"}
            mock_jwks.return_value = {"keys": []}

            client = TestClient(app, follow_redirects=False)
            response = client.get(f"/auth/callback?code=mycode&state={state}")

        assert response.status_code == 302
        location = response.headers["location"]
        token = location.split("token=")[1]
        decoded = jwt.decode(token, SECRET, algorithms=["HS256"])
        assert decoded["sub"] == "42"
        assert decoded["email"] == "alice@example.com"
        assert decoded["name"] == "Alice"
        assert decoded["role"] == "ADMIN"
