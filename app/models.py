import re
from datetime import datetime, timezone
from typing import Literal
from pydantic import BaseModel, field_validator, Field


# Subdomain: lowercase alphanumeric + hyphens, max 48 chars
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,46}[a-z0-9]$|^[a-z0-9]$")
# Repo URL: must be https, no shell metacharacters
_SAFE_URL_RE = re.compile(r"^https://[^\s;&|`$<>]+$")


def _check_slug(v: str) -> str:
    if not _SLUG_RE.match(v):
        raise ValueError("subdomain must be lowercase alphanumeric with hyphens, max 48 chars")
    return v


def _check_url(v: str) -> str:
    if not _SAFE_URL_RE.match(v):
        raise ValueError("repo_url must be a safe https:// URL")
    return v


class Project(BaseModel):
    id: str
    name: str
    repo_url: str
    subdomain: str
    path: str
    port: int = Field(ge=1, le=65535)
    deployed_at: datetime | None = None
    updated_at: datetime | None = None

    _validate_slug = field_validator("subdomain")(_check_slug)
    _validate_url = field_validator("repo_url")(_check_url)


class ProjectResponse(Project):
    status: Literal["running", "stopped"] = "stopped"


class DeployRequest(BaseModel):
    name: str
    repo_url: str
    subdomain: str

    _validate_slug = field_validator("subdomain")(_check_slug)
    _validate_url = field_validator("repo_url")(_check_url)


class AccuroUser(BaseModel):
    id: str
    email: str
    name: str
    role: str
    is_active: bool


class JWTClaims(BaseModel):
    sub: str
    email: str
    name: str
    role: str
    exp: int
    iat: int
