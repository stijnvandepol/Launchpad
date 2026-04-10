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
