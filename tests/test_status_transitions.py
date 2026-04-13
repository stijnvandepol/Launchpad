# tests/test_status_transitions.py
import time
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
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
            ACCURO_URL="http://x", LAUNCHPAD_JWT_SECRET=SECRET, TUNNEL_UUID="t",
            CF_ACCOUNT_ID="fake-account", CF_API_TOKEN="fake-token",
            BASE_DIR=tmp_dir,
        )

    app.dependency_overrides[get_settings] = override_settings
    app.dependency_overrides[require_user] = lambda: FAKE_USER
    return app


@pytest.fixture
def store_dir(tmp_path):
    return str(tmp_path)


def _create_and_set_status(client, store_dir, status: ProjectStatus, subdomain="demo"):
    from app.services.project_store import update_project_status
    p = client.post("/projects", json={
        "name": "Demo", "repo_url": "https://github.com/x/y", "subdomain": subdomain,
    }).json()
    db_path = store_dir + "/projects.db"
    update_project_status(db_path, p["id"], status)
    return p["id"]


def test_cannot_clone_from_cloning(store_dir):
    client = TestClient(_app(store_dir), raise_server_exceptions=False)
    pid = _create_and_set_status(client, store_dir, ProjectStatus.cloning)
    r = client.post(f"/projects/{pid}/clone")
    assert r.status_code == 409


def test_cannot_clone_from_running(store_dir):
    client = TestClient(_app(store_dir), raise_server_exceptions=False)
    pid = _create_and_set_status(client, store_dir, ProjectStatus.running, subdomain="d2")
    r = client.post(f"/projects/{pid}/clone")
    assert r.status_code == 409


def test_cannot_deploy_from_pending(store_dir):
    client = TestClient(_app(store_dir), raise_server_exceptions=False)
    pid = _create_and_set_status(client, store_dir, ProjectStatus.pending, subdomain="d3")
    r = client.post(f"/projects/{pid}/deploy")
    assert r.status_code == 409


def test_cannot_deploy_from_cloning(store_dir):
    client = TestClient(_app(store_dir), raise_server_exceptions=False)
    pid = _create_and_set_status(client, store_dir, ProjectStatus.cloning, subdomain="d4")
    r = client.post(f"/projects/{pid}/deploy")
    assert r.status_code == 409


def test_can_deploy_from_cloned(store_dir):
    from unittest.mock import patch
    client = TestClient(_app(store_dir))
    pid = _create_and_set_status(client, store_dir, ProjectStatus.cloned, subdomain="d5")
    with patch("app.routers.projects._do_deploy"):
        r = client.post(f"/projects/{pid}/deploy")
    assert r.status_code == 200


def test_can_deploy_from_failed(store_dir):
    from unittest.mock import patch
    client = TestClient(_app(store_dir))
    pid = _create_and_set_status(client, store_dir, ProjectStatus.failed, subdomain="d6")
    with patch("app.routers.projects._do_deploy"):
        r = client.post(f"/projects/{pid}/deploy")
    assert r.status_code == 200


def test_can_clone_from_failed(store_dir):
    from unittest.mock import patch
    client = TestClient(_app(store_dir))
    pid = _create_and_set_status(client, store_dir, ProjectStatus.failed, subdomain="d7")
    with patch("app.routers.projects._do_clone"):
        r = client.post(f"/projects/{pid}/clone")
    assert r.status_code == 200
