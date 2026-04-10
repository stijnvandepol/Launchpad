import pytest
from pydantic import ValidationError


def test_jwt_secret_too_short():
    from app.config import Settings
    with pytest.raises(ValidationError, match="at least 32"):
        Settings(
            ACCURO_URL="http://accuro:8000",
            LAUNCHPAD_JWT_SECRET="short",
            BASE_DIR="/demos",
            CLOUDFLARED_CONFIG="/cloudflared/config.yml",
            TUNNEL_UUID="abc",
        )


def test_valid_settings():
    from app.config import Settings
    s = Settings(
        ACCURO_URL="http://accuro:8000",
        LAUNCHPAD_JWT_SECRET="a" * 32,
        BASE_DIR="/demos",
        CLOUDFLARED_CONFIG="/cloudflared/config.yml",
        TUNNEL_UUID="abc",
    )
    assert s.allowed_roles == ["admin"]
    assert s.BASE_DOMAIN == "webvakwerk.nl"
