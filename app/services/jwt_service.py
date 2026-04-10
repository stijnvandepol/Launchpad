from jose import jwt, JWTError
from datetime import datetime, timezone
from app.models import JWTClaims

ALGORITHM = "HS256"
TOKEN_EXPIRY_SECONDS = 8 * 3600  # 8 hours


def sign_token(claims: dict, secret: str) -> str:
    now = int(datetime.now(timezone.utc).timestamp())
    payload = {
        **claims,
        "iat": now,
        "exp": now + TOKEN_EXPIRY_SECONDS,
    }
    return jwt.encode(payload, secret, algorithm=ALGORITHM)


def verify_token(token: str, secret: str) -> JWTClaims:
    try:
        payload = jwt.decode(token, secret, algorithms=[ALGORITHM])
        return JWTClaims.model_validate(payload)
    except (JWTError, Exception) as e:
        raise ValueError(f"Invalid token: {e}")
