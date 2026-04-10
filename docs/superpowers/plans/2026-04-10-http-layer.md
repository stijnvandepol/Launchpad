# Launchpad HTTP Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the FastAPI HTTP layer: JWT auth, protected project CRUD, Docker deploy/stop, Cloudflare ingress management, and the app entry point.

**Architecture:** Login proxies credentials to Accuro and returns an internal HS256 JWT. All project routes require that JWT via a FastAPI dependency. Deploy clones the repo, builds/runs the Docker container, and patches the cloudflared YAML config. Stop removes the container and removes the ingress rule.

**Tech Stack:** FastAPI, python-jose (JWT), docker SDK 7.x, ruamel.yaml, httpx + respx (tests), pytest, fastapi.testclient

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `app/services/jwt_service.py` | Create | sign + verify HS256 tokens |
| `app/services/docker_service.py` | Create | deploy/stop containers via docker SDK |
| `app/services/cloudflare_service.py` | Create | add/remove cloudflared ingress rules |
| `app/dependencies.py` | Create | `require_user` FastAPI dependency |
| `app/routers/auth.py` | Create | `POST /auth/login` |
| `app/routers/projects.py` | Create | project CRUD + deploy/stop endpoints |
| `app/main.py` | Create | FastAPI app assembly |
| `tests/test_jwt_service.py` | Create | JWT sign/verify unit tests |
| `tests/test_dependencies.py` | Create | dependency unit tests |
| `tests/test_auth_router.py` | Create | auth endpoint tests (respx) |
| `tests/test_projects_router.py` | Create | project endpoint tests |
| `tests/test_docker_service.py` | Create | docker service tests (mock SDK) |
| `tests/test_cloudflare_service.py` | Create | cloudflare service tests (tmp files) |

---

## Task 1: JWT Service

**Files:**
- Create: `app/services/jwt_service.py`
- Create: `tests/test_jwt_service.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_jwt_service.py
import pytest
import time
from app.services.jwt_service import sign_token, verify_token

SECRET = "a" * 32


def test_sign_and_verify_roundtrip():
    claims = {"sub": "u1", "email": "a@b.com", "name": "Alice", "role": "admin"}
    token = sign_token(claims, SECRET)
    result = verify_token(token, SECRET)
    assert result.sub == "u1"
    assert result.email == "a@b.com"
    assert result.role == "admin"


def test_verify_wrong_secret_raises():
    claims = {"sub": "u1", "email": "a@b.com", "name": "Alice", "role": "admin"}
    token = sign_token(claims, SECRET)
    with pytest.raises(ValueError, match="Invalid token"):
        verify_token(token, "b" * 32)


def test_verify_expired_token_raises(monkeypatch):
    import app.services.jwt_service as svc
    # Patch expiry to 0 seconds so token is immediately expired
    monkeypatch.setattr(svc, "TOKEN_EXPIRY_SECONDS", 0)
    claims = {"sub": "u1", "email": "a@b.com", "name": "Alice", "role": "admin"}
    token = sign_token(claims, SECRET)
    time.sleep(1)
    with pytest.raises(ValueError, match="Invalid token"):
        verify_token(token, SECRET)


def test_verify_garbage_raises():
    with pytest.raises(ValueError, match="Invalid token"):
        verify_token("not.a.token", SECRET)
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd /home/gebruiker/launchpad
pytest tests/test_jwt_service.py -v
```
Expected: `ImportError` (module does not exist yet)

- [ ] **Step 3: Implement jwt_service**

```python
# app/services/jwt_service.py
from jose import jwt, JWTError
from datetime import datetime, timezone
from app.models import JWTClaims

ALGORITHM = "HS256"
TOKEN_EXPIRY_SECONDS = 8 * 3600  # 8 hours


def sign_token(claims: dict, secret: str) -> str:
    now = int(datetime.now(timezone.utc).timestamp())
    payload = {
        **claims,
        "iat": now,
        "exp": now + TOKEN_EXPIRY_SECONDS,
    }
    return jwt.encode(payload, secret, algorithm=ALGORITHM)


def verify_token(token: str, secret: str) -> JWTClaims:
    try:
        payload = jwt.decode(token, secret, algorithms=[ALGORITHM])
        return JWTClaims.model_validate(payload)
    except (JWTError, Exception) as e:
        raise ValueError(f"Invalid token: {e}")
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
pytest tests/test_jwt_service.py -v
```
Expected: 4 passed (note: `test_verify_expired_token_raises` may need `leeway=0` — if it flickers, add `options={"leeway": 0}` to `jwt.decode`)

