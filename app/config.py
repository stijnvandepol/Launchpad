from functools import lru_cache
from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    ACCURO_URL: str
    ACCURO_ALLOWED_ROLES: str = "admin"
    LAUNCHPAD_JWT_SECRET: str
    BASE_DIR: str = "/demos"
    TUNNEL_UUID: str
    CF_ACCOUNT_ID: str
    CF_API_TOKEN: str
    BASE_DOMAIN: str = "webvakwerk.nl"
    PORT: int = 3000
    GITHUB_PAT: str | None = None  # optional, for private repos

    @field_validator("LAUNCHPAD_JWT_SECRET")
    @classmethod
    def jwt_secret_min_length(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError("LAUNCHPAD_JWT_SECRET must be at least 32 characters")
        return v

    @property
    def allowed_roles(self) -> list[str]:
        return [r.strip().upper() for r in self.ACCURO_ALLOWED_ROLES.split(",") if r.strip()]

    model_config = {"env_file": ".env", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
