# app/services/docker_service.py
import docker
from docker.errors import DockerException, NotFound


class DockerError(Exception):
    pass


def deploy_container(name: str, repo_path: str, port: int) -> str:
    """Run container named `name` from image with same name, binding `port`."""
    try:
        client = docker.from_env()
        try:
            old = client.containers.get(name)
            old.stop()
            old.remove()
        except NotFound:
            pass
        container = client.containers.run(
            name,  # image tag == container name (built separately)
            name=name,
            ports={f"{port}/tcp": port},
            detach=True,
            restart_policy={"Name": "unless-stopped"},
        )
        return container.id
    except DockerException as e:
        raise DockerError(f"Docker error: {e}")


def stop_container(name: str) -> None:
    """Stop and remove container by name. No-op if not found."""
    try:
        client = docker.from_env()
        try:
            container = client.containers.get(name)
            container.stop()
            container.remove()
        except NotFound:
            pass
    except DockerException as e:
        raise DockerError(f"Docker error: {e}")


def container_status(name: str) -> str:
    """Return 'running' if container exists and is running, otherwise 'stopped'."""
    try:
        client = docker.from_env()
        try:
            container = client.containers.get(name)
            return "running" if container.status == "running" else "stopped"
        except NotFound:
            return "stopped"
    except DockerException as e:
        raise DockerError(f"Docker error: {e}")
