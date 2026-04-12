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
        data = project.model_dump()
        existing = session.get(Project, project.id)
        if existing:
            for key, val in data.items():
                setattr(existing, key, val)
        else:
            session.add(Project(**data))
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
    used = {p.port for p in load_projects(path)}
    port = _PORT_START
    while port in used:
        port += 1
    return port
