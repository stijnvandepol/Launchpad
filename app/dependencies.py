# app/dependencies.py
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
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
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
