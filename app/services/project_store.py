import json
import os
import tempfile
from pathlib import Path
from app.models import Project


def load_projects(path: str) -> list[Project]:
    p = Path(path)
    if not p.exists():
        return []
    text = p.read_text(encoding="utf-8").strip()
    if not text:
        return []
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    return [Project.model_validate(item) for item in data]


def save_projects(path: str, projects: list[Project]) -> None:
    p = Path(path)
    data = [project.model_dump(mode="json") for project in projects]
    dir_ = p.parent
    with tempfile.NamedTemporaryFile(
        "w", dir=dir_, suffix=".tmp", delete=False, encoding="utf-8"
    ) as f:
        json.dump(data, f, indent=2, default=str)
        tmp_path = f.name
    os.replace(tmp_path, path)


def get_project(path: str, project_id: str) -> Project | None:
    return next((p for p in load_projects(path) if p.id == project_id), None)


def upsert_project(path: str, project: Project) -> None:
    projects = load_projects(path)
    projects = [p for p in projects if p.id != project.id]
    projects.append(project)
    save_projects(path, projects)


def delete_project(path: str, project_id: str) -> None:
    projects = [p for p in load_projects(path) if p.id != project_id]
    save_projects(path, projects)
