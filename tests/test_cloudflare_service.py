# tests/test_cloudflare_service.py
import tempfile
import os
from pathlib import Path
from ruamel.yaml import YAML


def _write_config(d: str, ingress: list) -> str:
    p = os.path.join(d, "config.yml")
    yaml = YAML()
    with open(p, "w") as f:
        yaml.dump({"tunnel": "t", "ingress": ingress}, f)
    return p


def _read_ingress(path: str) -> list:
    yaml = YAML()
    return yaml.load(Path(path))["ingress"]


def test_add_ingress_inserts_before_catchall():
    from app.services.cloudflare_service import add_ingress
    with tempfile.TemporaryDirectory() as d:
        p = _write_config(d, [{"service": "http_status:404"}])
        add_ingress(p, "my-app", "webvakwerk.nl", 3001)
        ingress = _read_ingress(p)
        assert ingress[0]["hostname"] == "my-app.webvakwerk.nl"
        assert ingress[0]["service"] == "http://localhost:3001"
        assert ingress[-1]["service"] == "http_status:404"


def test_add_ingress_replaces_existing():
    from app.services.cloudflare_service import add_ingress
    with tempfile.TemporaryDirectory() as d:
        p = _write_config(d, [
            {"hostname": "my-app.webvakwerk.nl", "service": "http://localhost:3000"},
            {"service": "http_status:404"},
        ])
        add_ingress(p, "my-app", "webvakwerk.nl", 3001)
        ingress = _read_ingress(p)
        rules = [r for r in ingress if r.get("hostname") == "my-app.webvakwerk.nl"]
        assert len(rules) == 1
        assert rules[0]["service"] == "http://localhost:3001"


def test_remove_ingress_deletes_rule():
    from app.services.cloudflare_service import remove_ingress
    with tempfile.TemporaryDirectory() as d:
        p = _write_config(d, [
            {"hostname": "my-app.webvakwerk.nl", "service": "http://localhost:3001"},
            {"service": "http_status:404"},
        ])
        remove_ingress(p, "my-app", "webvakwerk.nl")
        ingress = _read_ingress(p)
        assert not any(r.get("hostname") == "my-app.webvakwerk.nl" for r in ingress)
        assert ingress[-1]["service"] == "http_status:404"


def test_remove_ingress_noop_when_not_present():
    from app.services.cloudflare_service import remove_ingress
    with tempfile.TemporaryDirectory() as d:
        p = _write_config(d, [{"service": "http_status:404"}])
        remove_ingress(p, "nonexistent", "webvakwerk.nl")
        ingress = _read_ingress(p)
        assert len(ingress) == 1
