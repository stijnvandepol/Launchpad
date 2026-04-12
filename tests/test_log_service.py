import pytest


@pytest.fixture
def store(tmp_path):
    return str(tmp_path / "projects.db")


def test_append_and_get_logs(store):
    from app.services.log_service import append_log, get_logs
    append_log(store, "p1", "line one")
    append_log(store, "p1", "line two")
    logs = get_logs(store, "p1")
    assert len(logs) == 2
    assert logs[0].text == "line one"
    assert logs[1].text == "line two"


def test_get_logs_empty(store):
    from app.services.log_service import get_logs
    assert get_logs(store, "p1") == []


def test_get_logs_after(store):
    from app.services.log_service import append_log, get_logs, get_logs_after
    append_log(store, "p1", "a")
    append_log(store, "p1", "b")
    append_log(store, "p1", "c")
    all_logs = get_logs(store, "p1")
    after_first = get_logs_after(store, "p1", all_logs[0].id)
    assert len(after_first) == 2
    assert after_first[0].text == "b"


def test_logs_are_isolated_by_project(store):
    from app.services.log_service import append_log, get_logs
    append_log(store, "p1", "from p1")
    append_log(store, "p2", "from p2")
    assert len(get_logs(store, "p1")) == 1
    assert len(get_logs(store, "p2")) == 1


def test_logs_ordered_by_id(store):
    from app.services.log_service import append_log, get_logs
    for i in range(5):
        append_log(store, "p1", f"line {i}")
    logs = get_logs(store, "p1")
    ids = [l.id for l in logs]
    assert ids == sorted(ids)