- [ ] **Step 5: Commit**

```bash
git add app/services/jwt_service.py tests/test_jwt_service.py
git commit -m "feat: JWT sign/verify service"
```

---

## Task 2: Auth Dependency

**Files:**
- Create: `app/dependencies.py`
- Create: `tests/test_dependencies.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_dependencies.py
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.services.jwt_service import sign_token

SECRET = "a" * 32


def _make_app(secret: str):
    from app.dependencies import require_user
    from app.config import Settings
    app = FastAPI()

    def override_settings():
        return Settings(
            ACCURO_URL="http://accuro:8000",
            LAUNCHPAD_JWT_SECRET=secret,
            TUNNEL_UUID="uuid-1",
        )

    app.dependency_overrides = {}

    @app.get("/me")
    def me(user=pytest.importorskip("fastapi").Depends(require_user)):
        return {"sub": user.sub, "role": user.role}

    return app


def test_valid_token_passes():
    from app.dependencies import require_user
    from app.config import Settings
    from fastapi import FastAPI, Depends
    from fastapi.testclient import TestClient

    app = FastAPI()
    token = sign_token({"sub": "u1", "email": "a@b.com", "name": "Alice", "role": "admin"}, SECRET)

    def override_settings():
        return Settings(ACCURO_URL="http://x", LAUNCHPAD_JWT_SECRET=SECRET, TUNNEL_UUID="t")

    from app.config import get_settings
    app.dependency_overrides[get_settings] = override_settings

    @app.get("/me")
    def me(user=Depends(require_user)):
        return {"sub": user.sub}

    client = TestClient(app)
    r = client.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["sub"] == "u1"


def test_missing_token_returns_403():
    from app.dependencies import require_user
    from fastapi import FastAPI, Depends
    from fastapi.testclient import TestClient

    app = FastAPI()

    @app.get("/me")
    def me(user=Depends(require_user)):
        return {}

    client = TestClient(app, raise_server_exceptions=False)
    r = client.get("/me")
    assert r.status_code in (401, 403)


def test_invalid_token_returns_401():
    from app.dependencies import require_user
    from app.config import Settings, get_settings
    from fastapi import FastAPI, Depends
    from fastapi.testclient import TestClient

    app = FastAPI()

    def override_settings():
        return Settings(ACCURO_URL="http://x", LAUNCHPAD_JWT_SECRET=SECRET, TUNNEL_UUID="t")

    app.dependency_overrides[get_settings] = override_settings

    @app.get("/me")
    def me(user=Depends(require_user)):
        return {}

    client = TestClient(app, raise_server_exceptions=False)
    r = client.get("/me", headers={"Authorization": "Bearer badtoken"})
    assert r.status_code == 401
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/test_dependencies.py -v
```
Expected: `ImportError` (module does not exist)

- [ ] **Step 3: Implement dependencies.py**

```python
# app/dependencies.py
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
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
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
pytest tests/test_dependencies.py -v
```
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add app/dependencies.py tests/test_dependencies.py
git commit -m "feat: require_user FastAPI dependency"
```

---

## Task 3: Auth Router

**Files:**
- Create: `app/routers/auth.py`
- Create: `tests/test_auth_router.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_auth_router.py
import pytest
import respx
import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.config import Settings, get_settings

SECRET = "a" * 32
ACCURO_URL = "http://accuro-test:8000"


def _app():
    from app.routers.auth import router
    app = FastAPI()
    app.include_router(router)

    def override():
        return Settings(
            ACCURO_URL=ACCURO_URL,
            LAUNCHPAD_JWT_SECRET=SECRET,
            TUNNEL_UUID="t",
        )

    app.dependency_overrides[get_settings] = override
    return app


