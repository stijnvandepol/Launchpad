# app/services/cloudflare_service.py
import logging
import httpx

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.cloudflare.com/client/v4"
_CATCH_ALL = {"service": "http_status:404"}

# Single reused client — connection keep-alive, no per-call TCP overhead
_client = httpx.Client(timeout=10)


class CloudflareAPIError(Exception):
    """Raised when the Cloudflare API returns a non-2xx response or is unreachable."""


def _headers(api_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_token}", "Content-Type": "application/json"}


def _config_url(account_id: str, tunnel_id: str) -> str:
    return f"{_BASE_URL}/accounts/{account_id}/cfd_tunnel/{tunnel_id}/configurations"


def _get_ingress(account_id: str, tunnel_id: str, api_token: str) -> list[dict]:
    url = _config_url(account_id, tunnel_id)
    try:
        r = _client.get(url, headers=_headers(api_token))
        r.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise CloudflareAPIError(
            f"GET configurations HTTP {e.response.status_code}: {e.response.text}"
        ) from e
    except httpx.RequestError as e:
        raise CloudflareAPIError(f"GET configurations request error: {e}") from e
    data = r.json()
    result = data.get("result") or {}
    config = result.get("config") or {}
    return config.get("ingress") or []


def _put_ingress(account_id: str, tunnel_id: str, api_token: str, ingress: list[dict]) -> None:
    url = _config_url(account_id, tunnel_id)
    try:
        r = _client.put(
            url,
            headers=_headers(api_token),
            json={"config": {"ingress": ingress}},
        )
        r.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise CloudflareAPIError(
            f"PUT configurations HTTP {e.response.status_code}: {e.response.text}"
        ) from e
    except httpx.RequestError as e:
        raise CloudflareAPIError(f"PUT configurations request error: {e}") from e
    logger.info("cloudflare: tunnel ingress updated (%d rule(s))", len(ingress))


def add_ingress(account_id: str, tunnel_id: str, api_token: str, subdomain: str, base_domain: str, port: int) -> None:
    """Add or update an ingress rule via the Cloudflare API."""
    hostname = f"{subdomain}.{base_domain}"
    service = f"http://localhost:{port}"
    logger.debug("cloudflare: add_ingress %s -> %s", hostname, service)
    current = _get_ingress(account_id, tunnel_id, api_token)
    named = [r for r in current if r.get("hostname") and r["hostname"] != hostname]
    named.append({"hostname": hostname, "service": service})
    _put_ingress(account_id, tunnel_id, api_token, named + [_CATCH_ALL])


def remove_ingress(account_id: str, tunnel_id: str, api_token: str, subdomain: str, base_domain: str) -> None:
    """Remove an ingress rule via the Cloudflare API."""
    hostname = f"{subdomain}.{base_domain}"
    logger.debug("cloudflare: remove_ingress %s", hostname)
    current = _get_ingress(account_id, tunnel_id, api_token)
    named = [r for r in current if r.get("hostname") and r["hostname"] != hostname]
    _put_ingress(account_id, tunnel_id, api_token, named + [_CATCH_ALL])
