# PaaS Demo Platform Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend Launchpad from a synchronous clone+deploy tool into a full async PaaS with two-step Clone→Deploy flow, live log streaming via SSE, granular project status, and Docker resource limits.

**Architecture:** FastAPI BackgroundTasks handle async clone/deploy operations; status and logs are stored in SQLite (SQLModel); a new SSE endpoint streams `LogLine` rows to the frontend; the Vue 3 dashboard is extended with `StatusBadge`, `LogDrawer`, and polling.

**Tech Stack:** Python 3.12, FastAPI, SQLModel (SQLite), sse-starlette, Vue 3, TypeScript, PrimeVue, Tailwind

---

## Baseline

Before starting: 41 tests pass, 10 fail (8 stale docker-SDK tests, 1 model validation bug, 1 router bug). This plan fixes all 10 as part of the implementation.

---

## File Map

**New files:**
- `app/db.py` — lazy SQLite engine factory (WAL mode, create_all)
- `app/services/log_service.py` — `append_log`, `get_logs`, `get_logs_after`
- `frontend/src/components/StatusBadge.vue` — extracted reusable status badge
- `frontend/src/components/LogDrawer.vue` — slide-over log panel
- `frontend/src/composables/useProjectLogs.ts` — SSE composable

**Rewritten files:**
- `app/models.py` — add `ProjectStatus` enum, update `Project` to SQLModel, add `LogLine`
- `app/services/project_store.py` — SQLite backend (same external interface + `update_project_status`)
- `app/services/docker_service.py` — add `_run_streaming`, `validate_repo`, `write_compose_override`; fix stale tests
- `app/dependencies.py` — add `require_user_sse` (accepts token query param for EventSource)

**Modified files:**
- `requirements.txt` — add `sqlmodel`, `sse-starlette`
- `app/routers/projects.py` — split deploy→clone+deploy, make both async, add restart+logs endpoints
- `app/main.py` — startup event to init DB
- `tests/test_docker_service.py` — rewrite for subprocess-based implementation
- `tests/test_project_store.py` — rewrite for SQLite interface
- `tests/test_projects_router.py` — update for async flow, fix `store_dir` fixture
- `frontend/src/api/projects.ts` — add `clone`, `restart`, `logs` endpoints
- `frontend/src/views/Dashboard.vue` — new status badges, action buttons, polling, log drawer, info block

**New test files:**
- `tests/test_log_service.py`
- `tests/test_clone_validation.py`
- `tests/test_clone_deploy_flow.py`
- `tests/test_status_transitions.py`
- `tests/test_sse_logs.py`

---

## Task 1: Add Python dependencies

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Add sqlmodel and sse-starlette to requirements.txt**

```
# Runtime
fastapi==0.115.5
uvicorn[standard]==0.32.1
python-multipart==0.0.12
jinja2==3.1.4
python-jose[cryptography]==3.3.0
slowapi==0.1.9
httpx==0.28.1
ruamel.yaml==0.18.6
pydantic-settings==2.6.1
sqlmodel==0.0.22
sse-starlette==2.1.3

# Testing
pytest==8.3.4
pytest-asyncio==0.24.0
respx==0.23.1
```

- [ ] **Step 2: Install dependencies**

```bash
pip install sqlmodel==0.0.22 sse-starlette==2.1.3
```

Expected: both packages install without errors.

- [ ] **Step 3: Commit**

```bash
git add requirements.txt
git commit -m "chore: add sqlmodel and sse-starlette dependencies"
```

---

## Task 2: Update models.py

**Files:**
- Modify: `app/models.py`

- [ ] **Step 1: Write failing test for new ProjectStatus enum**

Add to `tests/test_models.py` (append after existing tests):

```python
def test_project_status_values():
    from app.models import ProjectStatus
    assert set(ProjectStatus) == {
        ProjectStatus.pending, ProjectStatus.cloning, ProjectStatus.cloned,
        ProjectStatus.building, ProjectStatus.running,
        ProjectStatus.failed, ProjectStatus.stopped,
    }

def test_project_has_status_and_error_fields():
    from app.models import Project
    p = Project(
        id="1", name="demo", repo_url="https://github.com/x/y",
        subdomain="demo", path="/demos/demo", port=3001,
    )
    assert p.status == "pending"
    assert p.error is None

def test_logline_has_required_fields():
    from app.models import LogLine
    from datetime import datetime, timezone
    ll = LogLine(project_id="abc", ts=datetime.now(timezone.utc), text="hello")
    assert ll.text == "hello"
    assert ll.project_id == "abc"
```

- [ ] **Step 2: Run test to confirm failure**

```bash
python3 -m pytest tests/test_models.py::test_project_status_values -v
```

Expected: `ImportError: cannot import name 'ProjectStatus'`

- [ ] **Step 3: Rewrite app/models.py**

```python
import re
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from pydantic import BaseModel, field_validator, Field
from sqlmodel import SQLModel, Field as SQLField


# Subdomain: lowercase alphanumeric + hyphens, 1-48 chars
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,46}[a-z0-9]$|^[a-z0-9]$")
# Repo URL: must be https, no shell metacharacters
_SAFE_URL_RE = re.compile(r"^https://[^\s;&|`$<>]+$")


def _check_slug(v: str) -> str:
    if not _SLUG_RE.match(v):
        raise ValueError("subdomain must be lowercase alphanumeric with hyphens, max 48 chars")
    return v


def _check_url(v: str) -> str:
    if not _SAFE_URL_RE.match(v):
        raise ValueError("repo_url must be a safe https:// URL")
    return v


class ProjectStatus(str, Enum):
    pending  = "pending"
    cloning  = "cloning"
    cloned   = "cloned"
    building = "building"
    running  = "running"
    failed   = "failed"
    stopped  = "stopped"


class Project(SQLModel, table=True):
    id:          str            = SQLField(primary_key=True)
    name:        str
    repo_url:    str
    subdomain:   str            = SQLField(unique=True, index=True)
    path:        str
    port:        int            = SQLField(ge=1, le=65535)
    status:      ProjectStatus  = SQLField(default=ProjectStatus.pending)
    error:       Optional[str]  = SQLField(default=None)
    deployed_at: Optional[datetime] = SQLField(default=None)
    updated_at:  Optional[datetime] = SQLField(default=None)

    model_config = {"arbitrary_types_allowed": True}


class LogLine(SQLModel, table=True):
    id:         Optional[int] = SQLField(default=None, primary_key=True)
    project_id: str           = SQLField(index=True)
    ts:         datetime      = SQLField(default_factory=lambda: datetime.now(timezone.utc))
    text:       str


class ProjectResponse(BaseModel):
    id:          str
    name:        str
    repo_url:    str
    subdomain:   str
    path:        str
    port:        int
    status:      str
    error:       Optional[str] = None
    deployed_at: Optional[datetime] = None
    updated_at:  Optional[datetime] = None


class DeployRequest(BaseModel):
    name:      str
    repo_url:  str
    subdomain: str

    @field_validator("subdomain")
    @classmethod
    def validate_slug(cls, v: str) -> str:
        return _check_slug(v)

    @field_validator("repo_url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        return _check_url(v)


class AccuroUser(BaseModel):
    id:        str
    email:     str
    name:      str
    role:      str
    is_active: bool


class JWTClaims(BaseModel):
    sub:   str
    email: str
    name:  str
    role:  str
    exp:   int
    iat:   int
```

- [ ] **Step 4: Run tests**

```bash
python3 -m pytest tests/test_models.py -v
```

Expected: all model tests pass (including the previously failing `test_project_name_invalid` — check if it now passes; if not, inspect what it tests and fix accordingly).

- [ ] **Step 5: Commit**

```bash
git add app/models.py tests/test_models.py
git commit -m "feat: add ProjectStatus enum, LogLine model, update Project to SQLModel"
```

---

## Task 3: Add app/db.py — SQLite engine factory

**Files:**
- Create: `app/db.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_db.py`:

```python
def test_get_engine_creates_db_file(tmp_path):
    from app.db import get_engine
    db_path = str(tmp_path / "test.db")
    engine = get_engine(db_path)
    assert engine is not None
    # Second call returns same engine (cached)
    assert get_engine(db_path) is get_engine(db_path)

def test_get_engine_enables_wal_mode(tmp_path):
    from app.db import get_engine
    from sqlalchemy import text
    db_path = str(tmp_path / "test.db")
    engine = get_engine(db_path)
    with engine.connect() as conn:
        result = conn.execute(text("PRAGMA journal_mode")).scalar()
    assert result == "wal"

def test_tables_are_created(tmp_path):
    from app.db import get_engine
    from sqlalchemy import inspect
    db_path = str(tmp_path / "test.db")
    engine = get_engine(db_path)
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    assert "project" in tables
    assert "logline" in tables
```

- [ ] **Step 2: Run tests to confirm failure**

```bash
python3 -m pytest tests/test_db.py -v
```

Expected: `ImportError: cannot import name 'get_engine' from 'app.db'`

- [ ] **Step 3: Create app/db.py**

```python
# app/db.py
from sqlalchemy import text
from sqlmodel import SQLModel, create_engine, Session

# Cache engines by path so each DB file gets exactly one engine
_engines: dict[str, object] = {}


def get_engine(path: str):
    """Return (and cache) the SQLAlchemy engine for the given SQLite path.

    Creates tables and enables WAL mode on first call per path.
    """
    if path in _engines:
        return _engines[path]

    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})

    with engine.connect() as conn:
        conn.execute(text("PRAGMA journal_mode=WAL"))
        conn.commit()

    SQLModel.metadata.create_all(engine)
    _engines[path] = engine
    return engine


