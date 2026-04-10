# tests/test_projects_router.py
import time
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import patch
from app.config import Settings, get_settings
from app.dependencies import require_user
from app.models import JWTClaims
from ruamel.yaml import YAML

SECRET = "a" * 32
FAKE_USER = JWTClaims(
    sub="u1", email="a@b.com", name="Admin", role="admin",
    exp=int(time.time()) + 3600, iat=int(time.time()),
)


def _app(tmp_dir: str, cf_config: str = None):
    from app.routers.projects import router
    app = FastAPI()
    app.include_router(router)

    def override_settings():
        return Settings(
            ACCURO_URL="http://x",
            LAUNCHPAD_JWT_SECRET=SECRET,
            TUNNEL_UUID="t",
            BASE_DIR=tmp_dir,
            CLOUDFLARED_CONFIG=cf_config or f"{tmp_dir}/config.yml",
        )

    app.dependency_overrides[get_settings] = override_settings
    app.dependency_overrides[require_user] = lambda: FAKE_USER
    return app


def _write_cf_config(path: str):
    yaml = YAML()
    from pathlib import Path
    yaml.dump({"tunnel": "t", "ingress": [{"service": "http_status:404"}]}, Path(path).open("w"))


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


def test_deploy_calls_docker_and_cloudflare(store_dir, tmp_path):
    cf = str(tmp_path / "config.yml")
    _write_cf_config(cf)
    client = TestClient(_app(store_dir, cf_config=cf))
    pid = client.post("/projects", json={
        "name": "demo", "repo_url": "https://github.com/x/y",
        "subdomain": "demo", "port": 3002,
    }).json()["id"]

    with patch("app.routers.projects.deploy_container", return_value="cid-1") as mock_deploy, \
         patch("app.routers.projects.add_ingress") as mock_cf:
        r = client.post(f"/projects/{pid}/deploy")

    assert r.status_code == 200
    mock_deploy.assert_called_once_with("demo", f"{store_dir}/demo", 3002)
    mock_cf.assert_called_once()
    assert r.json()["deployed_at"] is not None


def test_stop_calls_docker_and_removes_ingress(store_dir, tmp_path):
    cf = str(tmp_path / "config.yml")
    _write_cf_config(cf)
    client = TestClient(_app(store_dir, cf_config=cf))
    pid = client.post("/projects", json={
        "name": "demo", "repo_url": "https://github.com/x/y",
        "subdomain": "demo", "port": 3002,
    }).json()["id"]

    with patch("app.routers.projects.stop_container") as mock_stop, \
         patch("app.routers.projects.remove_ingress") as mock_cf:
        r = client.post(f"/projects/{pid}/stop")

    assert r.status_code == 200
    mock_stop.assert_called_once_with("demo")
    mock_cf.assert_called_once()
    assert r.json()["updated_at"] is not None


def test_deploy_returns_502_on_docker_error(store_dir):
    from app.services.docker_service import DockerError
    client = TestClient(_app(store_dir), raise_server_exceptions=False)
    pid = client.post("/projects", json={
        "name": "demo", "repo_url": "https://github.com/x/y",
        "subdomain": "demo", "port": 3002,
    }).json()["id"]

    with patch("app.routers.projects.deploy_container", side_effect=DockerError("fail")):
        r = client.post(f"/projects/{pid}/deploy")

    assert r.status_code == 502


def test_list_projects_includes_status(store_dir):
    client = TestClient(_app(store_dir))
    client.post("/projects", json={
        "name": "my-app", "repo_url": "https://github.com/x/y",
        "subdomain": "my-app", "port": 3001,
    })
    with patch("app.routers.projects.container_status", return_value="stopped"):
        resp = client.get("/projects")
    assert resp.status_code == 200
    data = resp.json()
    # every project must have a status field
    for project in data:
        assert "status" in project
        assert project["status"] in ("running", "stopped")


def test_list_projects_docker_unavailable(store_dir):
    from app.services.docker_service import DockerError
    client = TestClient(_app(store_dir))
    client.post("/projects", json={
        "name": "my-app", "repo_url": "https://github.com/x/y",
        "subdomain": "my-app", "port": 3001,
    })
    with patch("app.routers.projects.container_status", side_effect=DockerError("daemon down")):
        resp = client.get("/projects")
    assert resp.status_code == 200
    for project in resp.json():
        assert project["status"] == "stopped"


def test_update_project_success(store_dir, tmp_path):
    from unittest.mock import patch, MagicMock
    project_id = "test-update-id"
    client = TestClient(_app(store_dir))
    # First create a project
    pid = client.post("/projects", json={
        "name": "demo", "repo_url": "https://github.com/x/y",
        "subdomain": "demo", "port": 3000,
    }).json()["id"]

    with patch("app.routers.projects.get_project") as mock_get, \
         patch("app.routers.projects.subprocess") as mock_sub, \
         patch("app.routers.projects.stop_container"), \
         patch("app.routers.projects.deploy_container", return_value="abc123"), \
         patch("app.routers.projects.upsert_project"), \
         patch("app.routers.projects.container_status", return_value="running"):
        from app.models import Project
        mock_get.return_value = Project(
            id=pid, name="demo", repo_url="https://github.com/x/y",
            subdomain="demo", path=str(tmp_path), port=3000
        )
        mock_sub.run.return_value = MagicMock(returncode=0, stderr="")
        resp = client.post(f"/projects/{pid}/update")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "running"
    assert data["updated_at"] is not None


def test_update_project_not_found(store_dir):
    client = TestClient(_app(store_dir), raise_server_exceptions=False)
    with patch("app.routers.projects.get_project", return_value=None):
        resp = client.post("/projects/nonexistent/update")
    assert resp.status_code == 404


def test_update_project_git_fail(store_dir, tmp_path):
    from unittest.mock import patch, MagicMock
    project_id = "fail-id"
    client = TestClient(_app(store_dir), raise_server_exceptions=False)
    # First create a project
    pid = client.post("/projects", json={
        "name": "demo", "repo_url": "https://github.com/x/y",
        "subdomain": "demo", "port": 3000,
    }).json()["id"]

    with patch("app.routers.projects.get_project") as mock_get, \
         patch("app.routers.projects.subprocess") as mock_sub:
        from app.models import Project
        mock_get.return_value = Project(
            id=pid, name="demo", repo_url="https://github.com/x/y",
            subdomain="demo", path=str(tmp_path), port=3000
        )
        mock_sub.run.return_value = MagicMock(returncode=1, stderr="fatal: not a git repo")
        resp = client.post(f"/projects/{pid}/update")
    assert resp.status_code == 502
    assert "git pull" in resp.json()["detail"]