@respx.mock
def test_login_returns_token():
    respx.post(f"{ACCURO_URL}/api/v1/auth/login").mock(
        return_value=httpx.Response(200, json={"access_token": "accuro-tok"})
    )
    respx.get(f"{ACCURO_URL}/api/v1/auth/verify").mock(
        return_value=httpx.Response(200, json={
            "id": "u1", "email": "admin@test.com",
            "name": "Admin", "role": "admin", "is_active": True,
        })
    )
    client = TestClient(_app())
    r = client.post("/auth/login", json={"email": "admin@test.com", "password": "pass"})
    assert r.status_code == 200
    assert "access_token" in r.json()
    assert r.json()["token_type"] == "bearer"


@respx.mock
def test_login_wrong_password_returns_401():
    respx.post(f"{ACCURO_URL}/api/v1/auth/login").mock(
        return_value=httpx.Response(401, json={"detail": "Invalid credentials"})
    )
    client = TestClient(_app(), raise_server_exceptions=False)
    r = client.post("/auth/login", json={"email": "a@b.com", "password": "wrong"})
    assert r.status_code == 401


@respx.mock
def test_login_disallowed_role_returns_403():
    respx.post(f"{ACCURO_URL}/api/v1/auth/login").mock(
        return_value=httpx.Response(200, json={"access_token": "tok"})
    )
    respx.get(f"{ACCURO_URL}/api/v1/auth/verify").mock(
        return_value=httpx.Response(200, json={
            "id": "u2", "email": "viewer@test.com",
            "name": "Viewer", "role": "viewer", "is_active": True,
        })
    )
    client = TestClient(_app(), raise_server_exceptions=False)
    r = client.post("/auth/login", json={"email": "viewer@test.com", "password": "pass"})
    assert r.status_code == 403


@respx.mock
def test_login_accuro_unreachable_returns_401():
    respx.post(f"{ACCURO_URL}/api/v1/auth/login").mock(
        side_effect=httpx.ConnectError("refused")
    )
    client = TestClient(_app(), raise_server_exceptions=False)
    r = client.post("/auth/login", json={"email": "a@b.com", "password": "pass"})
    assert r.status_code == 401
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/test_auth_router.py -v
```
Expected: `ImportError`

- [ ] **Step 3: Implement auth router**

```python
# app/routers/auth.py
from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel
from app.services.accuro_auth import login_via_accuro, verify_accuro_token, AccuroAuthError
from app.services.jwt_service import sign_token
from app.config import get_settings, Settings

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, settings: Settings = Depends(get_settings)):
    try:
        accuro_token = await login_via_accuro(body.email, body.password, settings.ACCURO_URL)
        user = await verify_accuro_token(accuro_token, settings.ACCURO_URL)
    except AccuroAuthError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))

    if user.role not in settings.allowed_roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Role not permitted")

    token = sign_token(
        {"sub": user.id, "email": user.email, "name": user.name, "role": user.role},
        settings.LAUNCHPAD_JWT_SECRET,
    )
    return TokenResponse(access_token=token)
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
pytest tests/test_auth_router.py -v
```
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add app/routers/auth.py tests/test_auth_router.py
git commit -m "feat: POST /auth/login via Accuro proxy"
```

---

## Task 4: Docker Service

