import json
import pytest
from pathlib import Path


@pytest.fixture
def store_path(tmp_path):
    p = tmp_path / "projects.json"
    p.write_text("[]")
    return str(p)


def test_load_empty(store_path):
    from app.services.project_store import load_projects
    assert load_projects(store_path) == []


def test_save_and_load(store_path):
    from app.services.project_store import save_projects, load_projects
    from app.models import Project
    project = Project(
        id="1", name="demo", repo_url="https://github.com/x/y",
        subdomain="demo", path="/demos/demo", port=3001,
    )
    save_projects(store_path, [project])
    loaded = load_projects(store_path)
    assert len(loaded) == 1
    assert loaded[0].name == "demo"


def test_save_is_atomic(store_path, monkeypatch):
    from app.services.project_store import save_projects
    from app.models import Project
    import os

    original_replace = os.replace
    calls = []

    def patched_replace(src, dst):
        calls.append((src, dst))
        original_replace(src, dst)

    monkeypatch.setattr(os, "replace", patched_replace)

    project = Project(
        id="1", name="demo", repo_url="https://github.com/x/y",
        subdomain="demo", path="/demos/demo", port=3001,
    )
    save_projects(store_path, [project])
    assert len(calls) == 1
