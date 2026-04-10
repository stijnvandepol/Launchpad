# tests/test_dependencies.py
import time
import pytest
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient
from app.config import Settings, get_settings
from app.services.jwt_service import sign_token

SECRET = "a" * 32


def _make_app():
    from app.dependencies import require_user

    app = FastAPI()

    def override_settings():
        return Settings(ACCURO_URL="http://x", LAUNCHPAD_JWT_SECRET=SECRET, TUNNEL_UUID="t")

    app.dependency_overrides[get_settings] = override_settings

    @app.get("/me")
    def me(user=Depends(require_user)):
        return {"sub": user.sub}

    return app


def test_valid_token_passes():
    token = sign_token({"sub": "u1", "email": "a@b.com", "name": "Alice", "role": "admin"}, SECRET)
    client = TestClient(_make_app())
    r = client.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["sub"] == "u1"


def test_missing_token_returns_403():
    client = TestClient(_make_app(), raise_server_exceptions=False)
    r = client.get("/me")
    assert r.status_code in (401, 403)


def test_invalid_token_returns_401():
    client = TestClient(_make_app(), raise_server_exceptions=False)
    r = client.get("/me", headers={"Authorization": "Bearer badtoken"})
    assert r.status_code == 401


def test_token_missing_claims_returns_401():
    from jose import jwt as jose_jwt
    # Valid signature, but missing required JWTClaims fields
    bad_payload = {"sub": "u1", "iat": 1000000, "exp": 9999999999}
    token = jose_jwt.encode(bad_payload, SECRET, algorithm="HS256")
    client = TestClient(_make_app(), raise_server_exceptions=False)
    r = client.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401
