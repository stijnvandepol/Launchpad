"""OIDC client service for Launchpad."""
import time
from typing import Any
from urllib.parse import urlencode

import httpx
from jose import JWTError, jwt

from app.config import Settings


class OIDCError(Exception):
    """Raised when OIDC flow fails."""


# In-process JWKS cache: {url: {"jwks": dict, "fetched_at": float}}
_jwks_cache: dict[str, dict[str, Any]] = {}
_JWKS_TTL = 3600  # 1 hour


def build_authorize_url(settings: Settings, state: str) -> str:
    """Build the Accuro OIDC authorization URL."""
    params = urlencode({
        "client_id": settings.ACCURO_CLIENT_ID,
        "redirect_uri": f"{settings.LAUNCHPAD_BASE_URL}/auth/callback",
        "scope": "openid profile",
        "state": state,
        "response_type": "code",
    })
    return f"{settings.ACCURO_URL}/oauth/authorize?{params}"


async def exchange_code(settings: Settings, code: str, redirect_uri: str) -> dict:
    """Exchange authorization code for tokens at Accuro token endpoint."""
    async with httpx.AsyncClient() as http:
        response = await http.post(
            f"{settings.ACCURO_URL}/oauth/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": settings.ACCURO_CLIENT_ID,
                "client_secret": settings.ACCURO_CLIENT_SECRET,
                "redirect_uri": redirect_uri,
            },
        )
    if response.status_code != 200:
        raise OIDCError(f"Token exchange failed: {response.status_code}")
    return response.json()


async def fetch_jwks(settings: Settings) -> dict:
    """Fetch JWKS from Accuro, cached for 1 hour."""
    jwks_url = f"{settings.ACCURO_URL}/oauth/jwks"
    cached = _jwks_cache.get(jwks_url)
    if cached and (time.time() - cached["fetched_at"]) < _JWKS_TTL:
        return cached["jwks"]

    async with httpx.AsyncClient() as http:
        response = await http.get(jwks_url)
    if response.status_code != 200:
        raise OIDCError(f"JWKS fetch failed: {response.status_code}")

    jwks = response.json()
    _jwks_cache[jwks_url] = {"jwks": jwks, "fetched_at": time.time()}
    return jwks


def verify_id_token(id_token: str, jwks: dict, client_id: str, issuer: str) -> dict:
    """Verify RS256 ID token signature and claims."""
    try:
        claims = jwt.decode(
            id_token,
            jwks,
            algorithms=["RS256"],
            audience=client_id,
            issuer=issuer,
        )
    except JWTError as exc:
        raise OIDCError(f"ID token verification failed: {exc}") from exc
    return claims
