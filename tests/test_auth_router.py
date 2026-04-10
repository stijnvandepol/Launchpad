# tests/test_auth_router.py
import pytest
import respx
import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.config import Settings, get_settings

SECRET = "a" * 32
ACCURO_URL = "http://accuro-test:8000"


def _app():
    from app.routers.auth import router
    app = FastAPI()
    app.include_router(router)

    def override():
        return Settings(
            ACCURO_URL=ACCURO_URL,
            LAUNCHPAD_JWT_SECRET=SECRET,
            TUNNEL_UUID="t",
        )

    app.dependency_overrides[get_settings] = override
    return app


@pytest.mark.asyncio
async def test_login_returns_token():
    async with respx.mock:
        respx.post(f"{ACCURO_URL}/api/v1/auth/login").mock(
            return_value=httpx.Response(200, json={"access_token": "accuro-tok"})
        )
        respx.get(f"{ACCURO_URL}/api/v1/auth/verify").mock(
            return_value=httpx.Response(200, json={
                "id": "u1", "email": "admin@test.com",
                "name": "Admin", "role": "admin", "is_active": True,
            })
        )
        client = TestClient(_app())
        r = client.post("/auth/login", json={"email": "admin@test.com", "password": "pass"})
    assert r.status_code == 200
    assert "access_token" in r.json()
    assert r.json()["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_login_wrong_password_returns_401():
    async with respx.mock:
        respx.post(f"{ACCURO_URL}/api/v1/auth/login").mock(
            return_value=httpx.Response(401, json={"detail": "Invalid credentials"})
        )
        client = TestClient(_app(), raise_server_exceptions=False)
        r = client.post("/auth/login", json={"email": "a@b.com", "password": "wrong"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_login_disallowed_role_returns_403():
    async with respx.mock:
        respx.post(f"{ACCURO_URL}/api/v1/auth/login").mock(
            return_value=httpx.Response(200, json={"access_token": "tok"})
        )
        respx.get(f"{ACCURO_URL}/api/v1/auth/verify").mock(
            return_value=httpx.Response(200, json={
                "id": "u2", "email": "viewer@test.com",
                "name": "Viewer", "role": "viewer", "is_active": True,
            })
        )
        client = TestClient(_app(), raise_server_exceptions=False)
        r = client.post("/auth/login", json={"email": "viewer@test.com", "password": "pass"})
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_login_accuro_unreachable_returns_401():
    async with respx.mock:
        respx.post(f"{ACCURO_URL}/api/v1/auth/login").mock(
            side_effect=httpx.ConnectError("refused")
        )
        client = TestClient(_app(), raise_server_exceptions=False)
        r = client.post("/auth/login", json={"email": "a@b.com", "password": "pass"})
    assert r.status_code == 401