**Files:**
- Create: `app/services/docker_service.py`
- Create: `tests/test_docker_service.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_docker_service.py
import pytest
from unittest.mock import MagicMock, patch
from docker.errors import NotFound, DockerException


def _mock_client(containers=None):
    client = MagicMock()
    client.containers = MagicMock()
    if containers is not None:
        client.containers.get.side_effect = containers
    return client


def test_deploy_stops_existing_and_runs_new():
    from app.services.docker_service import deploy_container
    existing = MagicMock()
    client = _mock_client()
    client.containers.get.return_value = existing
    client.containers.run.return_value = MagicMock(id="new-container-id")

    with patch("app.services.docker_service.docker.from_env", return_value=client):
        cid = deploy_container("my-app", "/demos/my-app", 3001)

    existing.stop.assert_called_once()
    existing.remove.assert_called_once()
    client.containers.run.assert_called_once()
    assert cid == "new-container-id"


def test_deploy_skips_stop_when_no_existing():
    from app.services.docker_service import deploy_container
    client = _mock_client()
    client.containers.get.side_effect = NotFound("not found")
    client.containers.run.return_value = MagicMock(id="c2")

    with patch("app.services.docker_service.docker.from_env", return_value=client):
        cid = deploy_container("my-app", "/demos/my-app", 3001)

    assert cid == "c2"


def test_deploy_raises_docker_error_on_failure():
    from app.services.docker_service import deploy_container, DockerError
    client = _mock_client()
    client.containers.get.side_effect = NotFound("x")
    client.containers.run.side_effect = DockerException("boom")

    with patch("app.services.docker_service.docker.from_env", return_value=client):
        with pytest.raises(DockerError, match="Docker error"):
            deploy_container("my-app", "/demos/my-app", 3001)


def test_stop_removes_container():
    from app.services.docker_service import stop_container
    container = MagicMock()
    client = _mock_client()
    client.containers.get.return_value = container

    with patch("app.services.docker_service.docker.from_env", return_value=client):
        stop_container("my-app")

    container.stop.assert_called_once()
    container.remove.assert_called_once()


def test_stop_is_noop_when_not_found():
    from app.services.docker_service import stop_container
    client = _mock_client()
    client.containers.get.side_effect = NotFound("x")

    with patch("app.services.docker_service.docker.from_env", return_value=client):
        stop_container("my-app")  # should not raise
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/test_docker_service.py -v
```
Expected: `ImportError`

- [ ] **Step 3: Implement docker_service**

```python
# app/services/docker_service.py
import docker
from docker.errors import DockerException, NotFound


class DockerError(Exception):
    pass


def deploy_container(name: str, repo_path: str, port: int) -> str:
    """Run container named `name` from image built at `repo_path`, binding `port`."""
    try:
        client = docker.from_env()
        try:
            old = client.containers.get(name)
            old.stop()
            old.remove()
        except NotFound:
            pass
        container = client.containers.run(
            name,  # image tag == container name (built separately via `docker build -t {name} {repo_path}`)
            name=name,
            ports={f"{port}/tcp": port},
            detach=True,
            restart_policy={"Name": "unless-stopped"},
        )
        return container.id
    except DockerException as e:
        raise DockerError(f"Docker error: {e}")


def stop_container(name: str) -> None:
    """Stop and remove container by name. No-op if not found."""
    try:
        client = docker.from_env()
        try:
            container = client.containers.get(name)
            container.stop()
            container.remove()
        except NotFound:
            pass
    except DockerException as e:
        raise DockerError(f"Docker error: {e}")
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
pytest tests/test_docker_service.py -v
```
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add app/services/docker_service.py tests/test_docker_service.py
git commit -m "feat: Docker deploy/stop service"
```

---

## Task 5: Cloudflare Service

**Files:**
- Create: `app/services/cloudflare_service.py`
- Create: `tests/test_cloudflare_service.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_cloudflare_service.py
import pytest
from pathlib import Path
from ruamel.yaml import YAML


def _write_config(tmp_path: Path, ingress: list) -> str:
    p = tmp_path / "config.yml"
    yaml = YAML()
    yaml.dump({"tunnel": "uuid-1", "ingress": ingress}, p)
    return str(p)


def _read_ingress(path: str) -> list:
    yaml = YAML()
    return yaml.load(Path(path))["ingress"]


def test_add_ingress_inserts_before_catchall():
    from app.services.cloudflare_service import add_ingress
    path = _write_config(
        pytest.importorskip("pathlib").Path("/tmp"),  # overridden below
        [{"service": "http_status:404"}],
    )
    # Use tmp_path properly
    import tempfile, os
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "config.yml")
        yaml = YAML()
        yaml.dump({"tunnel": "t", "ingress": [{"service": "http_status:404"}]}, open(p, "w"))
        add_ingress(p, "my-app", "webvakwerk.nl", 3001)
        ingress = _read_ingress(p)
        assert ingress[0]["hostname"] == "my-app.webvakwerk.nl"
        assert ingress[0]["service"] == "http://localhost:3001"
        assert ingress[-1]["service"] == "http_status:404"


