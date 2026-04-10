# app/routers/projects.py
import uuid
import subprocess
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from app.config import get_settings, Settings
from app.dependencies import require_user
from app.models import Project, ProjectResponse, DeployRequest, JWTClaims
from app.services.project_store import load_projects, upsert_project, delete_project, get_project
from app.services.docker_service import clone_repo, deploy_project, stop_project, project_status, DockerError
from app.services.cloudflare_service import add_ingress, remove_ingress

router = APIRouter(prefix="/projects", tags=["projects"])


def _store_path(settings: Settings) -> str:
    return f"{settings.BASE_DIR}/projects.json"


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
    project = Project(
        id=str(uuid.uuid4()),
        name=body.name,
        repo_url=body.repo_url,
        subdomain=body.subdomain,
        path=f"{settings.BASE_DIR}/{body.subdomain}",
        port=body.port,
    )
    upsert_project(_store_path(settings), project)
    return ProjectResponse(**project.model_dump(), status="stopped")


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project_endpoint(
    project_id: str,
    settings: Settings = Depends(get_settings),
    _: JWTClaims = Depends(require_user),
):
    store = _store_path(settings)
    project = get_project(store, project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    try:
        stop_project(project.path)
    except DockerError:
        pass
    delete_project(store, project_id)


@router.post("/{project_id}/deploy", response_model=ProjectResponse)
def deploy_project_endpoint(
    project_id: str,
    settings: Settings = Depends(get_settings),
    _: JWTClaims = Depends(require_user),
):
    store = _store_path(settings)
    project = get_project(store, project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    try:
        clone_repo(project.repo_url, project.path)
        deploy_project(project.path)
    except DockerError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))
    try:
        add_ingress(settings.CLOUDFLARED_CONFIG, project.subdomain, settings.BASE_DOMAIN, project.port)
    except (FileNotFoundError, ValueError, Exception) as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Cloudflare config error: {e}")
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
    project = get_project(store, project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    try:
        stop_project(project.path)
    except DockerError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))
    try:
        remove_ingress(settings.CLOUDFLARED_CONFIG, project.subdomain, settings.BASE_DOMAIN)
    except (FileNotFoundError, ValueError, Exception) as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Cloudflare config error: {e}")
    project = project.model_copy(update={"updated_at": datetime.now(timezone.utc)})
    upsert_project(store, project)
    return ProjectResponse(**project.model_dump(), status="stopped")


@router.post("/{project_id}/update", response_model=ProjectResponse)
def update_project(
    project_id: str,
    settings: Settings = Depends(get_settings),
    _: JWTClaims = Depends(require_user),
):
    store = _store_path(settings)
    project = get_project(store, project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    result = subprocess.run(
        ["git", "pull"],
        cwd=project.path,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"git pull failed: {result.stderr}",
        )

    try:
        stop_project(project.path)
        deploy_project(project.path)
    except DockerError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))

    project = project.model_copy(update={"updated_at": datetime.now(timezone.utc)})
    upsert_project(store, project)
    return ProjectResponse(**project.model_dump(), status="running")
