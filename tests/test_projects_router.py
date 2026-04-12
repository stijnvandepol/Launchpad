# tests/test_projects_router.py
import time
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from app.config import Settings, get_settings
from app.dependencies import require_user
from app.models import JWTClaims, ProjectStatus

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
    return str(tmp_path)


def _create_project(client, subdomain="demo"):
    return client.post("/projects", json={
        "name": "Demo", "repo_url": "https://github.com/x/y",
        "subdomain": subdomain,
    }).json()


# ── LIST / CREATE / DELETE ────────────────────────────────────────────────────


def test_list_projects_empty(store_dir):
    client = TestClient(_app(store_dir))
    assert client.get("/projects").json() == []


def test_create_project(store_dir):
    client = TestClient(_app(store_dir))
    r = client.post("/projects", json={
        "name": "My-App", "repo_url": "https://github.com/x/y", "subdomain": "my-app",
    })
    assert r.status_code == 201
    assert r.json()["name"] == "My-App"
    assert r.json()["status"] == "pending"
    assert "id" in r.json()


def test_create_and_list(store_dir):
    client = TestClient(_app(store_dir))
    _create_project(client)
    assert len(client.get("/projects").json()) == 1


def test_delete_project(store_dir):
    client = TestClient(_app(store_dir))
    pid = _create_project(client)["id"]
    with patch("app.routers.projects.stop_project"), \
         patch("app.routers.projects.remove_ingress"):
        assert client.delete(f"/projects/{pid}").status_code == 204
    assert client.get("/projects").json() == []


def test_delete_nonexistent_returns_404(store_dir):
    client = TestClient(_app(store_dir), raise_server_exceptions=False)
    assert client.delete("/projects/no-such-id").status_code == 404


# ── CLONE ─────────────────────────────────────────────────────────────────────


def test_clone_starts_background_task(store_dir):
    client = TestClient(_app(store_dir))
    pid = _create_project(client)["id"]
    with patch("app.routers.projects._do_clone") as mock_clone:
        r = client.post(f"/projects/{pid}/clone")
    assert r.status_code == 200
    mock_clone.assert_called_once()


def test_clone_returns_cloning_status(store_dir):
    client = TestClient(_app(store_dir))
    pid = _create_project(client)["id"]
    with patch("app.routers.projects._do_clone"):
        r = client.post(f"/projects/{pid}/clone")
    assert r.json()["status"] == "cloning"


def test_clone_from_running_returns_409(store_dir):
    from app.services.project_store import update_project_status
    client = TestClient(_app(store_dir), raise_server_exceptions=False)
    p = _create_project(client, subdomain="demo2")
    update_project_status(store_dir + "/projects.db", p["id"], ProjectStatus.running)
    r = client.post(f"/projects/{p['id']}/clone")
    assert r.status_code == 409


# ── DEPLOY ────────────────────────────────────────────────────────────────────


def test_deploy_starts_background_task(store_dir):
    from app.services.project_store import update_project_status
    client = TestClient(_app(store_dir))
    p = _create_project(client)
    update_project_status(store_dir + "/projects.db", p["id"], ProjectStatus.cloned)
    with patch("app.routers.projects._do_deploy") as mock_deploy:
        r = client.post(f"/projects/{p['id']}/deploy")
    assert r.status_code == 200
    mock_deploy.assert_called_once()


def test_deploy_returns_building_status(store_dir):
    from app.services.project_store import update_project_status
    client = TestClient(_app(store_dir))
    p = _create_project(client)
    update_project_status(store_dir + "/projects.db", p["id"], ProjectStatus.cloned)
    with patch("app.routers.projects._do_deploy"):
        r = client.post(f"/projects/{p['id']}/deploy")
    assert r.json()["status"] == "building"


def test_deploy_from_pending_returns_409(store_dir):
    client = TestClient(_app(store_dir), raise_server_exceptions=False)
    p = _create_project(client)
    r = client.post(f"/projects/{p['id']}/deploy")
    assert r.status_code == 409


# ── STOP ──────────────────────────────────────────────────────────────────────


def test_stop_calls_compose_down(store_dir):
    client = TestClient(_app(store_dir))
    pid = _create_project(client)["id"]
    with patch("app.routers.projects.stop_project") as mock_stop, \
         patch("app.routers.projects.remove_ingress"):
        r = client.post(f"/projects/{pid}/stop")
    assert r.status_code == 200
    mock_stop.assert_called_once()
    assert r.json()["status"] == "stopped"


def test_stop_returns_502_on_error(store_dir):
    from app.services.docker_service import DockerError
    client = TestClient(_app(store_dir), raise_server_exceptions=False)
    pid = _create_project(client)["id"]
    with patch("app.routers.projects.stop_project", side_effect=DockerError("fail")):
        r = client.post(f"/projects/{pid}/stop")
    assert r.status_code == 502


# ── UPDATE ────────────────────────────────────────────────────────────────────


def test_update_success(store_dir):
    client = TestClient(_app(store_dir))
    pid = _create_project(client)["id"]
    with patch("app.routers.projects.pull_repo"), \
         patch("app.routers.projects.stop_project"), \
         patch("app.routers.projects.deploy_project"):
        r = client.post(f"/projects/{pid}/update")
    assert r.status_code == 200
    assert r.json()["updated_at"] is not None


def test_update_not_found(store_dir):
    client = TestClient(_app(store_dir), raise_server_exceptions=False)
    assert client.post("/projects/nonexistent/update").status_code == 404


def test_update_git_pull_fail(store_dir):
    from app.services.docker_service import DockerError
    client = TestClient(_app(store_dir), raise_server_exceptions=False)
    pid = _create_project(client)["id"]
    with patch("app.routers.projects.pull_repo", side_effect=DockerError("git pull failed")):
        r = client.post(f"/projects/{pid}/update")
    assert r.status_code == 502
    assert "git pull" in r.json()["detail"]


# ── STATUS ────────────────────────────────────────────────────────────────────


def test_list_includes_db_status(store_dir):
    client = TestClient(_app(store_dir))
    _create_project(client)
    resp = client.get("/projects")
    assert resp.json()[0]["status"] == "pending"


def test_list_detects_crashed_container(store_dir):
    from app.services.project_store import update_project_status
    client = TestClient(_app(store_dir))
    p = _create_project(client)
    update_project_status(store_dir + "/projects.db", p["id"], ProjectStatus.running)
    with patch("app.routers.projects.project_status", return_value="stopped"):
        resp = client.get("/projects")
    assert resp.json()[0]["status"] == "stopped"
