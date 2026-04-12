# Launchpad — PaaS Demo Platform: Design Spec

**Date:** 2026-04-12  
**Status:** Approved  
**Scope:** Extend Launchpad with async clone/deploy pipeline, live log streaming, granular project status, and resource-limited containers.

---

## 1. Context

Launchpad is an existing FastAPI + Vue 3 application that registers GitHub repos, builds Docker images via `docker compose`, and exposes them via Cloudflare Tunnel subdomains. Authentication is delegated to Accuro; Launchpad issues its own short-lived JWT.

The current flow is fully synchronous: clone + build + run happen in a single blocking HTTP request. This spec extends the platform to make clone and deploy async, add live log streaming, and split the flow into two explicit user steps (Clone → Deploy).

**Scale target:** 1–5 concurrent deployments (personal/team use).

---

## 2. Architecture

```
┌─────────────────────────────────────────────────┐
│  Vue 3 Frontend                                 │
│  ProjectTable · CloneModal · LogDrawer          │
└────────────────┬────────────────────────────────┘
                 │ HTTP + SSE
┌────────────────▼────────────────────────────────┐
│  FastAPI                                        │
│  /projects          CRUD + clone trigger        │
│  /projects/{id}/clone    → BackgroundTask       │
│  /projects/{id}/deploy   → BackgroundTask       │
│  /projects/{id}/logs     → SSE stream           │
│  /projects/{id}/stop                            │
│  /projects/{id}/restart                         │
│  DELETE /projects/{id}                          │
└──────┬──────────────────────────┬───────────────┘
       │ SQLModel (SQLite)        │ subprocess
┌──────▼──────────┐    ┌─────────▼───────────────┐
│  projects.db    │    │  Docker CLI             │
│  Project table  │    │  git clone / pull       │
│  LogLine table  │    │  docker compose up/down │
└─────────────────┘    └─────────────────────────┘
```

**What changes vs. current:**

| Current | New |
|---|---|
| JSON file store | SQLite via SQLModel |
| Synchronous clone + build | Clone and deploy as separate BackgroundTasks |
| Two statuses: running / stopped | Seven statuses: pending → cloning → cloned → building → running → failed → stopped |
| No logs | LogLine table + SSE endpoint |
| No resource limits | `--memory 512m --cpus 0.5` on every container |

The existing `docker_service.py`, `cloudflare_service.py`, and auth layer remain largely intact. `project_store.py` is replaced by a SQLite-backed store.

---

## 3. Data Model

```python
class ProjectStatus(str, Enum):
    pending   = "pending"    # created, not yet cloned
    cloning   = "cloning"    # git clone running
    cloned    = "cloned"     # ready for deploy
    building  = "building"   # docker build running
    running   = "running"    # container is up
    failed    = "failed"     # clone or build failed
    stopped   = "stopped"    # intentionally stopped

class Project(SQLModel, table=True):
    id:          str             # UUID, primary key
    name:        str
    repo_url:    str
    subdomain:   str             # unique, indexed
    path:        str
    port:        int             # auto-assigned, 8001+
    status:      ProjectStatus   # default: pending
    error:       str | None      # last error message
    deployed_at: datetime | None
    updated_at:  datetime | None

class LogLine(SQLModel, table=True):
    id:         int | None       # auto-increment primary key
    project_id: str              # FK → Project.id, indexed
    ts:         datetime         # UTC timestamp
    text:       str              # log line content
```

**Notes:**
- SQLite WAL mode is enabled so SSE reads and BackgroundTask writes don't block each other.
- LogLines are cumulative per project (not per job). Timestamps separate deploy runs.
- Log cleanup is out of scope for this iteration.

---

## 4. API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/projects` | List all projects with live status |
| `POST` | `/projects` | Create project (status: `pending`) |
| `POST` | `/projects/{id}/clone` | Start clone as BackgroundTask |
| `POST` | `/projects/{id}/deploy` | Start build+run as BackgroundTask |
| `POST` | `/projects/{id}/stop` | Stop container (synchronous) |
| `POST` | `/projects/{id}/restart` | Stop + deploy as BackgroundTask |
| `DELETE` | `/projects/{id}` | Stop container, remove ingress, delete files + DB row |
| `GET` | `/projects/{id}/logs` | SSE stream of LogLines |

### Clone flow (BackgroundTask)
```
POST /projects/{id}/clone  (requires status = pending or failed)
  → set status = cloning
  → if path exists: remove directory (retry case)
  → git clone repo_url path  (timeout: 120s)
  → check: Dockerfile or docker-compose.yml present?
    → yes: set status = cloned
    → no:  set status = failed, error = "No Dockerfile or docker-compose.yml found"
```

Note: directory removal before re-clone handles partial clones from previous failed attempts.