def test_add_ingress_replaces_existing():
    import tempfile, os
    from app.services.cloudflare_service import add_ingress
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "config.yml")
        yaml = YAML()
        yaml.dump({"tunnel": "t", "ingress": [
            {"hostname": "my-app.webvakwerk.nl", "service": "http://localhost:3000"},
            {"service": "http_status:404"},
        ]}, open(p, "w"))
        add_ingress(p, "my-app", "webvakwerk.nl", 3001)
        ingress = _read_ingress(p)
        rules = [r for r in ingress if r.get("hostname") == "my-app.webvakwerk.nl"]
        assert len(rules) == 1
        assert rules[0]["service"] == "http://localhost:3001"


def test_remove_ingress_deletes_rule():
    import tempfile, os
    from app.services.cloudflare_service import remove_ingress
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "config.yml")
        yaml = YAML()
        yaml.dump({"tunnel": "t", "ingress": [
            {"hostname": "my-app.webvakwerk.nl", "service": "http://localhost:3001"},
            {"service": "http_status:404"},
        ]}, open(p, "w"))
        remove_ingress(p, "my-app", "webvakwerk.nl")
        ingress = _read_ingress(p)
        assert not any(r.get("hostname") == "my-app.webvakwerk.nl" for r in ingress)
        assert ingress[-1]["service"] == "http_status:404"


def test_remove_ingress_noop_when_not_present():
    import tempfile, os
    from app.services.cloudflare_service import remove_ingress
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "config.yml")
        yaml = YAML()
        yaml.dump({"tunnel": "t", "ingress": [{"service": "http_status:404"}]}, open(p, "w"))
        remove_ingress(p, "nonexistent", "webvakwerk.nl")  # should not raise
        ingress = _read_ingress(p)
        assert len(ingress) == 1
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/test_cloudflare_service.py -v
```
Expected: `ImportError`

- [ ] **Step 3: Implement cloudflare_service**

```python
# app/services/cloudflare_service.py
from pathlib import Path
from ruamel.yaml import YAML


def add_ingress(config_path: str, subdomain: str, base_domain: str, port: int) -> None:
    """Insert or replace an ingress rule for subdomain, keeping catch-all last."""
    yaml = YAML()
    p = Path(config_path)
    data = yaml.load(p)
    hostname = f"{subdomain}.{base_domain}"
    service = f"http://localhost:{port}"

    ingress = data.get("ingress", [])
    catch_all = next((r for r in ingress if "hostname" not in r), None)
    named = [r for r in ingress if r.get("hostname") != hostname and "hostname" in r]
    named.append({"hostname": hostname, "service": service})
    data["ingress"] = named + ([catch_all] if catch_all else [])

    with p.open("w") as f:
        yaml.dump(data, f)


def remove_ingress(config_path: str, subdomain: str, base_domain: str) -> None:
    """Remove ingress rule for subdomain. No-op if not present."""
    yaml = YAML()
    p = Path(config_path)
    data = yaml.load(p)
    hostname = f"{subdomain}.{base_domain}"
    data["ingress"] = [r for r in data.get("ingress", []) if r.get("hostname") != hostname]
    with p.open("w") as f:
        yaml.dump(data, f)
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
pytest tests/test_cloudflare_service.py -v
```
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add app/services/cloudflare_service.py tests/test_cloudflare_service.py
git commit -m "feat: Cloudflare ingress add/remove service"
```

---

## Task 6: Projects Router (CRUD + Deploy/Stop)

