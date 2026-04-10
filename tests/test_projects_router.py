# tests/test_projects_router.py
import time
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from app.config import Settings, get_settings
from app.dependencies import require_user
from app.models import JWTClaims, Project

SECRET = "a" * 32
FAKE_USER = JWTClaims(
    sub="u1", email="a@b.com", name="Admin", role="admin",
    exp=int(time.time()) + 3600, iat=int(time.time()),
)


def _app(tmp_dir: str):
    from app.routers.projects import router
    app = FastAPI()
    app.include_router(router)

    def override_settings():
        return Settings(
            ACCURO_URL="http://x",
            LAUNCHPAD_JWT_SECRET=SECRET,
            TUNNEL_UUID="t",
            BASE_DIR=tmp_dir,
        )

    app.dependency_overrides[get_settings] = override_settings
    app.dependency_overrides[require_user] = lambda: FAKE_USER
    return app


@pytest.fixture
def store_dir(tmp_path):
    (tmp_path / "projects.json").write_text("[]")
    return str(tmp_path)


def test_list_projects_empty(store_dir):
    client = TestClient(_app(store_dir))
    r = client.get("/projects")
    assert r.status_code == 200
    assert r.json() == []


def test_create_project(store_dir):
    client = TestClient(_app(store_dir))
    r = client.post("/projects", json={
        "name": "my-app", "repo_url": "https://github.com/x/y",
        "subdomain": "my-app", "port": 3001,
    })
    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "my-app"
    assert "id" in body


def test_create_and_list(store_dir):
    client = TestClient(_app(store_dir))
    client.post("/projects", json={
        "name": "demo", "repo_url": "https://github.com/x/y",
        "subdomain": "demo", "port": 3002,
    })
    r = client.get("/projects")
    assert len(r.json()) == 1


def test_delete_project(store_dir):
    client = TestClient(_app(store_dir))
    pid = client.post("/projects", json={
        "name": "demo", "repo_url": "https://github.com/x/y",
        "subdomain": "demo", "port": 3002,
    }).json()["id"]
    assert client.delete(f"/projects/{pid}").status_code == 204
    assert client.get("/projects").json() == []


def test_delete_nonexistent_returns_404(store_dir):
    client = TestClient(_app(store_dir), raise_server_exceptions=False)
    assert client.delete("/projects/no-such-id").status_code == 404


def test_deploy_clones_and_runs_compose(store_dir):
    client = TestClient(_app(store_dir))
    pid = client.post("/projects", json={
        "name": "demo", "repo_url": "https://github.com/x/y",
        "subdomain": "demo", "port": 3002,
    }).json()["id"]

    with patch("app.routers.projects.clone_repo") as mock_clone, \
         patch("app.routers.projects.deploy_project") as mock_deploy:
        r = client.post(f"/projects/{pid}/deploy")

    assert r.status_code == 200
    mock_clone.assert_called_once()
    mock_deploy.assert_called_once()
    assert r.json()["deployed_at"] is not None


def test_stop_calls_compose_down(store_dir):
    client = TestClient(_app(store_dir))
    pid = client.post("/projects", json={
        "name": "demo", "repo_url": "https://github.com/x/y",
        "subdomain": "demo", "port": 3002,
    }).json()["id"]

    with patch("app.routers.projects.stop_project") as mock_stop:
        r = client.post(f"/projects/{pid}/stop")

    assert r.status_code == 200
    mock_stop.assert_called_once()
    assert r.json()["updated_at"] is not None


def test_deploy_returns_502_on_docker_error(store_dir):
    from app.services.docker_service import DockerError
    client = TestClient(_app(store_dir), raise_server_exceptions=False)
    pid = client.post("/projects", json={
        "name": "demo", "repo_url": "https://github.com/x/y",
        "subdomain": "demo", "port": 3002,
    }).json()["id"]

    with patch("app.routers.projects.clone_repo"), \
         patch("app.routers.projects.deploy_project", side_effect=DockerError("fail")):
        r = client.post(f"/projects/{pid}/deploy")

    assert r.status_code == 502


