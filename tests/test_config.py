import pytest
from pydantic import ValidationError


def test_jwt_secret_too_short():
    from app.config import Settings
    with pytest.raises(ValidationError, match="at least 32"):
        Settings(
            ACCURO_URL="http://accuro:8000",
            LAUNCHPAD_JWT_SECRET="short",
            BASE_DIR="/demos",
            TUNNEL_UUID="abc",
            CF_ACCOUNT_ID="fake-account",
            CF_API_TOKEN="fake-token",
        )


def test_valid_settings():
    from app.config import Settings
    s = Settings(
        ACCURO_URL="http://accuro:8000",
        LAUNCHPAD_JWT_SECRET="a" * 32,
        BASE_DIR="/demos",
        TUNNEL_UUID="abc",
        CF_ACCOUNT_ID="fake-account",
        CF_API_TOKEN="fake-token",
    )
    assert s.allowed_roles == ["ADMIN"]
    assert s.BASE_DOMAIN == "webvakwerk.nl"
