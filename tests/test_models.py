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


def test_project_status_values():
    from app.models import ProjectStatus
    assert set(ProjectStatus) == {
        ProjectStatus.pending, ProjectStatus.cloning, ProjectStatus.cloned,
        ProjectStatus.building, ProjectStatus.running,
        ProjectStatus.failed, ProjectStatus.stopped,
    }

def test_project_has_status_and_error_fields():
    from app.models import Project
    p = Project(
        id="1", name="demo", repo_url="https://github.com/x/y",
        subdomain="demo", path="/demos/demo", port=3001,
    )
    assert p.status == "pending"
    assert p.error is None

def test_logline_has_required_fields():
    from app.models import LogLine
    from datetime import datetime, timezone
    ll = LogLine(project_id="abc", ts=datetime.now(timezone.utc), text="hello")
    assert ll.text == "hello"
    assert ll.project_id == "abc"
