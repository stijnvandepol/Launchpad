# app/routers/projects.py
import logging
import os
import re
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
    _run_streaming, validate_repo, write_compose_override, strip_host_ports,
    deploy_project, stop_project, teardown_project, project_status, pull_repo, DockerError,
    CONTAINER_DEFAULT_PORT, detect_container_port,
)
from app.services.cloudflare_service import add_ingress, remove_ingress, create_dns_record, delete_dns_record, CloudflareAPIError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/projects", tags=["projects"])


def _store_path(settings: Settings) -> str:
    return f"{settings.BASE_DIR}/projects.db"


def _safe_remove_ingress(settings: Settings, subdomain: str) -> None:
    """Remove ingress rule and DNS record, logging any failure without raising."""
    try:
        remove_ingress(
            settings.CF_ACCOUNT_ID, settings.TUNNEL_UUID, settings.CF_API_TOKEN,
            subdomain, settings.BASE_DOMAIN,
        )
    except CloudflareAPIError as e:
        logger.warning("cloudflare: remove_ingress failed for %s: %s", subdomain, e)
    except Exception as e:
        logger.warning("cloudflare: unexpected error removing ingress for %s: %s", subdomain, e)
    try:
        delete_dns_record(
            settings.CF_ZONE_ID, subdomain, settings.BASE_DOMAIN, settings.CF_API_TOKEN,
        )
    except CloudflareAPIError as e:
        logger.warning("cloudflare: delete_dns_record failed for %s: %s", subdomain, e)
    except Exception as e:
        logger.warning("cloudflare: unexpected error deleting DNS for %s: %s", subdomain, e)


def _get_or_404(store: str, project_id: str) -> Project:
    p = get_project(store, project_id)
    if not p:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return p


def _to_response(p: Project, live_status: ProjectStatus | None = None) -> ProjectResponse:
    return ProjectResponse(
        id=p.id, name=p.name, repo_url=p.repo_url, subdomain=p.subdomain,
        path=p.path, port=p.port, container_port=p.container_port,
        status=live_status if live_status is not None else p.status,
        error=p.error, deployed_at=p.deployed_at, updated_at=p.updated_at,
    )


# ── Background task functions ────────────────────────────────────────────────


def _sanitize_log(line: str, github_pat: str | None) -> str:
    """Remove PAT from log output to prevent credential leakage."""
    if github_pat:
        line = line.replace(github_pat, "***")
    return line


def _do_clone(project_id: str, repo_url: str, path: str, store: str, github_pat: str | None = None) -> None:
    update_project_status(store, project_id, ProjectStatus.cloning)
    append_log(store, project_id, f"=== Clone started: {repo_url} ===")
    try:
        if os.path.exists(path):
            shutil.rmtree(path)
        clone_url = repo_url.replace("https://", f"https://{github_pat}@", 1) if github_pat else repo_url
        try:
            for line in _run_streaming(["git", "clone", clone_url, path], timeout=120):
                append_log(store, project_id, _sanitize_log(line, github_pat))
        except DockerError:
            if not github_pat:
                raise
            # PAT failed — retry without (works for public repos)
            append_log(store, project_id, "Auth failed, retrying without token...")
            if os.path.exists(path):
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
    update_project_status(store, project_id, ProjectStatus.building)
    append_log(store, project_id, f"=== Deploy started (port {port}) ===")
    try:
        strip_host_ports(path)
        p_pre = get_project(store, project_id)
        container_port = p_pre.container_port if p_pre else CONTAINER_DEFAULT_PORT
        # Auto-detect from repo files when still at the default — handles apps that
        # expose a non-8080 port (e.g. nginx on 80) without requiring manual input.
        if container_port == CONTAINER_DEFAULT_PORT:
            detected = detect_container_port(path)
            if detected != CONTAINER_DEFAULT_PORT:
                container_port = detected
                logger.info("auto-detected container port %d for project %s", container_port, project_id)
        write_compose_override(path, port, container_port)
        for line in _run_streaming(
            ["docker", "compose", "up", "-d", "--build"],
            cwd=path,
            timeout=600,
        ):
            append_log(store, project_id, line)
        try:
            add_ingress(settings.CF_ACCOUNT_ID, settings.TUNNEL_UUID, settings.CF_API_TOKEN, subdomain, settings.BASE_DOMAIN, port)
        except CloudflareAPIError as e:
            logger.warning("cloudflare: add_ingress failed for %s: %s", subdomain, e)
            append_log(store, project_id, f"WARNING: cloudflare ingress failed: {e}")
        except Exception as e:
            logger.warning("cloudflare: unexpected error adding ingress for %s: %s", subdomain, e)
            append_log(store, project_id, f"WARNING: cloudflare ingress error: {type(e).__name__}: {e}")
        try:
            create_dns_record(settings.CF_ZONE_ID, subdomain, settings.BASE_DOMAIN, settings.TUNNEL_UUID, settings.CF_API_TOKEN)
        except CloudflareAPIError as e:
            logger.warning("cloudflare: create_dns_record failed for %s: %s", subdomain, e)
            append_log(store, project_id, f"WARNING: cloudflare DNS failed: {e}")
        except Exception as e:
            logger.warning("cloudflare: unexpected error creating DNS for %s: %s", subdomain, e)
            append_log(store, project_id, f"WARNING: cloudflare DNS error: {type(e).__name__}: {e}")
        p = get_project(store, project_id)
        if p:
            p = p.model_copy(update={"deployed_at": datetime.now(timezone.utc)})
            upsert_project(store, p)
        append_log(store, project_id, "=== Deploy complete ===")
        update_project_status(store, project_id, ProjectStatus.running)
    except DockerError as e:
        append_log(store, project_id, f"ERROR: {e}")
        update_project_status(store, project_id, ProjectStatus.failed, str(e))


