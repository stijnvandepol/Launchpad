# app/dependencies.py
from fastapi import Depends, HTTPException, Query, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import ValidationError
from app.services.jwt_service import verify_token
from app.config import get_settings, Settings
from app.models import JWTClaims

_bearer = HTTPBearer()


def require_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    settings: Settings = Depends(get_settings),
) -> JWTClaims:
    try:
        return verify_token(credentials.credentials, settings.LAUNCHPAD_JWT_SECRET)
    except (ValueError, ValidationError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def require_user_sse(
    token: str = Query(..., description="JWT token for SSE auth"),
    settings: Settings = Depends(get_settings),
) -> JWTClaims:
    """Dependency for SSE endpoints — accepts token as query param."""
    try:
        return verify_token(token, settings.LAUNCHPAD_JWT_SECRET)
    except (ValueError, ValidationError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