def get_session(path: str) -> Session:
    """Return a new SQLModel session for the given DB path."""
    return Session(get_engine(path))
```

- [ ] **Step 4: Run tests**

```bash
python3 -m pytest tests/test_db.py -v
```

Expected: all 3 pass.

- [ ] **Step 5: Commit**

```bash
git add app/db.py tests/test_db.py
git commit -m "feat: add SQLite engine factory with WAL mode"
```

---

## Task 4: Rewrite project_store.py with SQLite backend

**Files:**
- Modify: `app/services/project_store.py`
- Modify: `tests/test_project_store.py`

- [ ] **Step 1: Rewrite tests/test_project_store.py**

```python
import pytest
from datetime import datetime, timezone


@pytest.fixture
def store(tmp_path):
    """Return path to a fresh SQLite DB."""
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
```

- [ ] **Step 2: Run tests to confirm failure**

```bash
python3 -m pytest tests/test_project_store.py -v
```

Expected: all 9 tests fail with ImportError on `update_project_status` and `next_port`.

- [ ] **Step 3: Rewrite app/services/project_store.py**

```python
# app/services/project_store.py
from datetime import datetime, timezone
from typing import Optional
from sqlmodel import select
from app.db import get_session
from app.models import Project, ProjectStatus

_PORT_START = 8001


def load_projects(path: str) -> list[Project]:
    with get_session(path) as session:
        return list(session.exec(select(Project)).all())


def get_project(path: str, project_id: str) -> Optional[Project]:
    with get_session(path) as session:
        return session.get(Project, project_id)


def upsert_project(path: str, project: Project) -> None:
    with get_session(path) as session:
        existing = session.get(Project, project.id)
        if existing:
            for key, val in project.model_dump().items():
                setattr(existing, key, val)
        else:
            session.add(project)
        session.commit()


def delete_project(path: str, project_id: str) -> None:
    with get_session(path) as session:
        p = session.get(Project, project_id)
        if p:
            session.delete(p)
            session.commit()


def update_project_status(
    path: str,
    project_id: str,
    status: ProjectStatus,
    error: Optional[str] = None,
) -> None:
    with get_session(path) as session:
        p = session.get(Project, project_id)
        if p:
            p.status = status
            p.error = error
            p.updated_at = datetime.now(timezone.utc)
            session.commit()


def next_port(path: str) -> int:
    """Return the lowest unused port starting from _PORT_START."""
    used = {p.port for p in load_projects(path)}
    port = _PORT_START
    while port in used:
        port += 1
    return port
```

- [ ] **Step 4: Run tests**

```bash
python3 -m pytest tests/test_project_store.py -v
```

Expected: all 9 pass.

- [ ] **Step 5: Commit**

```bash
git add app/services/project_store.py tests/test_project_store.py
git commit -m "feat: replace JSON project store with SQLite via SQLModel"
```

---

## Task 5: Add log_service.py

**Files:**
- Create: `app/services/log_service.py`
- Create: `tests/test_log_service.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_log_service.py`:

```python
import pytest
from datetime import datetime, timezone


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
```

- [ ] **Step 2: Run tests to confirm failure**

```bash
python3 -m pytest tests/test_log_service.py -v
```

Expected: `ImportError: No module named 'app.services.log_service'`

- [ ] **Step 3: Create app/services/log_service.py**

```python
# app/services/log_service.py
from sqlmodel import select
from app.db import get_session
from app.models import LogLine


def append_log(path: str, project_id: str, text: str) -> None:
    with get_session(path) as session:
        session.add(LogLine(project_id=project_id, text=text))
        session.commit()


def get_logs(path: str, project_id: str) -> list[LogLine]:
    with get_session(path) as session:
        stmt = select(LogLine).where(LogLine.project_id == project_id).order_by(LogLine.id)
        return list(session.exec(stmt).all())


def get_logs_after(path: str, project_id: str, after_id: int) -> list[LogLine]:
    with get_session(path) as session:
        stmt = (
            select(LogLine)
            .where(LogLine.project_id == project_id, LogLine.id > after_id)
            .order_by(LogLine.id)
        )
        return list(session.exec(stmt).all())
```

- [ ] **Step 4: Run tests**

```bash
python3 -m pytest tests/test_log_service.py -v
```

Expected: all 5 pass.

- [ ] **Step 5: Commit**

```bash
git add app/services/log_service.py tests/test_log_service.py
git commit -m "feat: add log_service for streaming LogLine writes and reads"
```

---

## Task 6: Rewrite docker_service.py

**Files:**
- Modify: `app/services/docker_service.py`
- Modify: `tests/test_docker_service.py`

- [ ] **Step 1: Rewrite tests/test_docker_service.py**

```python
# tests/test_docker_service.py
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
import subprocess


def test_run_streaming_yields_lines(tmp_path):
    from app.services.docker_service import _run_streaming
    lines = list(_run_streaming(["echo", "hello world"]))
    assert lines == ["hello world"]


def test_run_streaming_raises_docker_error_on_nonzero(tmp_path):
    from app.services.docker_service import _run_streaming, DockerError
    with pytest.raises(DockerError, match="failed"):
        list(_run_streaming(["false"]))  # 'false' exits with code 1


def test_validate_repo_accepts_dockerfile(tmp_path):
    from app.services.docker_service import validate_repo
    (tmp_path / "Dockerfile").write_text("FROM alpine")
    validate_repo(str(tmp_path))  # should not raise


def test_validate_repo_accepts_compose(tmp_path):
    from app.services.docker_service import validate_repo
    (tmp_path / "docker-compose.yml").write_text("services:\n  app:\n    image: alpine")
    validate_repo(str(tmp_path))  # should not raise


def test_validate_repo_raises_without_either(tmp_path):
    from app.services.docker_service import validate_repo, DockerError
    with pytest.raises(DockerError, match="No Dockerfile"):
        validate_repo(str(tmp_path))


def test_write_compose_override_creates_file(tmp_path):
    from app.services.docker_service import write_compose_override
    write_compose_override(str(tmp_path))
    override = tmp_path / "docker-compose.override.yml"
    assert override.exists()
    content = override.read_text()
    assert "512m" in content
    assert "0.5" in content


def test_write_compose_override_is_idempotent(tmp_path):
    from app.services.docker_service import write_compose_override
    write_compose_override(str(tmp_path))
    write_compose_override(str(tmp_path))  # second write should not raise
    content = (tmp_path / "docker-compose.override.yml").read_text()
    assert content.count("mem_limit") == 1


def test_deploy_project_calls_compose_up(tmp_path):
    from app.services.docker_service import deploy_project
    with patch("app.services.docker_service._run") as mock_run:
        deploy_project(str(tmp_path), port=3001)
    mock_run.assert_called_once_with(
        ["docker", "compose", "up", "-d", "--build"],
        cwd=str(tmp_path),
        env={"PORT": "3001"},
    )


def test_stop_project_calls_compose_down(tmp_path):
    from app.services.docker_service import stop_project
    with patch("app.services.docker_service._run") as mock_run:
        stop_project(str(tmp_path))
    mock_run.assert_called_once_with(
        ["docker", "compose", "down"], cwd=str(tmp_path), env=None,
    )