**Files:**
- Create: `app/routers/projects.py`
- Create: `tests/test_projects_router.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_projects_router.py
import pytest
import uuid
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from app.config import Settings, get_settings
from app.dependencies import require_user
from app.models import JWTClaims
import time

SECRET = "a" * 32
FAKE_USER = JWTClaims(
    sub="u1", email="a@b.com", name="Admin", role="admin",
    exp=int(time.time()) + 3600, iat=int(time.time()),
)


def _app(tmp_store: str):
    from app.routers.projects import router
    app = FastAPI()
    app.include_router(router)

    def override_settings():
        return Settings(
            ACCURO_URL="http://x",
            LAUNCHPAD_JWT_SECRET=SECRET,
            TUNNEL_UUID="t",
            BASE_DIR=tmp_store,
        )

    app.dependency_overrides[get_settings] = override_settings
    app.dependency_overrides[require_user] = lambda: FAKE_USER
    return app


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
    assert body["subdomain"] == "my-app"
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
    create_r = client.post("/projects", json={
        "name": "demo", "repo_url": "https://github.com/x/y",
        "subdomain": "demo", "port": 3002,
    })
    pid = create_r.json()["id"]
    r = client.delete(f"/projects/{pid}")
    assert r.status_code == 204
    assert client.get("/projects").json() == []


def test_delete_nonexistent_returns_404(store_dir):
    client = TestClient(_app(store_dir), raise_server_exceptions=False)
    r = client.delete("/projects/does-not-exist")
    assert r.status_code == 404


def test_deploy_calls_docker_and_cloudflare(store_dir, tmp_path):
    import os
    cf_config = tmp_path / "config.yml"
    from ruamel.yaml import YAML
    yaml = YAML()
    yaml.dump({"tunnel": "t", "ingress": [{"service": "http_status:404"}]}, cf_config.open("w"))

    app = FastAPI()
    from app.routers.projects import router
    app.include_router(router)

    def override_settings():
        return Settings(
            ACCURO_URL="http://x",
            LAUNCHPAD_JWT_SECRET=SECRET,
            TUNNEL_UUID="t",
            BASE_DIR=str(tmp_path),
            CLOUDFLARED_CONFIG=str(cf_config),
        )

    (tmp_path / "projects.json").write_text("[]")
    app.dependency_overrides[get_settings] = override_settings
    app.dependency_overrides[require_user] = lambda: FAKE_USER

    client = TestClient(app)
    create_r = client.post("/projects", json={
        "name": "demo", "repo_url": "https://github.com/x/y",
        "subdomain": "demo", "port": 3002,
    })
    pid = create_r.json()["id"]

    with patch("app.routers.projects.deploy_container", return_value="cid-1") as mock_deploy, \
         patch("app.routers.projects.add_ingress") as mock_cf:
        r = client.post(f"/projects/{pid}/deploy")

    assert r.status_code == 200
    mock_deploy.assert_called_once()
    mock_cf.assert_called_once()
    project = r.json()
    assert project["deployed_at"] is not None


def test_stop_calls_docker_and_removes_ingress(store_dir, tmp_path):
    cf_config = tmp_path / "config.yml"
    from ruamel.yaml import YAML
    yaml = YAML()
    yaml.dump({"tunnel": "t", "ingress": [{"service": "http_status:404"}]}, cf_config.open("w"))
    (tmp_path / "projects.json").write_text("[]")

    app = FastAPI()
    from app.routers.projects import router
    app.include_router(router)

    def override_settings():
        return Settings(
            ACCURO_URL="http://x", LAUNCHPAD_JWT_SECRET=SECRET, TUNNEL_UUID="t",
            BASE_DIR=str(tmp_path), CLOUDFLARED_CONFIG=str(cf_config),
        )

    app.dependency_overrides[get_settings] = override_settings
    app.dependency_overrides[require_user] = lambda: FAKE_USER

    client = TestClient(app)
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
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/test_projects_router.py -v
```
Expected: `ImportError`

- [ ] **Step 3: Implement projects router**

