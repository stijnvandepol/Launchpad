# tests/test_projects_router.py
import time
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from app.config import Settings, get_settings
from app.dependencies import require_user
from app.models import JWTClaims, Project
from app.services.docker_service import DockerError

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


# --- LIST / CREATE / DELETE ---


def test_list_projects_empty(store_dir):
    client = TestClient(_app(store_dir))
    assert client.get("/projects").json() == []


def test_create_project(store_dir):
    client = TestClient(_app(store_dir))
    r = client.post("/projects", json={
        "name": "My App", "repo_url": "https://github.com/x/y",
        "subdomain": "my-app", "port": 3001,
    })
    assert r.status_code == 201
    assert r.json()["name"] == "My App"
    assert "id" in r.json()


def test_create_and_list(store_dir):
    client = TestClient(_app(store_dir))
    client.post("/projects", json={
        "name": "demo", "repo_url": "https://github.com/x/y",
        "subdomain": "demo", "port": 3002,
    })
    assert len(client.get("/projects").json()) == 1


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


# --- DEPLOY / STOP ---


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


def test_deploy_returns_502_on_docker_error(store_dir):
    client = TestClient(_app(store_dir), raise_server_exceptions=False)
    pid = client.post("/projects", json={
        "name": "demo", "repo_url": "https://github.com/x/y",
        "subdomain": "demo", "port": 3002,
    }).json()["id"]

    with patch("app.routers.projects.clone_repo"), \
         patch("app.routers.projects.deploy_project", side_effect=DockerError("fail")):
        r = client.post(f"/projects/{pid}/deploy")

    assert r.status_code == 502


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


# --- UPDATE ---


def test_update_success(store_dir, tmp_path):
    client = TestClient(_app(store_dir))
    pid = client.post("/projects", json={
        "name": "demo", "repo_url": "https://github.com/x/y",
        "subdomain": "demo", "port": 3000,
    }).json()["id"]

    with patch("app.routers.projects.pull_repo"), \
         patch("app.routers.projects.stop_project"), \
         patch("app.routers.projects.deploy_project"):
        resp = client.post(f"/projects/{pid}/update")

    assert resp.status_code == 200
    assert resp.json()["updated_at"] is not None


def test_update_not_found(store_dir):
    client = TestClient(_app(store_dir), raise_server_exceptions=False)
    assert client.post("/projects/nonexistent/update").status_code == 404


def test_update_git_pull_fail(store_dir):
    client = TestClient(_app(store_dir), raise_server_exceptions=False)
    pid = client.post("/projects", json={
        "name": "demo", "repo_url": "https://github.com/x/y",
        "subdomain": "demo", "port": 3000,
    }).json()["id"]

    with patch("app.routers.projects.pull_repo", side_effect=DockerError("git pull failed")):
        resp = client.post(f"/projects/{pid}/update")

    assert resp.status_code == 502
    assert "git pull" in resp.json()["detail"]


def test_update_docker_fail(store_dir):
    client = TestClient(_app(store_dir), raise_server_exceptions=False)
    pid = client.post("/projects", json={
        "name": "demo", "repo_url": "https://github.com/x/y",
        "subdomain": "demo", "port": 3000,
    }).json()["id"]

    with patch("app.routers.projects.pull_repo"), \
         patch("app.routers.projects.stop_project", side_effect=DockerError("daemon down")):
        resp = client.post(f"/projects/{pid}/update")

    assert resp.status_code == 502
    assert "daemon down" in resp.json()["detail"]


# --- STATUS ---


def test_list_includes_status(store_dir):
    client = TestClient(_app(store_dir))
    client.post("/projects", json={
        "name": "my-app", "repo_url": "https://github.com/x/y",
        "subdomain": "my-app", "port": 3001,
    })
    with patch("app.routers.projects.project_status", return_value="stopped"):
        resp = client.get("/projects")
    for project in resp.json():
        assert project["status"] in ("running", "stopped")


def test_list_docker_unavailable(store_dir):
    client = TestClient(_app(store_dir))
    client.post("/projects", json={
        "name": "my-app", "repo_url": "https://github.com/x/y",
        "subdomain": "my-app", "port": 3001,
    })
    with patch("app.routers.projects.project_status", side_effect=DockerError("daemon down")):
        resp = client.get("/projects")
    for project in resp.json():
        assert project["status"] == "stopped"