def test_project_status_running(tmp_path):
    from app.services.docker_service import project_status
    with patch("app.services.docker_service._run") as mock_run:
        mock_run.return_value = MagicMock(stdout="abc123\n")
        assert project_status(str(tmp_path)) == "running"


def test_project_status_stopped_no_containers(tmp_path):
    from app.services.docker_service import project_status
    with patch("app.services.docker_service._run") as mock_run:
        mock_run.return_value = MagicMock(stdout="")
        assert project_status(str(tmp_path)) == "stopped"


def test_project_status_stopped_nonexistent_path():
    from app.services.docker_service import project_status
    assert project_status("/nonexistent/path") == "stopped"
```

- [ ] **Step 2: Run tests to confirm failures**

```bash
python3 -m pytest tests/test_docker_service.py -v
```

Expected: failures on `_run_streaming`, `validate_repo`, `write_compose_override`.

- [ ] **Step 3: Rewrite app/services/docker_service.py**

```python
# app/services/docker_service.py
import logging
import os
import subprocess
from pathlib import Path
from typing import Iterator, Optional

logger = logging.getLogger(__name__)

COMPOSE_OVERRIDE = """\
services:
  app:
    mem_limit: 512m
    cpus: "0.5"
    network_mode: bridge
    restart: "no"
"""


class DockerError(Exception):
    pass


def _run(
    cmd: list[str],
    cwd: Optional[str] = None,
    timeout: int = 300,
    env: Optional[dict] = None,
) -> subprocess.CompletedProcess:
    run_env = {**os.environ, **(env or {})}
    result = subprocess.run(
        cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout, env=run_env,
    )
    if result.returncode != 0:
        logger.error("Command %s failed: %s", cmd, result.stderr)
        raise DockerError(f"{' '.join(cmd)} failed: {result.stderr}")
    return result


def _run_streaming(
    cmd: list[str],
    cwd: Optional[str] = None,
    timeout: int = 300,
    env: Optional[dict] = None,
) -> Iterator[str]:
    """Run command and yield stdout+stderr lines as they arrive.

    Raises DockerError if the process exits with non-zero status.
    """
    run_env = {**os.environ, **(env or {})}
    proc = subprocess.Popen(
        cmd, cwd=cwd, env=run_env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        for line in proc.stdout:
            yield line.rstrip()
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        raise DockerError(f"Command timed out after {timeout}s")
    if proc.returncode != 0:
        raise DockerError(f"{' '.join(cmd)} failed (exit {proc.returncode})")


def validate_repo(path: str) -> None:
    """Raise DockerError if neither Dockerfile nor docker-compose.yml is present."""
    p = Path(path)
    if not (p / "Dockerfile").exists() and not (p / "docker-compose.yml").exists():
        raise DockerError("No Dockerfile or docker-compose.yml found in repository root")


def write_compose_override(path: str) -> None:
    """Write resource-limit override file. Always regenerated so repo cannot override limits."""
    (Path(path) / "docker-compose.override.yml").write_text(COMPOSE_OVERRIDE)


def pull_repo(path: str) -> None:
    """Pull latest changes in an existing repo."""
    _run(["git", "pull"], cwd=path, timeout=120)


def deploy_project(path: str, port: Optional[int] = None) -> None:
    """Run docker compose up -d --build, passing PORT as env var."""
    env = {"PORT": str(port)} if port else None
    _run(["docker", "compose", "up", "-d", "--build"], cwd=path, env=env)


def stop_project(path: str) -> None:
    """Run docker compose down in the project directory."""
    _run(["docker", "compose", "down"], cwd=path, env=None)


def project_status(path: str) -> str:
    """Return 'running' if any compose service is up, otherwise 'stopped'."""
    if not Path(path).exists():
        return "stopped"
    try:
        result = _run(["docker", "compose", "ps", "-q"], cwd=path)
        return "running" if result.stdout.strip() else "stopped"
    except DockerError:
        return "stopped"
```

- [ ] **Step 4: Run tests**

```bash
python3 -m pytest tests/test_docker_service.py -v
```

Expected: all 12 pass.

- [ ] **Step 5: Commit**

```bash
git add app/services/docker_service.py tests/test_docker_service.py
git commit -m "fix: rewrite docker_service with streaming output, validate_repo, compose override"
```

---

## Task 7: Add clone validation tests

**Files:**
- Create: `tests/test_clone_validation.py`

- [ ] **Step 1: Create tests/test_clone_validation.py**

```python
# tests/test_clone_validation.py
import pytest


def test_url_with_semicolon_is_rejected():
    from app.models import DeployRequest
    with pytest.raises(Exception, match="safe https"):
        DeployRequest(
            name="x", subdomain="demo",
            repo_url="https://github.com/x/y;rm -rf /",
        )


def test_url_with_backtick_is_rejected():
    from app.models import DeployRequest
    with pytest.raises(Exception, match="safe https"):
        DeployRequest(
            name="x", subdomain="demo",
            repo_url="https://github.com/x/y`whoami`",
        )


def test_http_url_is_rejected():
    from app.models import DeployRequest
    with pytest.raises(Exception, match="safe https"):
        DeployRequest(
            name="x", subdomain="demo",
            repo_url="http://github.com/x/y",
        )


def test_valid_github_url_passes():
    from app.models import DeployRequest
    req = DeployRequest(
        name="x", subdomain="demo",
        repo_url="https://github.com/user/repo",
    )
    assert req.repo_url == "https://github.com/user/repo"


def test_subdomain_with_uppercase_rejected():
    from app.models import DeployRequest
    with pytest.raises(Exception, match="lowercase"):
        DeployRequest(
            name="x", subdomain="MyApp",
            repo_url="https://github.com/x/y",
        )


def test_subdomain_starting_with_hyphen_rejected():
    from app.models import DeployRequest
    with pytest.raises(Exception, match="lowercase"):
        DeployRequest(
            name="x", subdomain="-myapp",
            repo_url="https://github.com/x/y",
        )
```

- [ ] **Step 2: Run tests**

```bash
python3 -m pytest tests/test_clone_validation.py -v
```

Expected: all 6 pass.

- [ ] **Step 3: Commit**

```bash
git add tests/test_clone_validation.py
git commit -m "test: add clone URL and subdomain validation tests"
```

---

## Task 8: Update dependencies.py — add SSE token support

**Files:**
- Modify: `app/dependencies.py`

- [ ] **Step 1: Update app/dependencies.py**

The native browser `EventSource` API cannot send custom headers. Accept the JWT via a
`?token=` query parameter for the SSE logs endpoint.

```python
# app/dependencies.py
from fastapi import Depends, HTTPException, Query, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import ValidationError
from app.services.jwt_service import verify_token
from app.config import get_settings, Settings
from app.models import JWTClaims

_bearer = HTTPBearer()


def require_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    settings: Settings = Depends(get_settings),
) -> JWTClaims:
    try:
        return verify_token(credentials.credentials, settings.LAUNCHPAD_JWT_SECRET)
    except (ValueError, ValidationError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def require_user_sse(
    token: str = Query(..., description="JWT token for SSE auth"),
    settings: Settings = Depends(get_settings),
) -> JWTClaims:
    """Dependency for SSE endpoints — accepts token as query param."""
    try:
        return verify_token(token, settings.LAUNCHPAD_JWT_SECRET)
    except (ValueError, ValidationError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
```

- [ ] **Step 2: Run existing auth tests to confirm nothing broke**

```bash
python3 -m pytest tests/test_dependencies.py tests/test_auth_router.py -v
```

Expected: all pass.

- [ ] **Step 3: Commit**

```bash
git add app/dependencies.py
git commit -m "feat: add require_user_sse dependency with query-param token for EventSource"
```

---

## Task 9: Rewrite projects router

**Files:**
- Modify: `app/routers/projects.py`

- [ ] **Step 1: Rewrite app/routers/projects.py**

```python
# app/routers/projects.py
import logging
import shutil
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sse_starlette.sse import EventSourceResponse
import asyncio

from app.config import get_settings, Settings
from app.dependencies import require_user, require_user_sse
from app.models import Project, ProjectResponse, DeployRequest, JWTClaims, ProjectStatus
from app.services.project_store import (
    load_projects, upsert_project, delete_project, get_project, update_project_status, next_port,
)
from app.services.log_service import append_log, get_logs, get_logs_after
from app.services.docker_service import (
    _run_streaming, validate_repo, write_compose_override,
    deploy_project, stop_project, project_status, pull_repo, DockerError,
)
from app.services.cloudflare_service import add_ingress, remove_ingress

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/projects", tags=["projects"])


def _store_path(settings: Settings) -> str:
    return f"{settings.BASE_DIR}/projects.db"


def _get_or_404(store: str, project_id: str) -> Project:
    p = get_project(store, project_id)
    if not p:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return p


def _to_response(p: Project, live_status: str | None = None) -> ProjectResponse:
    return ProjectResponse(
        id=p.id, name=p.name, repo_url=p.repo_url, subdomain=p.subdomain,
        path=p.path, port=p.port,
        status=live_status if live_status is not None else p.status.value,
        error=p.error, deployed_at=p.deployed_at, updated_at=p.updated_at,
    )


# ── Background task functions ────────────────────────────────────────────────


def _do_clone(project_id: str, repo_url: str, path: str, store: str) -> None:
    """BackgroundTask: git clone → validate → update status."""
    update_project_status(store, project_id, ProjectStatus.cloning)
    append_log(store, project_id, f"=== Clone started: {repo_url} ===")
    try:
        if shutil.os.path.exists(path):
            shutil.rmtree(path)
        for line in _run_streaming(["git", "clone", repo_url, path], timeout=120):
            append_log(store, project_id, line)
        validate_repo(path)
        append_log(store, project_id, "=== Clone complete ===")
        update_project_status(store, project_id, ProjectStatus.cloned)
    except DockerError as e:
        append_log(store, project_id, f"ERROR: {e}")
        update_project_status(store, project_id, ProjectStatus.failed, str(e))


def _do_deploy(project_id: str, path: str, port: int, subdomain: str, store: str, settings: Settings) -> None:
    """BackgroundTask: write override → docker compose up → ingress → update status."""
    update_project_status(store, project_id, ProjectStatus.building)
    append_log(store, project_id, f"=== Deploy started (port {port}) ===")
    try:
        write_compose_override(path)
        for line in _run_streaming(
            ["docker", "compose", "up", "-d", "--build"],
            cwd=path,
            env={"PORT": str(port)},
            timeout=600,
        ):
            append_log(store, project_id, line)
        try:
            add_ingress(settings.CLOUDFLARED_CONFIG, subdomain, settings.BASE_DOMAIN, port)
        except Exception as e:
            logger.warning("Ingress failed for %s: %s", subdomain, e)
            append_log(store, project_id, f"Warning: ingress setup failed: {e}")
        with get_project(store, project_id) as _:
            pass  # ensure project still exists
        p = get_project(store, project_id)
        if p:
            from app.services.project_store import upsert_project
            p = p.model_copy(update={"deployed_at": datetime.now(timezone.utc)})
            upsert_project(store, p)
        append_log(store, project_id, "=== Deploy complete ===")
        update_project_status(store, project_id, ProjectStatus.running)
    except DockerError as e:
        append_log(store, project_id, f"ERROR: {e}")
        update_project_status(store, project_id, ProjectStatus.failed, str(e))


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.get("", response_model=list[ProjectResponse])
def list_projects(
    settings: Settings = Depends(get_settings),
    _: JWTClaims = Depends(require_user),
):
    store = _store_path(settings)
    result = []
    for p in load_projects(store):
        if p.status == ProjectStatus.running:
            try:
                live = project_status(p.path)
                if live != "running":
                    update_project_status(store, p.id, ProjectStatus.stopped)
                    result.append(_to_response(p, "stopped"))
                    continue
            except DockerError:
                pass
        result.append(_to_response(p))
    return result


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
def create_project(
    body: DeployRequest,
    settings: Settings = Depends(get_settings),
    _: JWTClaims = Depends(require_user),
):
    store = _store_path(settings)
    project = Project(
        id=str(uuid.uuid4()),
        name=body.name,
        repo_url=body.repo_url,
        subdomain=body.subdomain,
        path=f"{settings.BASE_DIR}/{body.subdomain}",
        port=next_port(store),
    )
    upsert_project(store, project)
    return _to_response(project)


@router.post("/{project_id}/clone", response_model=ProjectResponse)
def clone_project_endpoint(
    project_id: str,
    background_tasks: BackgroundTasks,
    settings: Settings = Depends(get_settings),
    _: JWTClaims = Depends(require_user),
):
    store = _store_path(settings)
    project = _get_or_404(store, project_id)
    if project.status not in (ProjectStatus.pending, ProjectStatus.failed):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot clone from status '{project.status.value}'",
        )
    background_tasks.add_task(
        _do_clone, project.id, project.repo_url, project.path, store,
    )
    return _to_response(project, "cloning")


@router.post("/{project_id}/deploy", response_model=ProjectResponse)
def deploy_project_endpoint(
    project_id: str,
    background_tasks: BackgroundTasks,
    settings: Settings = Depends(get_settings),
    _: JWTClaims = Depends(require_user),
):
    store = _store_path(settings)
    project = _get_or_404(store, project_id)
    allowed = (ProjectStatus.cloned, ProjectStatus.stopped, ProjectStatus.failed)
    if project.status not in allowed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot deploy from status '{project.status.value}'",
        )
    background_tasks.add_task(
        _do_deploy, project.id, project.path, project.port,
        project.subdomain, store, settings,
    )
    return _to_response(project, "building")


