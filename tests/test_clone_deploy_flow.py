# tests/test_clone_deploy_flow.py
import pytest
from pathlib import Path
from unittest.mock import patch


@pytest.fixture
def store(tmp_path):
    return str(tmp_path / "projects.db")


@pytest.fixture
def project(store):
    from app.models import Project
    from app.services.project_store import upsert_project
    p = Project(
        id="p1", name="demo", repo_url="https://github.com/x/y",
        subdomain="demo", path="/tmp/demo-test", port=8001,
    )
    upsert_project(store, p)
    return p


def test_do_clone_sets_cloned_status(store, project, tmp_path):
    from app.routers.projects import _do_clone
    from app.services.project_store import get_project
    from app.models import ProjectStatus

    repo_path = str(tmp_path / "repo")
    project_updated = project.model_copy(update={"path": repo_path})
    from app.services.project_store import upsert_project
    upsert_project(store, project_updated)

    with patch("app.routers.projects._run_streaming") as mock_stream, \
         patch("app.routers.projects.validate_repo"):
        mock_stream.return_value = iter(["Cloning...", "done"])
        _do_clone(project.id, project.repo_url, repo_path, store)

    p = get_project(store, project.id)
    assert p.status == ProjectStatus.cloned


def test_do_clone_sets_failed_on_docker_error(store, project, tmp_path):
    from app.routers.projects import _do_clone
    from app.services.project_store import get_project
    from app.services.docker_service import DockerError
    from app.models import ProjectStatus

    repo_path = str(tmp_path / "repo")
    project_updated = project.model_copy(update={"path": repo_path})
    from app.services.project_store import upsert_project
    upsert_project(store, project_updated)

    with patch("app.routers.projects._run_streaming", side_effect=DockerError("network error")):
        _do_clone(project.id, project.repo_url, repo_path, store)

    p = get_project(store, project.id)
    assert p.status == ProjectStatus.failed
    assert "network error" in p.error


def test_do_clone_sets_failed_when_no_dockerfile(store, project, tmp_path):
    from app.routers.projects import _do_clone
    from app.services.project_store import get_project
    from app.services.docker_service import DockerError
    from app.models import ProjectStatus

    repo_path = str(tmp_path / "repo")
    project_updated = project.model_copy(update={"path": repo_path})
    from app.services.project_store import upsert_project
    upsert_project(store, project_updated)

    with patch("app.routers.projects._run_streaming") as mock_stream, \
         patch("app.routers.projects.validate_repo", side_effect=DockerError("No Dockerfile")):
        mock_stream.return_value = iter([])
        _do_clone(project.id, project.repo_url, repo_path, store)

    p = get_project(store, project.id)
    assert p.status == ProjectStatus.failed


def test_do_deploy_sets_running_status(store, project, tmp_path):
    from app.routers.projects import _do_deploy
    from app.services.project_store import get_project
    from app.models import ProjectStatus
    from app.config import Settings

    settings = Settings(
        ACCURO_URL="http://x", LAUNCHPAD_JWT_SECRET="a" * 32, TUNNEL_UUID="t",
        CF_ACCOUNT_ID="fake-account", CF_API_TOKEN="fake-token",
        BASE_DIR=str(tmp_path),
    )

    with patch("app.routers.projects.write_compose_override"), \
         patch("app.routers.projects._run_streaming") as mock_stream, \
         patch("app.routers.projects.add_ingress"):
        mock_stream.return_value = iter(["Building...", "done"])
        _do_deploy(project.id, project.path, project.port, project.subdomain, store, settings)

    p = get_project(store, project.id)
    assert p.status == ProjectStatus.running


def test_do_deploy_sets_failed_on_docker_error(store, project, tmp_path):
    from app.routers.projects import _do_deploy
    from app.services.project_store import get_project
    from app.services.docker_service import DockerError
    from app.models import ProjectStatus
    from app.config import Settings

    settings = Settings(
        ACCURO_URL="http://x", LAUNCHPAD_JWT_SECRET="a" * 32, TUNNEL_UUID="t",
        CF_ACCOUNT_ID="fake-account", CF_API_TOKEN="fake-token",
        BASE_DIR=str(tmp_path),
    )

    with patch("app.routers.projects.write_compose_override"), \
         patch("app.routers.projects._run_streaming", side_effect=DockerError("build failed")):
        _do_deploy(project.id, project.path, project.port, project.subdomain, store, settings)

    p = get_project(store, project.id)
    assert p.status == ProjectStatus.failed
    assert "build failed" in p.error
