# Launchpad

A self-hosted demo deployment platform. Point it at a git repo, and it deploys the app as a Docker container with a live subdomain on your Cloudflare Tunnel — no manual DNS, no port forwarding.

## How it works

```
POST /auth/login  →  Accuro validates credentials  →  Launchpad issues JWT
POST /projects    →  Register a project
POST /projects/{id}/deploy  →  Docker runs the container, Cloudflare routes subdomain.yourdomain.nl → port
POST /projects/{id}/stop    →  Container stopped, ingress rule removed
```

Authentication is delegated to [Accuro](https://github.com/stijnvandepol/accuro). Launchpad issues its own short-lived JWT after Accuro validates the login. All project endpoints require this token.

## Requirements

- Python 3.12+
- Docker (socket accessible at `/var/run/docker.sock`)
- [cloudflared](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/) running with a named tunnel
- A running Accuro instance

## Setup

### Docker Compose (recommended)

```bash
cp .env.example .env   # fill in your values
docker compose up -d
```

This starts Launchpad and cloudflared together. Launchpad gets access to the Docker socket so it can manage containers on the host.

### Manual

```bash
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --host 0.0.0.0 --port 8080
```

### Environment variables

| Variable | Description | Default |
|---|---|---|
| `ACCURO_URL` | Base URL of your Accuro instance | — |
| `ACCURO_ALLOWED_ROLES` | Comma-separated roles that may log in | `admin` |
| `LAUNCHPAD_JWT_SECRET` | HS256 signing secret (min 32 chars) | — |
| `TUNNEL_UUID` | UUID of your Cloudflare tunnel | — |
| `BASE_DOMAIN` | Domain for subdomains (e.g. `webvakwerk.nl`) | `webvakwerk.nl` |
| `BASE_DIR` | Root directory where projects are stored | `/demos` |
| `CLOUDFLARED_CONFIG` | Path to cloudflared `config.yml` | `/cloudflared/config.yml` |
| `PORT` | Port Launchpad listens on | `8080` |

## API

### Auth

```http
POST /auth/login
Content-Type: application/json

{ "email": "admin@example.com", "password": "..." }
```

Returns `{ "access_token": "...", "token_type": "bearer" }`. Pass this as `Authorization: Bearer <token>` on all other requests.

### Projects

```http
GET    /projects                  # List all projects
POST   /projects                  # Register a new project
DELETE /projects/{id}             # Remove a project
POST   /projects/{id}/deploy      # Deploy (Docker run + Cloudflare ingress)
POST   /projects/{id}/stop        # Stop (Docker stop + remove ingress)
```

**Create payload:**
```json
{
  "name": "my-app",
  "repo_url": "https://github.com/you/my-app",
  "subdomain": "my-app",
  "port": 3001
}
```

After deploying, the app is reachable at `https://my-app.webvakwerk.nl`.

### Health

```http
GET /health  →  { "status": "ok" }
```

Interactive docs available at `/docs`.

## Project structure

```
app/
├── main.py                  # FastAPI app entry point
├── config.py                # Pydantic settings
├── models.py                # Pydantic models
├── dependencies.py          # require_user JWT dependency
├── routers/
│   ├── auth.py              # Login endpoint
│   └── projects.py          # Project CRUD + deploy/stop
└── services/
    ├── accuro_auth.py        # Accuro HTTP client
    ├── jwt_service.py        # HS256 sign/verify
    ├── project_store.py      # Atomic JSON file store
    ├── docker_service.py     # Docker SDK wrapper
    └── cloudflare_service.py # cloudflared config management
tests/
data/
    projects.json            # Persistent project store
```

## Running tests

```bash
pytest -v
```

48 tests, no external dependencies required (Docker and Cloudflare calls are mocked).

## Deploy flow in detail

1. `POST /projects/{id}/deploy` is called
2. `deploy_container(subdomain, path, port)` — stops any existing container with the same name, then runs the image (pre-built as `docker build -t {subdomain} {path}`)
3. `add_ingress(config_path, subdomain, base_domain, port)` — upserts the ingress rule in cloudflared's `config.yml`, keeping the catch-all rule last
4. `deployed_at` is set on the project and saved to the store

Stopping reverses steps 2 and 3.