@router.post("/{project_id}/stop", response_model=ProjectResponse)
def stop_project_endpoint(
    project_id: str,
    settings: Settings = Depends(get_settings),
    _: JWTClaims = Depends(require_user),
):
    store = _store_path(settings)
    project = _get_or_404(store, project_id)
    try:
        stop_project(project.path)
    except DockerError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))
    try:
        remove_ingress(settings.CLOUDFLARED_CONFIG, project.subdomain, settings.BASE_DOMAIN)
    except Exception as e:
        logger.warning("Remove ingress failed for %s: %s", project.subdomain, e)
    update_project_status(store, project.id, ProjectStatus.stopped)
    return _to_response(get_project(store, project.id))


@router.post("/{project_id}/restart", response_model=ProjectResponse)
def restart_project_endpoint(
    project_id: str,
    background_tasks: BackgroundTasks,
    settings: Settings = Depends(get_settings),
    _: JWTClaims = Depends(require_user),
):
    store = _store_path(settings)
    project = _get_or_404(store, project_id)
    try:
        stop_project(project.path)
    except DockerError:
        pass
    try:
        remove_ingress(settings.CLOUDFLARED_CONFIG, project.subdomain, settings.BASE_DOMAIN)
    except Exception:
        pass
    update_project_status(store, project.id, ProjectStatus.stopped)
    background_tasks.add_task(
        _do_deploy, project.id, project.path, project.port,
        project.subdomain, store, settings,
    )
    return _to_response(get_project(store, project.id), "building")


@router.post("/{project_id}/update", response_model=ProjectResponse)
def update_project_endpoint(
    project_id: str,
    settings: Settings = Depends(get_settings),
    _: JWTClaims = Depends(require_user),
):
    store = _store_path(settings)
    project = _get_or_404(store, project_id)
    try:
        pull_repo(project.path)
        stop_project(project.path)
        deploy_project(project.path, project.port)
    except DockerError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))
    project = project.model_copy(update={"updated_at": datetime.now(timezone.utc)})
    upsert_project(store, project)
    return _to_response(project)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project_endpoint(
    project_id: str,
    settings: Settings = Depends(get_settings),
    _: JWTClaims = Depends(require_user),
):
    store = _store_path(settings)
    project = _get_or_404(store, project_id)
    try:
        stop_project(project.path)
    except DockerError:
        pass
    try:
        remove_ingress(settings.CLOUDFLARED_CONFIG, project.subdomain, settings.BASE_DOMAIN)
    except Exception:
        pass
    if shutil.os.path.exists(project.path):
        shutil.rmtree(project.path)
    delete_project(store, project_id)


@router.get("/{project_id}/logs")
async def logs_endpoint(
    project_id: str,
    settings: Settings = Depends(get_settings),
    _: JWTClaims = Depends(require_user_sse),
):
    store = _store_path(settings)
    _get_or_404(store, project_id)  # 404 early if not found

    async def event_generator():
        # Replay existing logs
        existing = get_logs(store, project_id)
        last_id = 0
        for log in existing:
            yield {"data": log.text}
            last_id = log.id

        # Poll for new logs until terminal status
        terminal = {ProjectStatus.running, ProjectStatus.failed, ProjectStatus.stopped}
        while True:
            await asyncio.sleep(0.5)
            p = get_project(store, project_id)
            new_lines = get_logs_after(store, project_id, last_id)
            for log in new_lines:
                yield {"data": log.text}
                last_id = log.id
            if p is None or p.status in terminal:
                break

    return EventSourceResponse(event_generator())
