# app/routers/projects.py
import logging
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from app.config import get_settings, Settings
from app.dependencies import require_user
from app.models import Project, ProjectResponse, DeployRequest, JWTClaims
from app.services.project_store import load_projects, upsert_project, delete_project, get_project
from app.services.docker_service import (
    clone_repo, pull_repo, deploy_project, stop_project, project_status, DockerError,
)
from app.services.cloudflare_service import add_ingress, remove_ingress

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects", tags=["projects"])


def _store_path(settings: Settings) -> str:
    return f"{settings.BASE_DIR}/projects.json"


_PORT_START = 8001


def _get_or_404(store: str, project_id: str) -> Project:
    project = get_project(store, project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


def _next_port(store: str) -> int:
    """Find the lowest available port starting from _PORT_START."""
    used = {p.port for p in load_projects(store)}
    port = _PORT_START
    while port in used:
        port += 1
    return port


# --- LIST / CREATE / DELETE ---


@router.get("", response_model=list[ProjectResponse])
def list_projects(
    settings: Settings = Depends(get_settings),
    _: JWTClaims = Depends(require_user),
):
    projects = load_projects(_store_path(settings))
    result = []
    for p in projects:
        try:
            ps = project_status(p.path)
        except DockerError:
            ps = "stopped"
        result.append(ProjectResponse(**p.model_dump(), status=ps))
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
        port=_next_port(store),
    )
    upsert_project(store, project)
    return ProjectResponse(**project.model_dump(), status="stopped")


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
    delete_project(store, project_id)


# --- DEPLOY / STOP / UPDATE ---


@router.post("/{project_id}/deploy", response_model=ProjectResponse)
def deploy_project_endpoint(
    project_id: str,
    settings: Settings = Depends(get_settings),
    _: JWTClaims = Depends(require_user),
):
    store = _store_path(settings)
    project = _get_or_404(store, project_id)
    try:
        clone_repo(project.repo_url, project.path)
        deploy_project(project.path, project.port)
    except DockerError as e:
        logger.error("Deploy failed for %s: %s", project.subdomain, e)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))
    try:
        add_ingress(settings.CLOUDFLARED_CONFIG, project.subdomain, settings.BASE_DOMAIN, project.port)
    except Exception as e:
        logger.error("Ingress failed for %s: %s", project.subdomain, e)
    project = project.model_copy(update={"deployed_at": datetime.now(timezone.utc)})
    upsert_project(store, project)
    return ProjectResponse(**project.model_dump(), status="running")


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
        logger.error("Stop failed for %s: %s", project.subdomain, e)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))
    try:
        remove_ingress(settings.CLOUDFLARED_CONFIG, project.subdomain, settings.BASE_DOMAIN)
    except Exception as e:
        logger.error("Remove ingress failed for %s: %s", project.subdomain, e)
    project = project.model_copy(update={"updated_at": datetime.now(timezone.utc)})
    upsert_project(store, project)
    return ProjectResponse(**project.model_dump(), status="stopped")


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
        logger.error("Update failed for %s: %s", project.subdomain, e)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))
    project = project.model_copy(update={"updated_at": datetime.now(timezone.utc)})
    upsert_project(store, project)
    return ProjectResponse(**project.model_dump(), status="running")
