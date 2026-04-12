import pytest
from datetime import datetime, timezone


@pytest.fixture
def store(tmp_path):
    return str(tmp_path / "projects.db")


def _make_project(**kwargs):
    from app.models import Project
    defaults = dict(
        id="p1", name="demo", repo_url="https://github.com/x/y",
        subdomain="demo", path="/demos/demo", port=3001,
    )
    defaults.update(kwargs)
    return Project(**defaults)


def test_load_empty(store):
    from app.services.project_store import load_projects
    assert load_projects(store) == []


def test_upsert_and_load(store):
    from app.services.project_store import upsert_project, load_projects
    p = _make_project()
    upsert_project(store, p)
    loaded = load_projects(store)
    assert len(loaded) == 1
    assert loaded[0].name == "demo"


def test_upsert_updates_existing(store):
    from app.services.project_store import upsert_project, get_project
    p = _make_project()
    upsert_project(store, p)
    p2 = p.model_copy(update={"name": "updated"})
    upsert_project(store, p2)
    loaded = get_project(store, "p1")
    assert loaded.name == "updated"


def test_get_project_not_found(store):
    from app.services.project_store import get_project
    assert get_project(store, "nonexistent") is None


def test_delete_project(store):
    from app.services.project_store import upsert_project, delete_project, load_projects
    upsert_project(store, _make_project())
    delete_project(store, "p1")
    assert load_projects(store) == []


def test_update_project_status(store):
    from app.services.project_store import upsert_project, update_project_status, get_project
    from app.models import ProjectStatus
    upsert_project(store, _make_project())
    update_project_status(store, "p1", ProjectStatus.running)
    p = get_project(store, "p1")
    assert p.status == ProjectStatus.running
    assert p.error is None


def test_update_project_status_with_error(store):
    from app.services.project_store import upsert_project, update_project_status, get_project
    from app.models import ProjectStatus
    upsert_project(store, _make_project())
    update_project_status(store, "p1", ProjectStatus.failed, error="build blew up")
    p = get_project(store, "p1")
    assert p.status == ProjectStatus.failed
    assert p.error == "build blew up"


def test_next_port_starts_at_8001(store):
    from app.services.project_store import next_port
    assert next_port(store) == 8001


def test_next_port_skips_used(store):
    from app.services.project_store import upsert_project, next_port
    upsert_project(store, _make_project(port=8001))
    upsert_project(store, _make_project(id="p2", subdomain="demo2", port=8002))
    assert next_port(store) == 8003