```

- [ ] **Step 2: Update main.py to use startup event**

```python
# app/main.py
import logging
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from app.routers import auth, projects

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Launchpad", version="2.0.0")

app.include_router(auth.router)
app.include_router(projects.router)


@app.on_event("startup")
def startup():
    from app.config import get_settings
    from app.db import get_engine
    settings = get_settings()
    import os
    os.makedirs(settings.BASE_DIR, exist_ok=True)
    get_engine(f"{settings.BASE_DIR}/projects.db")


@app.get("/health", tags=["ops"])
def health():
    return {"status": "ok"}


# Serve Vue SPA — must be last (catch-all)
_dist = Path(__file__).parent.parent / "frontend" / "dist"
if _dist.exists():
    app.mount("/", StaticFiles(directory=str(_dist), html=True), name="frontend")
```

- [ ] **Step 3: Commit**

```bash
git add app/routers/projects.py app/main.py
git commit -m "feat: async clone/deploy pipeline with SSE logs endpoint and restart"
```

---

## Task 10: Update and add router tests

**Files:**
- Modify: `tests/test_projects_router.py`
- Create: `tests/test_clone_deploy_flow.py`
- Create: `tests/test_status_transitions.py`

- [ ] **Step 1: Rewrite tests/test_projects_router.py**

```python
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


def _create_project(client, subdomain="demo", port_hint=None):
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
        "name": "My App", "repo_url": "https://github.com/x/y", "subdomain": "my-app",
    })
    assert r.status_code == 201
    assert r.json()["name"] == "My App"
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
    client = TestClient(_app(store_dir))
    p = _create_project(client, subdomain="demo2")
    update_project_status(store_dir + "/projects.db", p["id"], ProjectStatus.running)
    r = client.post(f"/projects/{p['id']}/clone", raise_server_exceptions=False)
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
```

- [ ] **Step 2: Run updated router tests**

```bash
python3 -m pytest tests/test_projects_router.py -v
```

Expected: all pass (some behavior changed; new tests added).

- [ ] **Step 3: Create tests/test_clone_deploy_flow.py**

```python
# tests/test_clone_deploy_flow.py
import pytest
from pathlib import Path
from unittest.mock import patch


@pytest.fixture
def store(tmp_path):
    return str(tmp_path / "projects.db")


@pytest.fixture
def project(store):
    from app.models import Project
    from app.services.project_store import upsert_project
    p = Project(
        id="p1", name="demo", repo_url="https://github.com/x/y",
        subdomain="demo", path="/tmp/demo-test", port=8001,
    )
    upsert_project(store, p)
    return p


def test_do_clone_sets_cloned_status(store, project, tmp_path):
    from app.routers.projects import _do_clone
    from app.services.project_store import get_project
    from app.models import ProjectStatus

    repo_path = str(tmp_path / "repo")
    project_updated = project.model_copy(update={"path": repo_path})
    from app.services.project_store import upsert_project
    upsert_project(store, project_updated)

    with patch("app.routers.projects._run_streaming") as mock_stream, \
         patch("app.routers.projects.validate_repo"):
        mock_stream.return_value = iter(["Cloning...", "done"])
        _do_clone(project.id, project.repo_url, repo_path, store)

    p = get_project(store, project.id)
    assert p.status == ProjectStatus.cloned


def test_do_clone_sets_failed_on_docker_error(store, project, tmp_path):
    from app.routers.projects import _do_clone
    from app.services.project_store import get_project
    from app.services.docker_service import DockerError
    from app.models import ProjectStatus

    repo_path = str(tmp_path / "repo")
    project_updated = project.model_copy(update={"path": repo_path})
    from app.services.project_store import upsert_project
    upsert_project(store, project_updated)

    with patch("app.routers.projects._run_streaming", side_effect=DockerError("network error")):
        _do_clone(project.id, project.repo_url, repo_path, store)

    p = get_project(store, project.id)
    assert p.status == ProjectStatus.failed
    assert "network error" in p.error


def test_do_clone_sets_failed_when_no_dockerfile(store, project, tmp_path):
    from app.routers.projects import _do_clone
    from app.services.project_store import get_project
    from app.services.docker_service import DockerError, validate_repo
    from app.models import ProjectStatus

    repo_path = str(tmp_path / "repo")
    project_updated = project.model_copy(update={"path": repo_path})
    from app.services.project_store import upsert_project
    upsert_project(store, project_updated)

    with patch("app.routers.projects._run_streaming") as mock_stream, \
         patch("app.routers.projects.validate_repo", side_effect=DockerError("No Dockerfile")):
        mock_stream.return_value = iter([])
        _do_clone(project.id, project.repo_url, repo_path, store)

    p = get_project(store, project.id)
    assert p.status == ProjectStatus.failed


def test_do_deploy_sets_running_status(store, project, tmp_path):
    from app.routers.projects import _do_deploy
    from app.services.project_store import get_project
    from app.models import ProjectStatus
    from app.config import Settings

    settings = Settings(
        ACCURO_URL="http://x", LAUNCHPAD_JWT_SECRET="a" * 32, TUNNEL_UUID="t",
        BASE_DIR=str(tmp_path),
    )

    with patch("app.routers.projects.write_compose_override"), \
         patch("app.routers.projects._run_streaming") as mock_stream, \
         patch("app.routers.projects.add_ingress"):
        mock_stream.return_value = iter(["Building...", "done"])
        _do_deploy(project.id, project.path, project.port, project.subdomain, store, settings)

    p = get_project(store, project.id)
    assert p.status == ProjectStatus.running


def test_do_deploy_sets_failed_on_docker_error(store, project, tmp_path):
    from app.routers.projects import _do_deploy
    from app.services.project_store import get_project
    from app.services.docker_service import DockerError
    from app.models import ProjectStatus
    from app.config import Settings

    settings = Settings(
        ACCURO_URL="http://x", LAUNCHPAD_JWT_SECRET="a" * 32, TUNNEL_UUID="t",
        BASE_DIR=str(tmp_path),
    )

    with patch("app.routers.projects.write_compose_override"), \
         patch("app.routers.projects._run_streaming", side_effect=DockerError("build failed")):
        _do_deploy(project.id, project.path, project.port, project.subdomain, store, settings)

    p = get_project(store, project.id)
    assert p.status == ProjectStatus.failed
    assert "build failed" in p.error
```

- [ ] **Step 4: Create tests/test_status_transitions.py**

```python
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
    pid = _create_and_set_status(client, store_dir, ProjectStatus.running)
    r = client.post(f"/projects/{pid}/clone")
    assert r.status_code == 409


def test_cannot_deploy_from_pending(store_dir):
    client = TestClient(_app(store_dir), raise_server_exceptions=False)
    pid = _create_and_set_status(client, store_dir, ProjectStatus.pending, subdomain="d2")
    r = client.post(f"/projects/{pid}/deploy")
    assert r.status_code == 409


def test_cannot_deploy_from_cloning(store_dir):
    client = TestClient(_app(store_dir), raise_server_exceptions=False)
    pid = _create_and_set_status(client, store_dir, ProjectStatus.cloning, subdomain="d3")
    r = client.post(f"/projects/{pid}/deploy")
    assert r.status_code == 409


def test_can_deploy_from_cloned(store_dir):
    from unittest.mock import patch
    client = TestClient(_app(store_dir))
    pid = _create_and_set_status(client, store_dir, ProjectStatus.cloned, subdomain="d4")
    with patch("app.routers.projects._do_deploy"):
        r = client.post(f"/projects/{pid}/deploy")
    assert r.status_code == 200


def test_can_deploy_from_failed(store_dir):
    from unittest.mock import patch
    client = TestClient(_app(store_dir))
    pid = _create_and_set_status(client, store_dir, ProjectStatus.failed, subdomain="d5")
    with patch("app.routers.projects._do_deploy"):
        r = client.post(f"/projects/{pid}/deploy")
    assert r.status_code == 200


def test_can_clone_from_failed(store_dir):
    from unittest.mock import patch
    client = TestClient(_app(store_dir))
    pid = _create_and_set_status(client, store_dir, ProjectStatus.failed, subdomain="d6")
    with patch("app.routers.projects._do_clone"):
        r = client.post(f"/projects/{pid}/clone")
    assert r.status_code == 200
