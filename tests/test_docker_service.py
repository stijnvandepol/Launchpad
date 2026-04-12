# tests/test_docker_service.py
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
import subprocess


def test_run_streaming_yields_lines(tmp_path):
    from app.services.docker_service import _run_streaming
    lines = list(_run_streaming(["echo", "hello world"]))
    assert lines == ["hello world"]


def test_run_streaming_raises_docker_error_on_nonzero(tmp_path):
    from app.services.docker_service import _run_streaming, DockerError
    with pytest.raises(DockerError, match="failed"):
        list(_run_streaming(["false"]))  # 'false' exits with code 1


def test_validate_repo_accepts_dockerfile(tmp_path):
    from app.services.docker_service import validate_repo
    (tmp_path / "Dockerfile").write_text("FROM alpine")
    validate_repo(str(tmp_path))  # should not raise


def test_validate_repo_accepts_compose(tmp_path):
    from app.services.docker_service import validate_repo
    (tmp_path / "docker-compose.yml").write_text("services:\n  app:\n    image: alpine")
    validate_repo(str(tmp_path))  # should not raise


def test_validate_repo_raises_without_either(tmp_path):
    from app.services.docker_service import validate_repo, DockerError
    with pytest.raises(DockerError, match="No Dockerfile"):
        validate_repo(str(tmp_path))


def test_write_compose_override_creates_file(tmp_path):
    from app.services.docker_service import write_compose_override
    write_compose_override(str(tmp_path), port=9001)
    override = tmp_path / "docker-compose.override.yml"
    assert override.exists()
    content = override.read_text()
    assert "512m" in content
    assert "0.5" in content
    assert "9001:8080" in content
    assert "PORT: \"8080\"" in content


def test_write_compose_override_is_idempotent(tmp_path):
    from app.services.docker_service import write_compose_override
    write_compose_override(str(tmp_path), port=9001)
    write_compose_override(str(tmp_path), port=9001)
    content = (tmp_path / "docker-compose.override.yml").read_text()
    assert content.count("mem_limit") == 1


def test_strip_host_ports_removes_ports(tmp_path):
    from app.services.docker_service import strip_host_ports
    compose = tmp_path / "docker-compose.yml"
    compose.write_text(
        "services:\n  app:\n    image: myapp\n    ports:\n      - \"8080:8080\"\n"
    )
    strip_host_ports(str(tmp_path))
    assert "ports" not in compose.read_text()


def test_strip_host_ports_noop_without_ports(tmp_path):
    from app.services.docker_service import strip_host_ports
    compose = tmp_path / "docker-compose.yml"
    compose.write_text("services:\n  app:\n    image: myapp\n")
    strip_host_ports(str(tmp_path))
    assert "image: myapp" in compose.read_text()


def test_strip_host_ports_noop_without_compose(tmp_path):
    from app.services.docker_service import strip_host_ports
    strip_host_ports(str(tmp_path))  # should not raise


def test_deploy_project_calls_compose_up(tmp_path):
    from app.services.docker_service import deploy_project
    with patch("app.services.docker_service._run") as mock_run:
        with patch("app.services.docker_service.write_compose_override") as mock_override:
            deploy_project(str(tmp_path), port=3001)
    mock_override.assert_called_once_with(str(tmp_path), 3001)
    mock_run.assert_called_once_with(
        ["docker", "compose", "up", "-d", "--build"],
        cwd=str(tmp_path),
    )


def test_stop_project_calls_compose_down(tmp_path):
    from app.services.docker_service import stop_project
    with patch("app.services.docker_service._run") as mock_run:
        stop_project(str(tmp_path))
    mock_run.assert_called_once_with(
        ["docker", "compose", "down"], cwd=str(tmp_path), env=None,
    )


def test_project_status_running(tmp_path):
    from app.services.docker_service import project_status
    with patch("app.services.docker_service._run") as mock_run:
        mock_run.return_value = MagicMock(stdout="abc123\n")
        assert project_status(str(tmp_path)) == "running"


def test_project_status_stopped_no_containers(tmp_path):
    from app.services.docker_service import project_status
    with patch("app.services.docker_service._run") as mock_run:
        mock_run.return_value = MagicMock(stdout="")
        assert project_status(str(tmp_path)) == "stopped"


def test_project_status_stopped_nonexistent_path():
    from app.services.docker_service import project_status
    assert project_status("/nonexistent/path") == "stopped"
