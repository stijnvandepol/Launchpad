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


def add_ingress(config_path: str, subdomain: str, base_domain: str, port: int, metrics_url: str) -> None:
    """Add or update an ingress rule, then hot-reload cloudflared."""
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
    _reload_cloudflared(metrics_url)


def remove_ingress(config_path: str, subdomain: str, base_domain: str, metrics_url: str) -> None:
    """Remove an ingress rule, then hot-reload cloudflared."""
    p = Path(config_path)
    data = _load(p)
    hostname = f"{subdomain}.{base_domain}"

    ingress = data.get("ingress", [])
    named = [r for r in ingress if r.get("hostname") and r.get("hostname") != hostname]
    data["ingress"] = named + [_CATCH_ALL]

    _save(p, data)
    _reload_cloudflared(metrics_url)


def _reload_cloudflared(metrics_url: str) -> None:
    """Hot-reload cloudflared config via the metrics API (no downtime)."""
    try:
        result = subprocess.run(
            ["curl", "-sf", "-X", "POST", f"{metrics_url}/config/reload"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            logger.info("Hot-reloaded cloudflared config via %s", metrics_url)
            return
        logger.error("Hot-reload failed (exit %s): %s", result.returncode, result.stderr)
    except Exception as e:
        logger.error("Hot-reload unavailable at %s: %s", metrics_url, e)