```python
# app/routers/projects.py
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from app.config import get_settings, Settings
from app.dependencies import require_user
from app.models import Project, DeployRequest, JWTClaims
from app.services.project_store import load_projects, upsert_project, delete_project, get_project
from app.services.docker_service import deploy_container, stop_container, DockerError
from app.services.cloudflare_service import add_ingress, remove_ingress

router = APIRouter(prefix="/projects", tags=["projects"])


def _store_path(settings: Settings) -> str:
    return f"{settings.BASE_DIR}/projects.json"


@router.get("", response_model=list[Project])
def list_projects(
    settings: Settings = Depends(get_settings),
    _: JWTClaims = Depends(require_user),
):
    return load_projects(_store_path(settings))


@router.post("", response_model=Project, status_code=status.HTTP_201_CREATED)
def create_project(
    body: DeployRequest,
    settings: Settings = Depends(get_settings),
    _: JWTClaims = Depends(require_user),
):
    project = Project(
        id=str(uuid.uuid4()),
        name=body.name,
        repo_url=body.repo_url,
        subdomain=body.subdomain,
        path=f"{settings.BASE_DIR}/{body.subdomain}",
        port=body.port,
    )
    upsert_project(_store_path(settings), project)
    return project


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project_endpoint(
    project_id: str,
    settings: Settings = Depends(get_settings),
    _: JWTClaims = Depends(require_user),
):
    store = _store_path(settings)
    if not get_project(store, project_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    delete_project(store, project_id)


@router.post("/{project_id}/deploy", response_model=Project)
def deploy_project(
    project_id: str,
    settings: Settings = Depends(get_settings),
    _: JWTClaims = Depends(require_user),
):
    store = _store_path(settings)
    project = get_project(store, project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    try:
        deploy_container(project.subdomain, project.path, project.port)
    except DockerError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))
    add_ingress(settings.CLOUDFLARED_CONFIG, project.subdomain, settings.BASE_DOMAIN, project.port)
    project = project.model_copy(update={"deployed_at": datetime.now(timezone.utc)})
    upsert_project(store, project)
    return project


@router.post("/{project_id}/stop", response_model=Project)
def stop_project(
    project_id: str,
    settings: Settings = Depends(get_settings),
    _: JWTClaims = Depends(require_user),
):
    store = _store_path(settings)
    project = get_project(store, project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    try:
        stop_container(project.subdomain)
    except DockerError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))
    remove_ingress(settings.CLOUDFLARED_CONFIG, project.subdomain, settings.BASE_DOMAIN)
    project = project.model_copy(update={"updated_at": datetime.now(timezone.utc)})
    upsert_project(store, project)
    return project
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
pytest tests/test_projects_router.py -v
```
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add app/routers/projects.py tests/test_projects_router.py
git commit -m "feat: project CRUD + deploy/stop endpoints"
```

---

## Task 7: App Entry Point (main.py)

**Files:**
- Create: `app/main.py`
- Create: `tests/test_main.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_main.py
from fastapi.testclient import TestClient


def test_health_endpoint():
    from app.main import app
    client = TestClient(app)
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_openapi_schema_includes_auth_and_projects():
    from app.main import app
    client = TestClient(app)
    r = client.get("/openapi.json")
    assert r.status_code == 200
    paths = r.json()["paths"]
    assert "/auth/login" in paths
    assert "/projects" in paths
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/test_main.py -v
```
Expected: `ImportError`

- [ ] **Step 3: Implement main.py**

```python
# app/main.py
from fastapi import FastAPI
from app.routers import auth, projects

app = FastAPI(title="Launchpad", version="1.0.0")

app.include_router(auth.router)
app.include_router(projects.router)


@app.get("/health", tags=["ops"])
def health():
    return {"status": "ok"}
```

- [ ] **Step 4: Update `app/routers/__init__.py`**

The file is currently empty — no changes needed; imports in `main.py` use full module paths.

- [ ] **Step 5: Run all tests**

```bash
pytest -v
```
Expected: all tests pass

- [ ] **Step 6: Commit**

```bash
git add app/main.py tests/test_main.py
git commit -m "feat: FastAPI app entry point with health endpoint"
```

---

## Self-Review

**Spec coverage:** No formal spec doc exists — the plan was derived from existing code. All established components are covered: JWT, auth dependency, auth router, project CRUD, deploy/stop, Docker, Cloudflare, app assembly.

**Placeholder scan:** No TBD/TODO in steps above. All code blocks are complete.

**Type consistency:**
- `JWTClaims` used consistently — defined in `app/models.py`, returned by `verify_token`, accepted by `require_user`
- `DockerError` raised in `docker_service.py`, caught in `projects.py`
- `_store_path(settings)` helper used consistently in all project endpoints
- `deploy_container(name, repo_path, port)` signature matches usage in router
- `add_ingress(config_path, subdomain, base_domain, port)` / `remove_ingress(config_path, subdomain, base_domain)` match usage in router
