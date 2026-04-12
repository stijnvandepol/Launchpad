# app/services/cloudflare_service.py
import logging
import subprocess
from pathlib import Path
from ruamel.yaml import YAML

logger = logging.getLogger(__name__)

_yaml = YAML()
_yaml.preserve_quotes = True

# Catch-all rule — must always be last in ingress list
_CATCH_ALL = {"service": "http_status:404"}


def _load(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Cloudflared config not found: {path}")
    data = _yaml.load(path)
    if data is None:
        raise ValueError(f"Cloudflared config is empty: {path}")
    return data


def _save(path: Path, data: dict) -> None:
    with path.open("w") as f:
        _yaml.dump(data, f)


def add_ingress(config_path: str, subdomain: str, base_domain: str, port: int) -> None:
    """Add or update an ingress rule, then restart cloudflared."""
    p = Path(config_path)
    data = _load(p)
    hostname = f"{subdomain}.{base_domain}"
    service = f"http://localhost:{port}"

    ingress = data.get("ingress", [])
    # Keep all named rules except the one we're replacing, and drop catch-all
    named = [r for r in ingress if r.get("hostname") and r.get("hostname") != hostname]
    named.append({"hostname": hostname, "service": service})
    data["ingress"] = named + [_CATCH_ALL]

    _save(p, data)
    _restart_cloudflared()


def remove_ingress(config_path: str, subdomain: str, base_domain: str) -> None:
    """Remove an ingress rule, then restart cloudflared."""
    p = Path(config_path)
    data = _load(p)
    hostname = f"{subdomain}.{base_domain}"

    ingress = data.get("ingress", [])
    named = [r for r in ingress if r.get("hostname") and r.get("hostname") != hostname]
    data["ingress"] = named + [_CATCH_ALL]

    _save(p, data)
    _restart_cloudflared()


def _restart_cloudflared() -> None:
    """Hot-reload cloudflared config via metrics API (no downtime).
    Falls back to container restart if the metrics endpoint is unavailable.
    """
    try:
        result = subprocess.run(
            ["curl", "-sf", "-X", "POST", "http://localhost:2000/config/reload"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            logger.info("Hot-reloaded cloudflared config")
            return
        logger.warning("Hot-reload failed (exit %s): %s", result.returncode, result.stderr)
    except Exception as e:
        logger.warning("Hot-reload unavailable: %s", e)

    # Fallback: container restart
    try:
        result = subprocess.run(
            ["docker", "ps", "-q", "--filter", "name=tunnel-projects"],
            capture_output=True, text=True, timeout=10,
        )
        container_id = result.stdout.strip()
        if container_id:
            subprocess.run(
                ["docker", "restart", container_id],
                capture_output=True, text=True, timeout=30,
            )
            logger.info("Restarted cloudflared container (fallback)")
        else:
            logger.warning("No cloudflared container found to restart")
    except Exception as e:
        logger.error("Failed to restart cloudflared: %s", e)
