"""Tests for app/services/oidc_client.py"""
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from jose import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

from app.services.oidc_client import (
    OIDCError,
    build_authorize_url,
    exchange_code,
    fetch_jwks,
    verify_id_token,
    _jwks_cache,
)


# Generate a test RSA key pair once for the module
_TEST_PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_TEST_PRIVATE_PEM = _TEST_PRIVATE_KEY.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.TraditionalOpenSSL,
    encryption_algorithm=serialization.NoEncryption(),
).decode()
_TEST_PUBLIC_PEM = _TEST_PRIVATE_KEY.public_key().public_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PublicFormat.SubjectPublicKeyInfo,
).decode()


def _make_settings(**kwargs):
    """Create a minimal Settings-like object for testing."""
    from unittest.mock import MagicMock
    settings = MagicMock()
    settings.ACCURO_URL = "http://accuro.test"
    settings.ACCURO_CLIENT_ID = "launchpad"
    settings.ACCURO_CLIENT_SECRET = "secret"
    settings.LAUNCHPAD_BASE_URL = "http://launchpad.test"
    for k, v in kwargs.items():
        setattr(settings, k, v)
    return settings


class TestBuildAuthorizeUrl:
    def test_build_authorize_url_contains_required_params(self):
        settings = _make_settings()
        state = "test-state"
        url = build_authorize_url(settings, state)
        assert url.startswith("http://accuro.test/oauth/authorize")
        assert "client_id=launchpad" in url
        assert "redirect_uri=http://launchpad.test/auth/callback" in url
        assert "state=test-state" in url
        assert "openid" in url


class TestExchangeCode:
    async def test_exchange_code_success(self):
        settings = _make_settings()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "acc",
            "id_token": "id",
            "token_type": "bearer",
        }
        with patch("app.services.oidc_client.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client
            result = await exchange_code(settings, "mycode", "http://launchpad.test/auth/callback")
        assert result["id_token"] == "id"

    async def test_exchange_code_failure_raises_oidc_error(self):
        settings = _make_settings()
        mock_response = MagicMock()
        mock_response.status_code = 400
        with patch("app.services.oidc_client.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client
            with pytest.raises(OIDCError):
                await exchange_code(settings, "badcode", "http://launchpad.test/auth/callback")


class TestFetchJwks:
    async def test_fetch_jwks_caches_result(self):
        settings = _make_settings()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"keys": [{"kty": "RSA"}]}

        _jwks_cache.clear()
        with patch("app.services.oidc_client.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            result1 = await fetch_jwks(settings)
            result2 = await fetch_jwks(settings)  # should use cache

            # HTTP was only called once
            assert mock_client.get.call_count == 1
        assert result1 == result2


class TestVerifyIdToken:
    def test_verify_id_token_valid(self):
        import time
        now = int(time.time())
        claims = {
            "sub": "1",
            "email": "test@example.com",
            "name": "Test",
            "role": "ADMIN",
            "iss": "http://accuro.test",
            "aud": "launchpad",
            "iat": now,
            "exp": now + 3600,
        }
        token = jwt.encode(claims, _TEST_PRIVATE_PEM, algorithm="RS256")

        # Build a minimal JWKS-like structure using the public PEM
        # python-jose can verify using the public PEM directly as the "keys" value
        result = verify_id_token(token, _TEST_PUBLIC_PEM, "launchpad", "http://accuro.test")
        assert result["email"] == "test@example.com"
        assert result["sub"] == "1"

    def test_verify_id_token_wrong_audience_raises(self):
        import time
        now = int(time.time())
        claims = {
            "sub": "1",
            "iss": "http://accuro.test",
            "aud": "other-client",
            "iat": now,
            "exp": now + 3600,
        }
        token = jwt.encode(claims, _TEST_PRIVATE_PEM, algorithm="RS256")
        with pytest.raises(OIDCError):
            verify_id_token(token, _TEST_PUBLIC_PEM, "launchpad", "http://accuro.test")

    def test_verify_id_token_expired_raises(self):
        import time
        now = int(time.time())
        claims = {
            "sub": "1",
            "iss": "http://accuro.test",
            "aud": "launchpad",
            "iat": now - 7200,
            "exp": now - 3600,  # expired 1 hour ago
        }
        token = jwt.encode(claims, _TEST_PRIVATE_PEM, algorithm="RS256")
        with pytest.raises(OIDCError):
            verify_id_token(token, _TEST_PUBLIC_PEM, "launchpad", "http://accuro.test")