### Deploy flow (BackgroundTask)
```
POST /projects/{id}/deploy  (requires status = cloned, stopped, or failed)
  → set status = building
  → write docker-compose.override.yml with resource limits
  → docker compose up -d --build  (with PORT env var)
  → add_ingress(subdomain, domain, port)
  → set status = running, deployed_at = now()
  → on error: set status = failed, error = stderr
```

Note: `failed` is allowed so that a failed deploy can be retried without re-cloning.

### SSE logs endpoint
```
GET /projects/{id}/logs
  → replay all existing LogLines for the project
  → poll every 0.5s for new LogLines, emit as SSE events
  → close stream when status ∈ {running, failed, stopped}
```

---

## 5. Resource Limits

A `docker-compose.override.yml` is written to the project directory before every deploy:

```yaml
services:
  app:
    mem_limit: 512m
    cpus: "0.5"
    network_mode: bridge
    restart: "no"
```

Docker Compose automatically picks up this file. It is regenerated on every deploy so it cannot be tampered with by the repo.

---

## 6. Frontend Changes

No new pages. All changes are within the existing dashboard view.

### Status badge → action button mapping

| Status | Badge | Available actions |
|---|---|---|
| `pending` | grey | Clone |
| `cloning` | blue + spinner | — |
| `cloned` | yellow | Deploy |
| `building` | blue + spinner | — |
| `running` | green | Stop, Restart, Update |
| `failed` | red | Clone (retry), Deploy (retry), Delete |
| `stopped` | grey | Deploy, Delete |

### New components

- **`LogDrawer.vue`** — slide-over panel (right side) that opens on project click. Shows a scrolling terminal-style log via SSE stream. Auto-closes when stream ends.
- **`StatusBadge.vue`** — extracts existing inline badge logic into a reusable component.

### SSE client (composable)
```ts
// composable: useProjectLogs(projectId)
const source = new EventSource(`/projects/${id}/logs`, {
  headers: { Authorization: `Bearer ${token}` }
})
source.onmessage = (e) => logs.value.push(e.data)
source.onerror = () => source.close()
```

### Status polling
The table polls `GET /projects` every 3 seconds while any project is in `cloning` or `building` state. Polling stops when all projects reach a terminal status.

### Repository requirements info block
A collapsible info block above the project table explains what a repo needs:
- A working `Dockerfile` or `docker-compose.yml`
- The app must listen on the port specified by `PORT` env var
- Optionally: `.env.example` for documentation

---

## 7. Security

- **URL validation:** `_SAFE_URL_RE` already rejects non-https URLs and shell metacharacters (unchanged).
- **No shell=True:** All subprocess calls use explicit argument lists — no command injection possible.
- **Override file:** `docker-compose.override.yml` is always regenerated by Launchpad before deploy, so the repo cannot override resource limits.
- **Port isolation:** Each project gets a unique port from 8001 upward; no two projects share a port.
- **No credential leakage:** `.env` files from repos are never read by Launchpad.

**Out of scope:** network policies between containers, image vulnerability scanning, per-user rate limiting.

---

## 8. Test Strategy

Existing 48 tests remain green. New tests:

### Unit tests

| File | Covers |
|---|---|
| `tests/test_project_store_sqlite.py` | CRUD via SQLite store, concurrent writes, status transitions |
| `tests/test_docker_service.py` *(extended)* | `compose_override` generation, resource limits present in override file |
| `tests/test_clone_validation.py` | Dockerfile/docker-compose.yml detection, invalid URL rejection |
| `tests/test_log_service.py` | LogLine write/read, ordering by timestamp |

### Integration tests

| File | Covers |
|---|---|
| `tests/test_clone_deploy_flow.py` | Clone → status `cloned`; Deploy → `building` → `running` (Docker mocked) |
| `tests/test_sse_logs.py` | SSE endpoint replays existing logs + streams new ones, closes on terminal status |
| `tests/test_status_transitions.py` | Invalid transitions rejected (e.g. deploy from `cloning`) |

### End-to-end (optional, manual)
```bash
RUN_E2E=1 pytest tests/e2e/
```
Clones a real public repo and deploys against a local Docker daemon. Only runs when `RUN_E2E=1` is set.

### Running tests after implementation
```bash
pytest -v                      # all unit + integration tests
pytest -v tests/test_sse*      # SSE-specific
RUN_E2E=1 pytest tests/e2e/    # optional e2e
```

---

## 9. Out of scope (future)

- Automatic log cleanup / retention policy
- Per-user resource quotas
- Network isolation between containers (requires gVisor or Kubernetes)
- Automatic vulnerability scanning of built images
- Multi-user project ownership
- Webhook-triggered redeploys (GitHub webhooks)
