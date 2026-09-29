"""Tests for the MCP HTTP transport's OAuth wiring (build_http_app in
mcp_server.py) — auth rejection, RFC 9728 discovery. Talks to the ASGI app
directly via Starlette's TestClient; never hits a real Django backend (the
OAuth provider's httpx calls would only fire on registration/authorize/token
requests, none of which these tests exercise).
"""
import pytest
from starlette.testclient import TestClient

import actorio_cli.mcp_server as mcp_server


@pytest.fixture(autouse=True)
def _internal_secret(monkeypatch):
    monkeypatch.setenv("MCP_OAUTH_INTERNAL_SECRET", "test-secret")


@pytest.fixture
def app():
    a = mcp_server.build_http_app(
        public_url="https://example.ngrok-free.app",
        api_base_url="https://api.example.com",
    )
    yield a
    mcp_server.PUBLIC_BASE_URL = None
    mcp_server.DJANGO_BASE_URL = None


def test_missing_authorization_header_rejected(app):
    with TestClient(app) as client:
        resp = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
    assert resp.status_code == 401
    assert resp.headers["www-authenticate"].startswith('Bearer error="invalid_token"')
    assert "resource_metadata=" in resp.headers["www-authenticate"]


def test_garbage_bearer_token_rejected(app, monkeypatch):
    async def _verify_none(self, token):
        return None

    monkeypatch.setattr("actorio_cli.oauth_provider.ActorioTokenVerifier.verify_token", _verify_none)
    with TestClient(app) as client:
        resp = client.post(
            "/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
            headers={"Authorization": "Bearer not-a-real-token"},
        )
    assert resp.status_code == 401


def test_protected_resource_metadata_is_valid_rfc9728(app):
    with TestClient(app) as client:
        resp = client.get("/.well-known/oauth-protected-resource/mcp")
    assert resp.status_code == 200
    data = resp.json()
    assert data["resource"] == "https://example.ngrok-free.app/mcp"
    assert data["authorization_servers"] == ["https://example.ngrok-free.app/"]


def test_authorization_server_metadata_is_published(app):
    with TestClient(app) as client:
        resp = client.get("/.well-known/oauth-authorization-server")
    assert resp.status_code == 200
    data = resp.json()
    assert data["issuer"] == "https://example.ngrok-free.app/"
    assert data["authorization_endpoint"].endswith("/authorize")
    assert data["token_endpoint"].endswith("/token")
    assert data["registration_endpoint"].endswith("/register")


def test_valid_bearer_token_reaches_the_mcp_endpoint(app, monkeypatch):
    """A verified token should pass RequireAuthMiddleware and reach the real
    MCP JSON-RPC handler (tools/list doesn't require the caller to be
    logged in anywhere else, so a 200 with a tool list proves the request
    got all the way through)."""
    from mcp.server.auth.provider import AccessToken

    async def _verify_ok(self, token):
        return AccessToken(token=token, client_id="client-abc", scopes=[], subject="42")

    monkeypatch.setattr("actorio_cli.oauth_provider.ActorioTokenVerifier.verify_token", _verify_ok)
    with TestClient(app) as client:
        resp = client.post(
            "/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
            headers={"Authorization": "Bearer good-token", "Accept": "application/json, text/event-stream"},
        )
    assert resp.status_code == 200


def test_export_download_proxy(app, monkeypatch):
    """The download proxy route is unauthenticated and forwards to Django's
    internal export endpoint, streaming the cached file back."""
    csv_bytes = b"id,name\n1,lego\n"

    def _mock_download(self, token, filename):
        assert token == "abc123"
        assert filename == "actorio-products.csv"
        return csv_bytes, "text/csv; charset=utf-8", "actorio-products.csv"

    monkeypatch.setattr("actorio_cli.client.Client.download_export", _mock_download)

    with TestClient(app) as client:
        resp = client.get("/cli/v1/exports/abc123/actorio-products.csv")

    assert resp.status_code == 200
    assert resp.content == csv_bytes
    assert resp.headers["content-type"] == "text/csv; charset=utf-8"
    assert 'filename="actorio-products.csv"' in resp.headers["content-disposition"]


def test_export_download_proxy_not_found(app, monkeypatch):
    """When Django returns 404 (expired/missing export), the proxy surfaces
    the error as JSON with the original status code."""
    from actorio_cli.client import ApiError

    def _mock_not_found(self, token, filename):
        raise ApiError(code="export_not_found", message="Export not found or expired", status=404)

    monkeypatch.setattr("actorio_cli.client.Client.download_export", _mock_not_found)

    with TestClient(app) as client:
        resp = client.get("/cli/v1/exports/expired/x.csv")

    assert resp.status_code == 404
    data = resp.json()
    assert data["error"]["code"] == "export_not_found"
