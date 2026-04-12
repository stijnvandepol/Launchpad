# tests/test_sse_logs.py
import asyncio
import pytest


@pytest.fixture
def store(tmp_path):
    return str(tmp_path / "projects.db")


@pytest.fixture
def project(store):
    from app.models import Project, ProjectStatus
    from app.services.project_store import upsert_project
    p = Project(
        id="p1", name="demo", repo_url="https://github.com/x/y",
        subdomain="demo", path="/tmp/demo", port=8001,
        status=ProjectStatus.building,
    )
    upsert_project(store, p)
    return p


def test_event_generator_replays_existing_logs(store, project):
    from app.services.log_service import append_log
    from app.services.project_store import update_project_status
    from app.models import ProjectStatus
    from app.services.log_service import get_logs, get_logs_after
    from app.services.project_store import get_project

    append_log(store, project.id, "line 1")
    append_log(store, project.id, "line 2")
    update_project_status(store, project.id, ProjectStatus.running)

    async def collect_events():
        events = []
        existing = get_logs(store, project.id)
        last_id = 0
        for log in existing:
            events.append(log.text)
            last_id = log.id

        terminal = {ProjectStatus.running, ProjectStatus.failed, ProjectStatus.stopped}
        while True:
            await asyncio.sleep(0)
            p = get_project(store, project.id)
            new_lines = get_logs_after(store, project.id, last_id)
            for log in new_lines:
                events.append(log.text)
                last_id = log.id
            if p is None or p.status in terminal:
                break
        return events

    events = asyncio.get_event_loop().run_until_complete(collect_events())
    assert "line 1" in events
    assert "line 2" in events


def test_event_generator_closes_on_failed_status(store, project):
    from app.services.log_service import append_log
    from app.services.project_store import update_project_status, get_project
    from app.services.log_service import get_logs, get_logs_after
    from app.models import ProjectStatus

    append_log(store, project.id, "error occurred")
    update_project_status(store, project.id, ProjectStatus.failed, "build blew up")

    async def collect_events():
        events = []
        existing = get_logs(store, project.id)
        last_id = 0
        for log in existing:
            events.append(log.text)
            last_id = log.id

        terminal = {ProjectStatus.running, ProjectStatus.failed, ProjectStatus.stopped}
        iterations = 0
        while True:
            await asyncio.sleep(0)
            p = get_project(store, project.id)
            if p is None or p.status in terminal:
                break
            iterations += 1
            assert iterations < 10, "Generator did not terminate"
        return events

    events = asyncio.get_event_loop().run_until_complete(collect_events())
    assert "error occurred" in events
