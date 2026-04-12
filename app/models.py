import re
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from pydantic import BaseModel, field_validator, ValidationError
from pydantic_core import InitErrorDetails, PydanticCustomError
from sqlmodel import SQLModel, Field as SQLField


# Subdomain: lowercase alphanumeric + hyphens, 1-48 chars
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,46}[a-z0-9]$|^[a-z0-9]$")
# Repo URL: must be https, no shell metacharacters
_SAFE_URL_RE = re.compile(r"^https://[^\s;&|`$<>]+$")
# Name: alphanumeric, hyphens, underscores only
_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


def _check_slug(v: str) -> str:
    if not _SLUG_RE.match(v):
        raise ValueError("subdomain must be lowercase alphanumeric with hyphens, max 48 chars")
    return v


def _check_url(v: str) -> str:
    if not _SAFE_URL_RE.match(v):
        raise ValueError("repo_url must be a safe https:// URL")
    return v


def _check_name(v: str) -> str:
    if not _NAME_RE.match(v):
        raise ValueError("name must contain only alphanumeric characters, hyphens, or underscores")
    return v


def _raise_validation_errors(cls_name: str, errors: list) -> None:
    raise ValidationError.from_exception_data(
        cls_name,
        [
            InitErrorDetails(
                type=PydanticCustomError("value_error", e["msg"]),
                loc=e["loc"],
                input=e["input"],
            )
            for e in errors
        ],
    )


class ProjectStatus(str, Enum):
    pending  = "pending"
    cloning  = "cloning"
    cloned   = "cloned"
    building = "building"
    running  = "running"
    failed   = "failed"
    stopped  = "stopped"


class Project(SQLModel, table=True):
    id:          str            = SQLField(primary_key=True)
    name:        str
    repo_url:    str
    subdomain:   str            = SQLField(unique=True, index=True)
    path:        str
    port:        int            = SQLField(ge=1, le=65535)
    status:      ProjectStatus  = SQLField(default=ProjectStatus.pending)
    error:       Optional[str]  = SQLField(default=None)
    deployed_at: Optional[datetime] = SQLField(default=None)
    updated_at:  Optional[datetime] = SQLField(default=None)

    model_config = {"arbitrary_types_allowed": True}

    def __init__(self, **data):
        errors = []
        name = data.get("name", "")
        if not _NAME_RE.match(name):
            errors.append({"loc": ("name",), "msg": "name must contain only alphanumeric characters, hyphens, or underscores", "input": name})
        port = data.get("port")
        if port is not None:
            try:
                port_int = int(port)
                if not (1 <= port_int <= 65535):
                    errors.append({"loc": ("port",), "msg": "port must be between 1 and 65535", "input": port})
            except (TypeError, ValueError):
                errors.append({"loc": ("port",), "msg": "port must be an integer", "input": port})
        repo_url = data.get("repo_url", "")
        if not _SAFE_URL_RE.match(repo_url):
            errors.append({"loc": ("repo_url",), "msg": "repo_url must be a safe https:// URL", "input": repo_url})
        subdomain = data.get("subdomain", "")
        if not _SLUG_RE.match(subdomain):
            errors.append({"loc": ("subdomain",), "msg": "subdomain must be lowercase alphanumeric with hyphens, max 48 chars", "input": subdomain})
        if errors:
            _raise_validation_errors(type(self).__name__, errors)
        super().__init__(**data)


class LogLine(SQLModel, table=True):
    id:         Optional[int] = SQLField(default=None, primary_key=True)
    project_id: str           = SQLField(index=True)
    ts:         datetime      = SQLField(default_factory=lambda: datetime.now(timezone.utc))
    text:       str


class ProjectResponse(BaseModel):
    id:          str
    name:        str
    repo_url:    str
    subdomain:   str
    path:        str
    port:        int
    status:      ProjectStatus
    error:       Optional[str] = None
    deployed_at: Optional[datetime] = None
    updated_at:  Optional[datetime] = None


class DeployRequest(BaseModel):
    name:       str
    repo_url:   str
    subdomain:  str
    @field_validator("subdomain")
    @classmethod
    def validate_slug(cls, v: str) -> str:
        return _check_slug(v)

    @field_validator("repo_url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        return _check_url(v)


class AccuroUser(BaseModel):
    id:        str
    email:     str
    name:      str
    role:      str
    is_active: bool


class JWTClaims(BaseModel):
    sub:   str
    email: str
    name:  str
    role:  str
    exp:   int
    iat:   int
