import httpx
from app.models import AccuroUser


class AccuroAuthError(Exception):
    pass


async def login_via_accuro(email: str, password: str, accuro_url: str) -> str:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{accuro_url}/api/v1/auth/login",
                json={"email": email, "password": password},
            )
    except httpx.ConnectError:
        raise AccuroAuthError("Accuro is unreachable")
    except httpx.TimeoutException:
        raise AccuroAuthError("Accuro request timed out")

    if resp.status_code == 401:
        raise AccuroAuthError("Invalid credentials")
    if resp.status_code != 200:
        raise AccuroAuthError(f"Accuro returned {resp.status_code}")

    data = resp.json()
    if "access_token" not in data:
        raise AccuroAuthError("Accuro response missing access_token")
    return data["access_token"]


async def verify_accuro_token(token: str, accuro_url: str) -> AccuroUser:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{accuro_url}/api/v1/auth/verify",
                headers={"Authorization": f"Bearer {token}"},
            )
    except httpx.ConnectError:
        raise AccuroAuthError("Accuro is unreachable")
    except httpx.TimeoutException:
        raise AccuroAuthError("Accuro request timed out")

    if resp.status_code == 401:
        raise AccuroAuthError("Token invalid or expired")
    if resp.status_code != 200:
        raise AccuroAuthError(f"Accuro verify returned {resp.status_code}")

    return AccuroUser.model_validate(resp.json())
