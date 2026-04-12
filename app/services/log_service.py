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