def _do_update(project_id: str, path: str, port: int, subdomain: str, store: str, settings: Settings) -> None:
    update_project_status(store, project_id, ProjectStatus.building)
    append_log(store, project_id, "=== Update started (git pull + redeploy) ===")
    try:
        for line in _run_streaming(["git", "pull"], cwd=path, timeout=120):
            append_log(store, project_id, line)
        teardown_project(path)
        _do_deploy(project_id, path, port, subdomain, store, settings)
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
                    result.append(_to_response(p, ProjectStatus.stopped))
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
        container_port=body.container_port,
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
        _do_clone, project.id, project.repo_url, project.path, store, settings.GITHUB_PAT,
    )
    return _to_response(project, ProjectStatus.cloning)


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
    return _to_response(project, ProjectStatus.building)


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
    _safe_remove_ingress(settings, project.subdomain)
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
        teardown_project(project.path)
    except DockerError:
        pass
    _safe_remove_ingress(settings, project.subdomain)
    update_project_status(store, project.id, ProjectStatus.stopped)
    background_tasks.add_task(
        _do_deploy, project.id, project.path, project.port,
        project.subdomain, store, settings,
    )
    return _to_response(get_project(store, project.id), ProjectStatus.building)


@router.post("/{project_id}/update", response_model=ProjectResponse)
def update_project_endpoint(
    project_id: str,
    background_tasks: BackgroundTasks,
    settings: Settings = Depends(get_settings),
    _: JWTClaims = Depends(require_user),
):
    store = _store_path(settings)
    project = _get_or_404(store, project_id)
    background_tasks.add_task(
        _do_update, project.id, project.path, project.port,
        project.subdomain, store, settings,
    )
    return _to_response(project, ProjectStatus.building)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project_endpoint(
    project_id: str,
    settings: Settings = Depends(get_settings),
    _: JWTClaims = Depends(require_user),
):
    store = _store_path(settings)
    project = _get_or_404(store, project_id)
    try:
        teardown_project(project.path)
    except DockerError:
        pass
    _safe_remove_ingress(settings, project.subdomain)
    if os.path.exists(project.path):
        shutil.rmtree(project.path)
    delete_project(store, project_id)


@router.get("/{project_id}/logs")
async def logs_endpoint(
    project_id: str,
    settings: Settings = Depends(get_settings),
    _: JWTClaims = Depends(require_user_sse),
):
    store = _store_path(settings)
    _get_or_404(store, project_id)

    async def event_generator():
        existing = get_logs(store, project_id)
        last_id = 0
        for log in existing:
            yield {"data": log.text}
            last_id = log.id

        terminal = {ProjectStatus.running, ProjectStatus.failed, ProjectStatus.stopped}
        while True:
            await asyncio.sleep(0.5)
            p = get_project(store, project_id)
            new_lines = get_logs_after(store, project_id, last_id)
            for log in new_lines:
                yield {"data": log.text}
                last_id = log.id
            if p is None or p.status in terminal:
                yield {"event": "done", "data": ""}
                break

    return EventSourceResponse(event_generator())
