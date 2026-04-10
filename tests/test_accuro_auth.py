import pytest
import respx
import httpx


@pytest.fixture
def accuro_url():
    return "http://accuro-test:8000"


@pytest.mark.asyncio
async def test_login_success(accuro_url):
    from app.services.accuro_auth import login_via_accuro
    async with respx.mock:
        respx.post(f"{accuro_url}/api/v1/auth/login").mock(
            return_value=httpx.Response(200, json={"access_token": "tok123"})
        )
        token = await login_via_accuro("admin@test.com", "pass123", accuro_url)
    assert token == "tok123"


@pytest.mark.asyncio
async def test_login_invalid_credentials(accuro_url):
    from app.services.accuro_auth import login_via_accuro, AccuroAuthError
    async with respx.mock:
        respx.post(f"{accuro_url}/api/v1/auth/login").mock(
            return_value=httpx.Response(401, json={"detail": "Invalid email or password"})
        )
        with pytest.raises(AccuroAuthError, match="Invalid credentials"):
            await login_via_accuro("wrong@test.com", "bad", accuro_url)


@pytest.mark.asyncio
async def test_verify_success(accuro_url):
    from app.services.accuro_auth import verify_accuro_token
    async with respx.mock:
        respx.get(f"{accuro_url}/api/v1/auth/verify").mock(
            return_value=httpx.Response(200, json={
                "id": "u1", "email": "admin@test.com",
                "name": "Admin", "role": "admin", "is_active": True,
            })
        )
        user = await verify_accuro_token("tok123", accuro_url)
    assert user.role == "admin"
    assert user.email == "admin@test.com"


@pytest.mark.asyncio
async def test_verify_expired_token(accuro_url):
    from app.services.accuro_auth import verify_accuro_token, AccuroAuthError
    async with respx.mock:
        respx.get(f"{accuro_url}/api/v1/auth/verify").mock(
            return_value=httpx.Response(401, json={"detail": "Invalid or expired token"})
        )
        with pytest.raises(AccuroAuthError, match="Token invalid"):
            await verify_accuro_token("expired_token", accuro_url)


@pytest.mark.asyncio
async def test_accuro_unreachable(accuro_url):
    from app.services.accuro_auth import login_via_accuro, AccuroAuthError
    async with respx.mock:
        respx.post(f"{accuro_url}/api/v1/auth/login").mock(
            side_effect=httpx.ConnectError("Connection refused")
        )
        with pytest.raises(AccuroAuthError, match="unreachable"):
            await login_via_accuro("admin@test.com", "pass", accuro_url)