def test_list_projects_includes_status(store_dir):
    client = TestClient(_app(store_dir))
    client.post("/projects", json={
        "name": "my-app", "repo_url": "https://github.com/x/y",
        "subdomain": "my-app", "port": 3001,
    })
    with patch("app.routers.projects.project_status", return_value="stopped"):
        resp = client.get("/projects")
    assert resp.status_code == 200
    for project in resp.json():
        assert "status" in project
        assert project["status"] in ("running", "stopped")


def test_list_projects_docker_unavailable(store_dir):
    from app.services.docker_service import DockerError
    client = TestClient(_app(store_dir))
    client.post("/projects", json={
        "name": "my-app", "repo_url": "https://github.com/x/y",
        "subdomain": "my-app", "port": 3001,
    })
    with patch("app.routers.projects.project_status", side_effect=DockerError("daemon down")):
        resp = client.get("/projects")
    assert resp.status_code == 200
    for project in resp.json():
        assert project["status"] == "stopped"


def test_update_project_success(store_dir, tmp_path):
    client = TestClient(_app(store_dir))
    pid = client.post("/projects", json={
        "name": "demo", "repo_url": "https://github.com/x/y",
        "subdomain": "demo", "port": 3000,
    }).json()["id"]

    with patch("app.routers.projects.get_project") as mock_get, \
         patch("app.routers.projects.subprocess") as mock_sub, \
         patch("app.routers.projects.stop_project"), \
         patch("app.routers.projects.deploy_project"), \
         patch("app.routers.projects.upsert_project"), \
         patch("app.routers.projects.project_status", return_value="running"):
        mock_get.return_value = Project(
            id=pid, name="demo", repo_url="https://github.com/x/y",
            subdomain="demo", path=str(tmp_path), port=3000
        )
        mock_sub.run.return_value = MagicMock(returncode=0, stderr="")
        mock_sub.TimeoutExpired = TimeoutError
        resp = client.post(f"/projects/{pid}/update")
    assert resp.status_code == 200
    assert resp.json()["updated_at"] is not None


def test_update_project_not_found(store_dir):
    client = TestClient(_app(store_dir), raise_server_exceptions=False)
    with patch("app.routers.projects.get_project", return_value=None):
        resp = client.post("/projects/nonexistent/update")
    assert resp.status_code == 404


def test_update_project_git_fail(store_dir, tmp_path):
    client = TestClient(_app(store_dir), raise_server_exceptions=False)
    pid = client.post("/projects", json={
        "name": "demo", "repo_url": "https://github.com/x/y",
        "subdomain": "demo", "port": 3000,
    }).json()["id"]

    with patch("app.routers.projects.get_project") as mock_get, \
         patch("app.routers.projects.subprocess") as mock_sub:
        mock_get.return_value = Project(
            id=pid, name="demo", repo_url="https://github.com/x/y",
            subdomain="demo", path=str(tmp_path), port=3000
        )
        mock_sub.run.return_value = MagicMock(returncode=1, stderr="fatal: not a git repo")
        mock_sub.TimeoutExpired = TimeoutError
        resp = client.post(f"/projects/{pid}/update")
    assert resp.status_code == 502
    assert "git pull" in resp.json()["detail"]


def test_update_project_docker_fail(store_dir, tmp_path):
    from app.services.docker_service import DockerError
    client = TestClient(_app(store_dir), raise_server_exceptions=False)

    with patch("app.routers.projects.get_project") as mock_get, \
         patch("app.routers.projects.subprocess") as mock_sub, \
         patch("app.routers.projects.stop_project", side_effect=DockerError("daemon down")):
        mock_get.return_value = Project(
            id="test-id", name="demo", repo_url="https://github.com/x/y",
            subdomain="demo", path=str(tmp_path), port=3000
        )
        mock_sub.run.return_value = MagicMock(returncode=0, stderr="")
        mock_sub.TimeoutExpired = TimeoutError
        resp = client.post("/projects/test-id/update")
    assert resp.status_code == 502
    assert "daemon down" in resp.json()["detail"]