```

- [ ] **Step 5: Create tests/test_sse_logs.py**

```python
# tests/test_sse_logs.py
import asyncio
import pytest
from datetime import datetime, timezone


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
    """Event generator emits all pre-existing log lines before polling."""
    from app.services.log_service import append_log
    from app.services.project_store import update_project_status
    from app.models import ProjectStatus

    append_log(store, project.id, "line 1")
    append_log(store, project.id, "line 2")
    update_project_status(store, project.id, ProjectStatus.running)

    # Inline the generator logic to test it without HTTP
    from app.services.log_service import get_logs, get_logs_after
    from app.services.project_store import get_project

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
    """Generator stops polling when status is 'failed'."""
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
```

- [ ] **Step 6: Run all new tests**

```bash
python3 -m pytest tests/test_clone_deploy_flow.py tests/test_status_transitions.py tests/test_sse_logs.py -v
```

Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add tests/test_projects_router.py tests/test_clone_deploy_flow.py \
        tests/test_status_transitions.py tests/test_sse_logs.py
git commit -m "test: update router tests and add clone/deploy/sse/transition integration tests"
```

---

## Task 11: Full test run — backend

- [ ] **Step 1: Run complete test suite**

```bash
python3 -m pytest -v
```

Expected: all tests pass. If any fail, fix before proceeding.

- [ ] **Step 2: Commit any fixes**

```bash
git add -A
git commit -m "fix: resolve any remaining test failures"
```

---

## Task 12: Frontend — update projects.ts API client

**Files:**
- Modify: `frontend/src/api/projects.ts`

- [ ] **Step 1: Update frontend/src/api/projects.ts**

```typescript
import { apiClient } from './client'

export type ProjectStatus =
  | 'pending' | 'cloning' | 'cloned'
  | 'building' | 'running' | 'failed' | 'stopped'

export interface Project {
  id: string
  name: string
  repo_url: string
  subdomain: string
  path: string
  port: number
  status: ProjectStatus
  error: string | null
  deployed_at: string | null
  updated_at: string | null
}

export interface CreateProjectPayload {
  name: string
  repo_url: string
  subdomain: string
}

export const projectsApi = {
  list:    ()          => apiClient.get<Project[]>('/projects'),
  create:  (data: CreateProjectPayload) => apiClient.post<Project>('/projects', data),
  clone:   (id: string) => apiClient.post<Project>(`/projects/${id}/clone`),
  deploy:  (id: string) => apiClient.post<Project>(`/projects/${id}/deploy`),
  restart: (id: string) => apiClient.post<Project>(`/projects/${id}/restart`),
  update:  (id: string) => apiClient.post<Project>(`/projects/${id}/update`),
  stop:    (id: string) => apiClient.post<Project>(`/projects/${id}/stop`),
  remove:  (id: string) => apiClient.delete(`/projects/${id}`),
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/api/projects.ts
git commit -m "feat: add clone/restart endpoints to frontend API client"
```

---

## Task 13: Frontend — StatusBadge component

**Files:**
- Create: `frontend/src/components/StatusBadge.vue`

- [ ] **Step 1: Create frontend/src/components/StatusBadge.vue**

```vue
<template>
  <span class="badge" :class="badgeClass">
    <span class="w-1.5 h-1.5 rounded-full mr-1" :class="dotClass"></span>
    <svg
      v-if="spinning"
      class="animate-spin h-3 w-3 mr-1"
      viewBox="0 0 24 24"
    >
      <circle
        cx="12" cy="12" r="10"
        stroke="currentColor" stroke-width="3"
        fill="none" stroke-dasharray="31.4 31.4"
        stroke-linecap="round"
      />
    </svg>
    {{ status }}
  </span>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { ProjectStatus } from '@/api/projects'

const props = defineProps<{ status: ProjectStatus }>()

const spinning = computed(() =>
  props.status === 'cloning' || props.status === 'building'
)

const badgeClass = computed(() => ({
  'bg-gray-100 text-gray-500':   props.status === 'pending' || props.status === 'stopped',
  'bg-blue-50 text-blue-700':    props.status === 'cloning' || props.status === 'building',
  'bg-yellow-50 text-yellow-700': props.status === 'cloned',
  'bg-green-50 text-green-700':  props.status === 'running',
  'bg-red-50 text-red-700':      props.status === 'failed',
}))

const dotClass = computed(() => ({
  'bg-gray-400':   props.status === 'pending' || props.status === 'stopped',
  'bg-blue-500':   props.status === 'cloning' || props.status === 'building',
  'bg-yellow-500': props.status === 'cloned',
  'bg-green-500':  props.status === 'running',
  'bg-red-500':    props.status === 'failed',
}))
</script>
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/StatusBadge.vue
git commit -m "feat: add StatusBadge component for all 7 project statuses"
```

---

## Task 14: Frontend — useProjectLogs composable

**Files:**
- Create: `frontend/src/composables/useProjectLogs.ts`

- [ ] **Step 1: Create frontend/src/composables/useProjectLogs.ts**

```typescript
import { ref, onUnmounted } from 'vue'

export function useProjectLogs(projectId: string) {
  const logs = ref<string[]>([])
  const streaming = ref(false)
  let source: EventSource | null = null

  function start() {
    const token = localStorage.getItem('token')
    if (!token) return
    close()
    logs.value = []
    streaming.value = true
    source = new EventSource(`/projects/${projectId}/logs?token=${encodeURIComponent(token)}`)
    source.onmessage = (e) => {
      logs.value.push(e.data)
    }
    source.onerror = () => {
      streaming.value = false
      source?.close()
      source = null
    }
  }

  function close() {
    source?.close()
    source = null
    streaming.value = false
  }

  onUnmounted(close)

  return { logs, streaming, start, close }
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/composables/useProjectLogs.ts
git commit -m "feat: add useProjectLogs SSE composable"
```

---

## Task 15: Frontend — LogDrawer component

**Files:**
- Create: `frontend/src/components/LogDrawer.vue`

- [ ] **Step 1: Create frontend/src/components/LogDrawer.vue**

```vue
<template>
  <Teleport to="body">
    <div
      v-if="visible"
      class="fixed inset-0 z-40 flex"
      @click.self="$emit('close')"
    >
      <!-- Overlay -->
      <div class="absolute inset-0 bg-black/40" @click="$emit('close')"></div>

      <!-- Drawer panel -->
      <div class="relative ml-auto w-full max-w-2xl bg-gray-950 shadow-xl flex flex-col h-full z-50">
        <!-- Header -->
        <div class="flex items-center justify-between px-4 py-3 border-b border-gray-800">
          <div>
            <p class="text-sm font-medium text-gray-100">{{ projectName }}</p>
            <p class="text-xs text-gray-400 font-mono">logs</p>
          </div>
          <div class="flex items-center gap-3">
            <span v-if="streaming" class="flex items-center gap-1 text-xs text-green-400">
              <span class="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse"></span>
              live
            </span>
            <button class="text-gray-400 hover:text-gray-100 transition-colors" @click="$emit('close')">
              <i class="pi pi-times text-sm"></i>
            </button>
          </div>
        </div>

        <!-- Log output -->
        <div ref="logContainer" class="flex-1 overflow-y-auto p-4 font-mono text-xs text-gray-300 space-y-0.5">
          <div v-if="logs.length === 0" class="text-gray-500">Waiting for logs…</div>
          <div v-for="(line, i) in logs" :key="i" class="leading-5 whitespace-pre-wrap break-all">
            {{ line }}
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, watch, nextTick } from 'vue'
import { useProjectLogs } from '@/composables/useProjectLogs'

const props = defineProps<{
  visible: boolean
  projectId: string
  projectName: string
}>()

defineEmits<{ (e: 'close'): void }>()

const logContainer = ref<HTMLElement | null>(null)
const { logs, streaming, start, close } = useProjectLogs(props.projectId)

watch(() => props.visible, (val) => {
  if (val) start()
  else close()
})

watch(logs, async () => {
  await nextTick()
  if (logContainer.value) {
    logContainer.value.scrollTop = logContainer.value.scrollHeight
  }
}, { deep: true })
</script>
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/LogDrawer.vue
git commit -m "feat: add LogDrawer slide-over component with SSE log streaming"
```

---

## Task 16: Frontend — update Dashboard.vue

**Files:**
- Modify: `frontend/src/views/Dashboard.vue`

Replace the entire `Dashboard.vue` file. Key changes: new action buttons per status, polling while building/cloning, LogDrawer integration, repo info block.

