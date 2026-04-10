# tests/test_docker_service.py
import pytest
from unittest.mock import MagicMock, patch
from docker.errors import NotFound, DockerException


def test_deploy_stops_existing_and_runs_new():
    from app.services.docker_service import deploy_container
    existing = MagicMock()
    client = MagicMock()
    client.containers.get.return_value = existing
    client.containers.run.return_value = MagicMock(id="new-container-id")

    with patch("app.services.docker_service.docker.from_env", return_value=client):
        cid = deploy_container("my-app", "/demos/my-app", 3001)

    existing.stop.assert_called_once()
    existing.remove.assert_called_once()
    client.containers.run.assert_called_once()
    assert cid == "new-container-id"


def test_deploy_skips_stop_when_no_existing():
    from app.services.docker_service import deploy_container
    client = MagicMock()
    client.containers.get.side_effect = NotFound("not found")
    client.containers.run.return_value = MagicMock(id="c2")

    with patch("app.services.docker_service.docker.from_env", return_value=client):
        cid = deploy_container("my-app", "/demos/my-app", 3001)

    assert cid == "c2"


def test_deploy_raises_docker_error_on_failure():
    from app.services.docker_service import deploy_container, DockerError
    client = MagicMock()
    client.containers.get.side_effect = NotFound("x")
    client.containers.run.side_effect = DockerException("boom")

    with patch("app.services.docker_service.docker.from_env", return_value=client):
        with pytest.raises(DockerError, match="Docker error"):
            deploy_container("my-app", "/demos/my-app", 3001)


def test_stop_removes_container():
    from app.services.docker_service import stop_container
    container = MagicMock()
    client = MagicMock()
    client.containers.get.return_value = container

    with patch("app.services.docker_service.docker.from_env", return_value=client):
        stop_container("my-app")

    container.stop.assert_called_once()
    container.remove.assert_called_once()


def test_stop_is_noop_when_not_found():
    from app.services.docker_service import stop_container
    client = MagicMock()
    client.containers.get.side_effect = NotFound("x")

    with patch("app.services.docker_service.docker.from_env", return_value=client):
        stop_container("my-app")  # should not raise


def test_container_status_running():
    from app.services.docker_service import container_status
    mock_container = MagicMock()
    mock_container.status = "running"
    with patch("app.services.docker_service.docker.from_env") as mock_docker:
        mock_docker.return_value.containers.get.return_value = mock_container
        assert container_status("myapp") == "running"


def test_container_status_stopped():
    from app.services.docker_service import container_status
    mock_container = MagicMock()
    mock_container.status = "exited"
    with patch("app.services.docker_service.docker.from_env") as mock_docker:
        mock_docker.return_value.containers.get.return_value = mock_container
        assert container_status("myapp") == "stopped"


def test_container_status_not_found():
    from app.services.docker_service import container_status
    with patch("app.services.docker_service.docker.from_env") as mock_docker:
        mock_docker.return_value.containers.get.side_effect = NotFound("myapp")
        assert container_status("myapp") == "stopped"
