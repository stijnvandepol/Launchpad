"""Auth router — OIDC Authorization Code flow."""
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from fastapi.responses import RedirectResponse
from jose import JWTError, jwt

from app.config import get_settings, Settings
from app.services.oidc_client import OIDCError, build_authorize_url, exchange_code, fetch_jwks, verify_id_token

router = APIRouter(prefix="/auth", tags=["auth"])


def _create_state_jwt(settings) -> str:
    """Create a signed state JWT for CSRF protection."""
    now = datetime.now(tz=timezone.utc)
    payload = {
        "type": "oauth_state",
        "nonce": str(uuid.uuid4()),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=10)).timestamp()),
    }
    return jwt.encode(payload, settings.LAUNCHPAD_JWT_SECRET, algorithm="HS256")


def _verify_state_jwt(token: str, settings) -> bool:
    """Verify the state JWT. Returns False if invalid."""
    try:
        claims = jwt.decode(token, settings.LAUNCHPAD_JWT_SECRET, algorithms=["HS256"])
        return claims.get("type") == "oauth_state"
    except JWTError:
        return False


_SESSION_TOKEN_EXPIRY_SECONDS = 8 * 3600  # 8 hours


def _issue_session_token(claims: dict, settings) -> str:
    """Issue a Launchpad session JWT from OIDC claims."""
    now = int(datetime.now(tz=timezone.utc).timestamp())
    payload = {
        "sub": claims["sub"],
        "email": claims["email"],
        "name": claims.get("name", ""),
        "role": claims.get("role", ""),
        "iat": now,
        "exp": now + _SESSION_TOKEN_EXPIRY_SECONDS,
    }
    return jwt.encode(payload, settings.LAUNCHPAD_JWT_SECRET, algorithm="HS256")


@router.get("/login")
async def login(settings: Settings = Depends(get_settings)):
    """Start OIDC flow — redirect to Accuro authorize endpoint."""
    state = _create_state_jwt(settings)
    authorize_url = build_authorize_url(settings, state)
    return RedirectResponse(authorize_url, status_code=302)


@router.get("/callback")
async def callback(
    code: str = "",
    state: str = "",
    error: str = "",
    settings: Settings = Depends(get_settings),
):
    """OIDC callback — exchange code for tokens, issue Launchpad JWT."""
    frontend_error_url = f"{settings.LAUNCHPAD_BASE_URL}/login?error=auth_failed"

    if error:
        return RedirectResponse(frontend_error_url, status_code=302)

    if not code or not state:
        return RedirectResponse(frontend_error_url, status_code=302)

    # Verify state JWT (CSRF check)
    if not _verify_state_jwt(state, settings):
        return RedirectResponse(frontend_error_url, status_code=302)

    try:
        redirect_uri = f"{settings.LAUNCHPAD_BASE_URL}/auth/callback"
        token_response = await exchange_code(settings, code, redirect_uri)
        id_token = token_response.get("id_token")
        if not id_token:
            return RedirectResponse(frontend_error_url, status_code=302)

        # Verify ID token
        jwks = await fetch_jwks(settings)
        claims = verify_id_token(id_token, jwks, settings.ACCURO_CLIENT_ID, settings.ACCURO_URL)

        # Issue Launchpad session JWT
        launchpad_token = _issue_session_token(claims, settings)

        frontend_callback_url = f"{settings.LAUNCHPAD_BASE_URL}/callback?token={launchpad_token}"
        return RedirectResponse(frontend_callback_url, status_code=302)

    except (OIDCError, Exception):
        return RedirectResponse(frontend_error_url, status_code=302)