- [ ] **Step 1: Replace frontend/src/views/Dashboard.vue**

```vue
<template>
  <div class="space-y-6">
    <!-- Header -->
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-lg font-semibold text-gray-900">Dashboard</h1>
        <p class="text-sm text-gray-500">Beheer je demo deployments</p>
      </div>
      <button class="btn-primary" @click="showNewProject = true">
        <i class="pi pi-plus text-xs"></i>
        Nieuw project
      </button>
    </div>

    <!-- Stats -->
    <div class="grid grid-cols-3 gap-4">
      <div class="stat-card">
        <p class="text-xs font-mono text-gray-500 uppercase tracking-wider">Projecten</p>
        <p class="text-2xl font-semibold text-gray-900">{{ projects.length }}</p>
      </div>
      <div class="stat-card">
        <p class="text-xs font-mono text-gray-500 uppercase tracking-wider">Actief</p>
        <p class="text-2xl font-semibold text-green-600">{{ runningCount }}</p>
      </div>
      <div class="stat-card">
        <p class="text-xs font-mono text-gray-500 uppercase tracking-wider">Domeinen</p>
        <div class="flex flex-wrap gap-1 pt-1">
          <a
            v-for="p in runningProjects"
            :key="p.id"
            :href="`https://${p.subdomain}.webvakwerk.nl`"
            target="_blank"
            rel="noopener noreferrer"
            class="badge bg-blue-50 text-blue-700 hover:bg-blue-100 transition-colors"
          >{{ p.subdomain }}</a>
          <span v-if="runningProjects.length === 0" class="text-sm text-gray-400">—</span>
        </div>
      </div>
    </div>

    <!-- Repo requirements info block -->
    <div class="card p-4">
      <button
        class="flex items-center gap-2 text-sm font-medium text-gray-700 w-full text-left"
        @click="showRepoInfo = !showRepoInfo"
      >
        <i class="pi pi-info-circle text-blue-500"></i>
        Vereisten voor je repository
        <i class="pi ml-auto text-gray-400 transition-transform" :class="showRepoInfo ? 'pi-chevron-up' : 'pi-chevron-down'"></i>
      </button>
      <div v-if="showRepoInfo" class="mt-3 text-sm text-gray-600 space-y-2 border-t border-gray-100 pt-3">
        <p>Zorg dat je repository voldoet aan de volgende vereisten:</p>
        <ul class="list-disc list-inside space-y-1 text-gray-500">
          <li>Een werkende <code class="bg-gray-100 px-1 rounded">Dockerfile</code> <strong>of</strong> <code class="bg-gray-100 px-1 rounded">docker-compose.yml</code> in de root</li>
          <li>De applicatie luistert op de poort die wordt doorgegeven via de <code class="bg-gray-100 px-1 rounded">PORT</code> omgevingsvariabele</li>
          <li>Optioneel: een <code class="bg-gray-100 px-1 rounded">.env.example</code> bestand voor documentatie</li>
        </ul>
        <p class="text-xs text-gray-400">Na het clonen wordt gecontroleerd of de vereiste bestanden aanwezig zijn.</p>
      </div>
    </div>

    <!-- Table -->
    <div class="card overflow-hidden">
      <div v-if="loading" class="p-8 text-center text-gray-400 text-sm">Laden…</div>
      <div v-else-if="fetchError" class="p-8 text-center text-red-400 text-sm">
        <i class="pi pi-exclamation-circle mr-2"></i>
        Projecten laden mislukt — ververs de pagina.
      </div>
      <table v-else class="w-full light-table">
        <thead>
          <tr>
            <th class="text-left px-4 py-3 text-xs font-mono text-gray-500 uppercase tracking-wider bg-gray-50 border-b border-gray-200">Naam</th>
            <th class="text-left px-4 py-3 text-xs font-mono text-gray-500 uppercase tracking-wider bg-gray-50 border-b border-gray-200">Repo</th>
            <th class="text-left px-4 py-3 text-xs font-mono text-gray-500 uppercase tracking-wider bg-gray-50 border-b border-gray-200">Status</th>
            <th class="text-left px-4 py-3 text-xs font-mono text-gray-500 uppercase tracking-wider bg-gray-50 border-b border-gray-200">Deployed</th>
            <th class="px-4 py-3 bg-gray-50 border-b border-gray-200"></th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="projects.length === 0">
            <td colspan="5" class="px-4 py-8 text-center text-sm text-gray-400">
              Geen projecten — maak er een aan.
            </td>
          </tr>
          <tr
            v-for="project in projects"
            :key="project.id"
            class="border-b border-gray-100 hover:bg-gray-50 transition-colors cursor-pointer"
            @click="openLogs(project)"
          >
            <!-- Naam -->
            <td class="px-4 py-3" @click.stop>
              <a
                v-if="project.status === 'running'"
                :href="`https://${project.subdomain}.webvakwerk.nl`"
                target="_blank"
                rel="noopener noreferrer"
                class="text-sm font-medium text-gray-900 hover:text-blue-600 transition-colors"
              >{{ project.name }}</a>
              <span v-else class="text-sm font-medium text-gray-900">{{ project.name }}</span>
              <p v-if="project.error" class="text-xs text-red-500 mt-0.5 truncate max-w-xs" :title="project.error">
                {{ project.error }}
              </p>
            </td>
            <!-- Repo -->
            <td class="px-4 py-3">
              <span class="text-sm text-gray-500 font-mono">{{ truncate(project.repo_url, 40) }}</span>
            </td>
            <!-- Status -->
            <td class="px-4 py-3">
              <StatusBadge :status="project.status" />
            </td>
            <!-- Deployed -->
            <td class="px-4 py-3">
              <span class="text-sm text-gray-500" :title="project.deployed_at ?? ''">
                {{ relativeTime(project.deployed_at) }}
              </span>
            </td>
            <!-- Acties -->
            <td class="px-4 py-3" @click.stop>
              <div class="flex items-center gap-1 justify-end">
                <!-- Clone (pending, failed) -->
                <button
                  v-if="project.status === 'pending' || project.status === 'failed'"
                  class="btn-secondary text-xs px-2 py-1"
                  :disabled="!!busy[project.id]"
                  title="Clone repository"
                  @click="action(project, 'clone')"
                >
                  <svg v-if="busy[project.id] === 'clone'" class="animate-spin h-3 w-3" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="3" fill="none" stroke-dasharray="31.4 31.4" stroke-linecap="round"/></svg>
                  <i v-else class="pi pi-download text-xs"></i>
                </button>

                <!-- Deploy (cloned, stopped, failed-after-build) -->
                <button
                  v-if="project.status === 'cloned' || project.status === 'stopped'"
                  class="btn-primary text-xs px-2 py-1"
                  :disabled="!!busy[project.id]"
                  title="Deploy"
                  @click="action(project, 'deploy')"
                >
                  <svg v-if="busy[project.id] === 'deploy'" class="animate-spin h-3 w-3" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="3" fill="none" stroke-dasharray="31.4 31.4" stroke-linecap="round"/></svg>
                  <i v-else class="pi pi-play text-xs"></i>
                </button>

                <!-- Update + Restart (running) -->
                <template v-if="project.status === 'running'">
                  <button
                    class="btn-secondary text-xs px-2 py-1"
                    :disabled="!!busy[project.id]"
                    title="Update (git pull + rebuild)"
                    @click="action(project, 'update')"
                  >
                    <svg v-if="busy[project.id] === 'update'" class="animate-spin h-3 w-3" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="3" fill="none" stroke-dasharray="31.4 31.4" stroke-linecap="round"/></svg>
                    <i v-else class="pi pi-refresh text-xs"></i>
                  </button>
                  <button
                    class="btn-danger text-xs px-2 py-1"
                    :disabled="!!busy[project.id]"
                    title="Stop"
                    @click="confirmStop(project)"
                  >
                    <svg v-if="busy[project.id] === 'stop'" class="animate-spin h-3 w-3" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="3" fill="none" stroke-dasharray="31.4 31.4" stroke-linecap="round"/></svg>
                    <i v-else class="pi pi-stop-circle text-xs"></i>
                  </button>
                </template>

                <!-- Delete (stopped, failed, cloned) -->
                <button
                  v-if="['stopped', 'failed', 'cloned', 'pending'].includes(project.status)"
                  class="btn-icon"
                  :disabled="!!busy[project.id]"
                  title="Verwijder"
                  @click="confirmDelete(project)"
                >
                  <i class="pi pi-trash text-xs"></i>
                </button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Nieuw project dialog -->
    <Dialog v-model:visible="showNewProject" header="Nieuw project" :style="{ width: '28rem' }" modal>
      <form @submit.prevent="createProject" class="space-y-4">
        <div>
          <label class="block text-xs font-medium text-gray-500 mb-1.5 uppercase tracking-wider">Naam</label>
          <input v-model="form.name" class="input" placeholder="Mijn App" required />
        </div>
        <div>
          <label class="block text-xs font-medium text-gray-500 mb-1.5 uppercase tracking-wider">Repo URL</label>
          <input v-model="form.repo_url" class="input" placeholder="https://github.com/user/repo" type="url" required />
        </div>
        <div>
          <label class="block text-xs font-medium text-gray-500 mb-1.5 uppercase tracking-wider">Subdomain</label>
          <input v-model="form.subdomain" class="input" placeholder="mijn-app" pattern="[a-z0-9][a-z0-9\-]{0,46}[a-z0-9]" required />
        </div>
        <div class="flex justify-end gap-2 pt-2">
          <button type="button" class="btn-secondary" @click="showNewProject = false">Annuleren</button>
          <button type="submit" class="btn-primary" :disabled="creating">
            <svg v-if="creating" class="animate-spin h-4 w-4" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="3" fill="none" stroke-dasharray="31.4 31.4" stroke-linecap="round"/></svg>
            <span v-else>Aanmaken</span>
          </button>
        </div>
      </form>
    </Dialog>

    <!-- Log Drawer -->
    <LogDrawer
      v-if="activeLogProject"
      :visible="showLogDrawer"
      :project-id="activeLogProject.id"
      :project-name="activeLogProject.name"
      @close="showLogDrawer = false"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useToast } from 'primevue/usetoast'
