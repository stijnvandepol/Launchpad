# app/routers/auth.py
from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel
from app.services.accuro_auth import login_via_accuro, verify_accuro_token, AccuroAuthError
from app.services.jwt_service import sign_token
from app.config import get_settings, Settings

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, settings: Settings = Depends(get_settings)):
    try:
        accuro_token = await login_via_accuro(body.email, body.password, settings.ACCURO_URL)
        user = await verify_accuro_token(accuro_token, settings.ACCURO_URL)
    except AccuroAuthError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if user.role.upper() not in settings.allowed_roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Role not permitted")

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account inactive")

    token = sign_token(
        {"sub": user.id, "email": user.email, "name": user.name, "role": user.role},
        settings.LAUNCHPAD_JWT_SECRET,
    )
    return TokenResponse(access_token=token)
