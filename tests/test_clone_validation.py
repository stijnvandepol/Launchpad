# tests/test_clone_validation.py
import pytest


def test_url_with_semicolon_is_rejected():
    from app.models import DeployRequest
    with pytest.raises(Exception, match="safe https"):
        DeployRequest(name="x", subdomain="demo", repo_url="https://github.com/x/y;rm -rf /")


def test_url_with_backtick_is_rejected():
    from app.models import DeployRequest
    with pytest.raises(Exception, match="safe https"):
        DeployRequest(name="x", subdomain="demo", repo_url="https://github.com/x/y`whoami`")


def test_http_url_is_rejected():
    from app.models import DeployRequest
    with pytest.raises(Exception, match="safe https"):
        DeployRequest(name="x", subdomain="demo", repo_url="http://github.com/x/y")


def test_valid_github_url_passes():
    from app.models import DeployRequest
    req = DeployRequest(name="x", subdomain="demo", repo_url="https://github.com/user/repo")
    assert req.repo_url == "https://github.com/user/repo"


def test_subdomain_with_uppercase_rejected():
    from app.models import DeployRequest
    with pytest.raises(Exception, match="lowercase"):
        DeployRequest(name="x", subdomain="MyApp", repo_url="https://github.com/x/y")


def test_subdomain_starting_with_hyphen_rejected():
    from app.models import DeployRequest
    with pytest.raises(Exception, match="lowercase"):
        DeployRequest(name="x", subdomain="-myapp", repo_url="https://github.com/x/y")
