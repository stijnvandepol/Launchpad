# app/services/docker_service.py
import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


class DockerError(Exception):
    pass


def _run(cmd: list[str], cwd: str | None = None, timeout: int = 300) -> subprocess.CompletedProcess:
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        logger.error("Command %s failed: %s", cmd, result.stderr)
        raise DockerError(f"{' '.join(cmd)} failed: {result.stderr}")
    return result


def clone_repo(repo_url: str, path: str) -> None:
    """Clone repo if the directory doesn't exist yet."""
    if Path(path).exists():
        return
    _run(["git", "clone", repo_url, path], timeout=120)


def pull_repo(path: str) -> None:
    """Pull latest changes in an existing repo."""
    _run(["git", "pull"], cwd=path, timeout=120)


def deploy_project(path: str) -> None:
    """Run docker compose up -d --build in the project directory."""
    _run(["docker", "compose", "up", "-d", "--build"], cwd=path)


def stop_project(path: str) -> None:
    """Run docker compose down in the project directory."""
    _run(["docker", "compose", "down"], cwd=path)


def project_status(path: str) -> str:
    """Return 'running' if any compose service is up, otherwise 'stopped'."""
    if not Path(path).exists():
        return "stopped"
    try:
        result = _run(["docker", "compose", "ps", "-q"], cwd=path)
        return "running" if result.stdout.strip() else "stopped"
    except DockerError:
        return "stopped"