import { useConfirm } from 'primevue/useconfirm'
import Dialog from 'primevue/dialog'
import StatusBadge from '@/components/StatusBadge.vue'
import LogDrawer from '@/components/LogDrawer.vue'
import { projectsApi, type Project } from '@/api/projects'

const toast = useToast()
const confirm = useConfirm()

const projects = ref<Project[]>([])
const loading = ref(true)
const fetchError = ref(false)
const busy = ref<Record<string, string>>({})
const showNewProject = ref(false)
const creating = ref(false)
const showRepoInfo = ref(false)
const showLogDrawer = ref(false)
const activeLogProject = ref<Project | null>(null)

const form = ref({ name: '', repo_url: '', subdomain: '' })

const runningCount = computed(() => projects.value.filter(p => p.status === 'running').length)
const runningProjects = computed(() => projects.value.filter(p => p.status === 'running'))
const hasActiveJobs = computed(() =>
  projects.value.some(p => p.status === 'cloning' || p.status === 'building')
)

// ── Polling ───────────────────────────────────────────────────────────────────

let pollInterval: ReturnType<typeof setInterval> | null = null

function startPolling() {
  if (pollInterval) return
  pollInterval = setInterval(async () => {
    if (!hasActiveJobs.value) {
      stopPolling()
      return
    }
    await fetchProjects()
  }, 3000)
}

function stopPolling() {
  if (pollInterval) {
    clearInterval(pollInterval)
    pollInterval = null
  }
}

onUnmounted(stopPolling)

// ── Data fetching ─────────────────────────────────────────────────────────────

async function fetchProjects() {
  fetchError.value = false
  try {
    const { data } = await projectsApi.list()
    projects.value = data
    if (hasActiveJobs.value) startPolling()
    else stopPolling()
  } catch {
    fetchError.value = true
  }
}

onMounted(async () => {
  loading.value = true
  await fetchProjects()
  loading.value = false
})

// ── Actions ───────────────────────────────────────────────────────────────────

async function action(project: Project, type: 'clone' | 'deploy' | 'update' | 'stop') {
  busy.value[project.id] = type
  try {
    const fn = projectsApi[type] as (id: string) => Promise<any>
    const { data } = await fn(project.id)
    // Optimistically update status in list
    const idx = projects.value.findIndex(p => p.id === project.id)
    if (idx !== -1) projects.value[idx] = data
    if (hasActiveJobs.value) startPolling()
  } catch (e: any) {
    toast.add({
      severity: 'error',
      summary: 'Fout',
      detail: e?.response?.data?.detail ?? 'Actie mislukt',
      life: 4000,
    })
  } finally {
    delete busy.value[project.id]
  }
}

function confirmStop(project: Project) {
  confirm.require({
    message: `Stop container voor "${project.name}"?`,
    header: 'Container stoppen',
    icon: 'pi pi-exclamation-triangle',
    acceptClass: 'btn-danger',
    accept: () => action(project, 'stop'),
  })
}

function confirmDelete(project: Project) {
  confirm.require({
    message: `Verwijder project "${project.name}" inclusief bestanden en containers?`,
    header: 'Project verwijderen',
    icon: 'pi pi-trash',
    acceptClass: 'btn-danger',
    accept: async () => {
      busy.value[project.id] = 'delete'
      try {
        await projectsApi.remove(project.id)
        projects.value = projects.value.filter(p => p.id !== project.id)
      } catch (e: any) {
        toast.add({
          severity: 'error',
          summary: 'Fout',
          detail: e?.response?.data?.detail ?? 'Verwijderen mislukt',
          life: 4000,
        })
      } finally {
        delete busy.value[project.id]
      }
    },
  })
}

async function createProject() {
  creating.value = true
  try {
    const { data } = await projectsApi.create(form.value)
    projects.value.push(data)
    showNewProject.value = false
    form.value = { name: '', repo_url: '', subdomain: '' }
    toast.add({ severity: 'success', summary: 'Aangemaakt', detail: data.name, life: 3000 })
  } catch (e: any) {
    toast.add({
      severity: 'error',
      summary: 'Fout',
      detail: e?.response?.data?.detail ?? 'Aanmaken mislukt',
      life: 4000,
    })
  } finally {
    creating.value = false
  }
}

// ── Log drawer ────────────────────────────────────────────────────────────────

function openLogs(project: Project) {
  activeLogProject.value = project
  showLogDrawer.value = true
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function truncate(s: string, n: number) {
  return s.length > n ? s.slice(0, n) + '…' : s
}

function relativeTime(iso: string | null): string {
  if (!iso) return '—'
  const diff = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'zojuist'
  if (mins < 60) return `${mins}m geleden`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours}u geleden`
  return `${Math.floor(hours / 24)}d geleden`
}
</script>
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/views/Dashboard.vue
git commit -m "feat: update dashboard with two-step clone/deploy, status badges, log drawer, polling"
```

---

## Task 17: Build frontend and run full test suite

- [ ] **Step 1: Install frontend dependencies and build**

```bash
cd /home/gebruiker/Launchpad/frontend && npm install && npm run build
```

Expected: build completes without errors. Fix any TypeScript errors before proceeding.

- [ ] **Step 2: Run complete backend test suite**

```bash
cd /home/gebruiker/Launchpad && python3 -m pytest -v
```

Expected: all tests pass. If any fail:
- Read the error message carefully
- Fix the root cause (do not skip or mock around it)
- Re-run until all green

- [ ] **Step 3: Final commit**

```bash
git add frontend/dist
git commit -m "build: rebuild frontend dist with new clone/deploy/logs UI"
```

---

## Self-Review Checklist

After implementation, verify each spec requirement has a corresponding task:

| Spec requirement | Task |
|---|---|
| Clone as separate step | Tasks 9, 10 |
| Status: pending→cloning→cloned→building→running→failed→stopped | Tasks 2, 4 |
| Async clone BackgroundTask | Task 9 |
| Async deploy BackgroundTask | Task 9 |
| Validate repo (Dockerfile/docker-compose.yml) | Tasks 6, 7 |
| SSE log streaming | Tasks 9, 10 |
| LogLine DB table | Tasks 2, 5 |
| Resource limits (512m / 0.5 CPU) | Task 6 |
| Compose override regenerated on each deploy | Task 6 |
| Restart endpoint | Task 9 |
| Delete cleans up files + container + DB | Task 9 |
| SQLite WAL mode | Task 3 |
| SSE auth via query param | Task 8 |
| StatusBadge component | Task 13 |
| LogDrawer component | Task 15 |
| Dashboard polling | Task 16 |
| Repo requirements info block | Task 16 |
| Fix pre-existing 10 test failures | Tasks 6, 9, 10 |
| All tests pass | Task 11, 17 |
