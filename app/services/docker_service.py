# app/services/docker_service.py
import logging
import os
import subprocess
from pathlib import Path
from typing import Iterator, Optional

logger = logging.getLogger(__name__)

CONTAINER_MEMORY_LIMIT = "512m"
CONTAINER_CPU_LIMIT = "0.5"
CONTAINER_DEFAULT_PORT = 8080


def _compose_override(port: int, container_port: int = CONTAINER_DEFAULT_PORT, service_name: str = "app") -> str:
    return f"""\
services:
  {service_name}:
    build: .
    mem_limit: {CONTAINER_MEMORY_LIMIT}
    cpus: "{CONTAINER_CPU_LIMIT}"
    network_mode: bridge
    restart: "no"
    ports:
      - "{port}:{container_port}"
    environment:
      PORT: "{container_port}"
"""


def detect_service_name(path: str) -> str:
    """Return the first service name from docker-compose.yml, or 'app' if absent/unreadable."""
    compose_file = Path(path) / "docker-compose.yml"
    if not compose_file.exists():
        return "app"
    try:
        from ruamel.yaml import YAML
        yaml = YAML()
        with open(compose_file) as f:
            data = yaml.load(f)
        services = (data or {}).get("services") or {}
        if services:
            return next(iter(services))
    except Exception:
        pass
    return "app"


def detect_container_port(path: str) -> int:
    """Detect the container's listen port from docker-compose.yml ports mapping or Dockerfile EXPOSE.

    Checks docker-compose.yml first (right-hand side of 'host:container' mapping),
    then falls back to the first EXPOSE directive in the Dockerfile.
    Returns CONTAINER_DEFAULT_PORT if nothing is found.
    """
    compose_file = Path(path) / "docker-compose.yml"
    if compose_file.exists():
        try:
            from ruamel.yaml import YAML
            yaml = YAML()
            with open(compose_file) as f:
                data = yaml.load(f)
            for service in ((data or {}).get("services") or {}).values():
                for p in (service or {}).get("ports") or []:
                    s = str(p).split("/")[0]  # strip /tcp, /udp
                    container_port = int(s.split(":")[-1]) if ":" in s else int(s)
                    return container_port
        except Exception:
            pass
    dockerfile = Path(path) / "Dockerfile"
    if dockerfile.exists():
        try:
            for line in dockerfile.read_text().splitlines():
                stripped = line.strip()
                if stripped.upper().startswith("EXPOSE "):
                    return int(stripped.split()[1].split("/")[0])
        except Exception:
            pass
    return CONTAINER_DEFAULT_PORT


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


def strip_host_ports(path: str) -> None:
    """Remove all 'ports:' entries from the repo's docker-compose.yml so the platform
    controls host port assignment exclusively via the override file. Without this, repos
    that hardcode 'ports: - "8080:8080"' would conflict when multiple projects run.
    """
    compose_file = Path(path) / "docker-compose.yml"
    if not compose_file.exists():
        return
    from ruamel.yaml import YAML
    yaml = YAML()
    yaml.preserve_quotes = True
    with open(compose_file) as f:
        data = yaml.load(f)
    if not data or "services" not in data:
        return
    changed = False
    for service in (data["services"] or {}).values():
        if service and "ports" in service:
            del service["ports"]
            changed = True
    if changed:
        with open(compose_file, "w") as f:
            yaml.dump(data, f)


def write_compose_override(path: str, port: int, container_port: int = 8080) -> None:
    """Write resource-limit + port-mapping override. Always regenerated so repo cannot override limits.
    Maps the unique assigned host port to the configured container port. PORT env var is also
    injected so apps that respect the PORT convention pick up the right value.
    Service name is auto-detected from docker-compose.yml so the override merges correctly.
    """
    service_name = detect_service_name(path)
    (Path(path) / "docker-compose.override.yml").write_text(
        _compose_override(port, container_port, service_name)
    )


def pull_repo(path: str) -> None:
    _run(["git", "pull"], cwd=path, timeout=120)


def deploy_project(path: str, port: Optional[int] = None) -> None:
    if port:
        write_compose_override(path, port)
    _run(["docker", "compose", "up", "-d", "--build"], cwd=path)


def stop_project(path: str) -> None:
    _run(["docker", "compose", "down"], cwd=path, env=None)


def teardown_project(path: str) -> None:
    """Stop containers and remove images. Used for pull (update code) and delete."""
    if not Path(path).exists():
        return
    _run(["docker", "compose", "down", "--rmi", "all", "--remove-orphans"], cwd=path, env=None)


def project_status(path: str) -> str:
    if not Path(path).exists():
        return "stopped"
    try:
        result = _run(["docker", "compose", "ps", "-q"], cwd=path)
        return "running" if result.stdout.strip() else "stopped"
    except DockerError:
        return "stopped"
