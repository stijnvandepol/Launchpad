import pytest
from datetime import datetime, timezone


def test_project_name_valid():
    from app.models import Project
    p = Project(
        id="abc", name="my-project", repo_url="https://github.com/org/repo",
        subdomain="my-project", path="/demos/my-project", port=3001,
    )
    assert p.name == "my-project"


def test_project_name_invalid():
    from app.models import Project
    from pydantic import ValidationError
    with pytest.raises(ValidationError, match="name"):
        Project(
            id="abc", name="My Project!", repo_url="https://github.com/org/repo",
            subdomain="my-project", path="/demos/my-project", port=3001,
        )


def test_project_port_range():
    from app.models import Project
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        Project(
            id="abc", name="ok", repo_url="https://github.com/org/repo",
            subdomain="ok", path="/demos/ok", port=99999,
        )


def test_repo_url_must_be_https():
    from app.models import Project
    from pydantic import ValidationError
    with pytest.raises(ValidationError, match="repo_url"):
        Project(
            id="abc", name="ok", repo_url="ftp://evil.com/repo",
            subdomain="ok", path="/demos/ok", port=3001,
        )
