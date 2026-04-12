# app/services/docker_service.py
import logging
import os
import subprocess
from pathlib import Path
from typing import Iterator, Optional

logger = logging.getLogger(__name__)

COMPOSE_OVERRIDE = """\
services:
  app:
    mem_limit: 512m
    cpus: "0.5"
    network_mode: bridge
    restart: "no"
"""


class DockerError(Exception):
    pass


def _run(
    cmd: list[str],
    cwd: Optional[str] = None,
    timeout: int = 300,
    env: Optional[dict] = None,
) -> subprocess.CompletedProcess:
    run_env = {**os.environ, **(env or {})}
    result = subprocess.run(
        cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout, env=run_env,
    )
    if result.returncode != 0:
        logger.error("Command %s failed: %s", cmd, result.stderr)
        raise DockerError(f"{' '.join(cmd)} failed: {result.stderr}")
    return result


def _run_streaming(
    cmd: list[str],
    cwd: Optional[str] = None,
    timeout: int = 300,
    env: Optional[dict] = None,
) -> Iterator[str]:
    """Run command and yield stdout+stderr lines as they arrive.
    Raises DockerError if process exits non-zero.
    """
    run_env = {**os.environ, **(env or {})}
    proc = subprocess.Popen(
        cmd, cwd=cwd, env=run_env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        for line in proc.stdout:
            yield line.rstrip()
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        raise DockerError(f"Command timed out after {timeout}s")
    if proc.returncode != 0:
        raise DockerError(f"{' '.join(cmd)} failed (exit {proc.returncode})")


def validate_repo(path: str) -> None:
    """Raise DockerError if neither Dockerfile nor docker-compose.yml is present."""
    p = Path(path)
    if not (p / "Dockerfile").exists() and not (p / "docker-compose.yml").exists():
        raise DockerError("No Dockerfile or docker-compose.yml found in repository root")


def write_compose_override(path: str) -> None:
    """Write resource-limit override. Always regenerated so repo cannot override limits."""
    (Path(path) / "docker-compose.override.yml").write_text(COMPOSE_OVERRIDE)


def pull_repo(path: str) -> None:
    _run(["git", "pull"], cwd=path, timeout=120)


def deploy_project(path: str, port: Optional[int] = None) -> None:
    env = {"PORT": str(port)} if port else None
    _run(["docker", "compose", "up", "-d", "--build"], cwd=path, env=env)


def stop_project(path: str) -> None:
    _run(["docker", "compose", "down"], cwd=path, env=None)


def project_status(path: str) -> str:
    if not Path(path).exists():
        return "stopped"
    try:
        result = _run(["docker", "compose", "ps", "-q"], cwd=path)
        return "running" if result.stdout.strip() else "stopped"
    except DockerError:
        return "stopped"
