# app/services/cloudflare_service.py
from pathlib import Path
from ruamel.yaml import YAML


def add_ingress(config_path: str, subdomain: str, base_domain: str, port: int) -> None:
    """Insert or replace an ingress rule for subdomain, keeping catch-all last."""
    yaml = YAML()
    p = Path(config_path)
    data = yaml.load(p)
    hostname = f"{subdomain}.{base_domain}"
    service = f"http://localhost:{port}"

    ingress = data.get("ingress", [])
    catch_all = next((r for r in ingress if "hostname" not in r), None)
    named = [r for r in ingress if r.get("hostname") != hostname and "hostname" in r]
    named.append({"hostname": hostname, "service": service})
    data["ingress"] = named + ([catch_all] if catch_all else [])

    with p.open("w") as f:
        yaml.dump(data, f)


def remove_ingress(config_path: str, subdomain: str, base_domain: str) -> None:
    """Remove ingress rule for subdomain. No-op if not present."""
    yaml = YAML()
    p = Path(config_path)
    data = yaml.load(p)
    hostname = f"{subdomain}.{base_domain}"
    data["ingress"] = [r for r in data.get("ingress", []) if r.get("hostname") != hostname]
    with p.open("w") as f:
        yaml.dump(data, f)
