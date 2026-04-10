import pytest
from app.services.jwt_service import sign_token, verify_token

SECRET = "a" * 32


def test_sign_and_verify_roundtrip():
    claims = {"sub": "u1", "email": "a@b.com", "name": "Alice", "role": "admin"}
    token = sign_token(claims, SECRET)
    result = verify_token(token, SECRET)
    assert result.sub == "u1"
    assert result.email == "a@b.com"
    assert result.role == "admin"


def test_verify_wrong_secret_raises():
    claims = {"sub": "u1", "email": "a@b.com", "name": "Alice", "role": "admin"}
    token = sign_token(claims, SECRET)
    with pytest.raises(ValueError, match="Invalid token"):
        verify_token(token, "b" * 32)


def test_verify_expired_token_raises():
    from jose import jwt as jose_jwt
    past_payload = {
        "sub": "u1", "email": "a@b.com", "name": "Alice", "role": "admin",
        "iat": 1000000, "exp": 1000001,  # fixed past timestamps
    }
    expired_token = jose_jwt.encode(past_payload, SECRET, algorithm="HS256")
    with pytest.raises(ValueError, match="Invalid token"):
        verify_token(expired_token, SECRET)


def test_verify_garbage_raises():
    with pytest.raises(ValueError, match="Invalid token"):
        verify_token("not.a.token", SECRET)
