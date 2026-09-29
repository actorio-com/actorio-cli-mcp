"""Tests for ActorioOAuthProvider/ActorioTokenVerifier — the thin httpx
proxies between the MCP ASGI service and Django's internal OAuth endpoints.
Mocks the HTTP boundary (respx) rather than a real Django server; the
Django side of each of these calls is covered by cli_api/tests/test_oauth.py.
"""
import pytest
import respx
from httpx import Response

from actorio_cli.oauth_provider import ActorioOAuthProvider, ActorioTokenVerifier
from mcp.server.auth.provider import AccessToken

BASE = "https://api.example.com"


@pytest.fixture
def provider():
    return ActorioOAuthProvider(django_base_url=BASE, internal_secret="s3cret")


@pytest.mark.asyncio
async def test_verify_token_valid():
    with respx.mock(base_url=BASE) as mock:
        mock.get("/cli/v1/oauth/introspect").mock(
            return_value=Response(200, json={
                "active": True, "sub": "42", "username": "alice",
                "oauth_client_id": "client-abc", "label": "oauth:Test",
            })
        )
        verifier = ActorioTokenVerifier(django_base_url=BASE)
        token = await verifier.verify_token("act_something")
    assert token is not None
    assert token.subject == "42"
    assert token.client_id == "client-abc"
    assert token.claims["username"] == "alice"


@pytest.mark.asyncio
async def test_verify_token_invalid_returns_none():
    with respx.mock(base_url=BASE) as mock:
        mock.get("/cli/v1/oauth/introspect").mock(return_value=Response(401))
        verifier = ActorioTokenVerifier(django_base_url=BASE)
        token = await verifier.verify_token("act_bad")
    assert token is None


@pytest.mark.asyncio
async def test_revoke_token_posts_raw_token(provider):
    with respx.mock(base_url=BASE) as mock:
        route = mock.post("/cli/v1/oauth/internal/revoke").mock(return_value=Response(200))
        await provider.revoke_token(AccessToken(token="act_abc123", client_id="client-abc", scopes=[]))
    assert route.called
    assert route.calls.last.request.headers["x-mcp-internal-secret"] == "s3cret"
    import json
    assert json.loads(route.calls.last.request.content) == {"token": "act_abc123"}


@pytest.mark.asyncio
async def test_exchange_authorization_code_returns_oauth_token(provider):
    from mcp.server.auth.provider import AuthorizationCode
    from pydantic import AnyUrl

    auth_code = AuthorizationCode(
        code="the-code", scopes=[], expires_at=9999999999.0, client_id="client-abc",
        code_challenge="c", redirect_uri=AnyUrl("https://chatgpt.example/callback"),
        redirect_uri_provided_explicitly=True, subject="42",
    )
    with respx.mock(base_url=BASE) as mock:
        mock.post("/cli/v1/oauth/internal/codes/exchange").mock(
            return_value=Response(200, json={"access_token": "act_new_token", "token_type": "Bearer"})
        )
        token = await provider.exchange_authorization_code(client=None, authorization_code=auth_code)
    assert token.access_token == "act_new_token"
    assert token.expires_in is None  # non-expiring, matches CliToken semantics
    assert token.refresh_token is None


# ---------------------------------------------------------------------------
# Token verifier — additional scenarios.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_verify_token_http_error_returns_none(monkeypatch):
    """Connection errors to Django are treated as unauthenticated."""
    import httpx as httpx_mod

    # Simulate a network error by patching the AsyncClient.get to raise
    original_get = httpx_mod.AsyncClient.get

    async def _raise(*args, **kwargs):
        raise httpx_mod.ConnectError("connection refused")

    monkeypatch.setattr(httpx_mod.AsyncClient, "get", _raise)
    verifier = ActorioTokenVerifier(django_base_url=BASE)
    token = await verifier.verify_token("act_anything")
    assert token is None


@pytest.mark.asyncio
async def test_verify_token_uses_oauth_client_id():
    """When oauth_client_id is missing from introspect, fall back to 'cli'."""
    with respx.mock(base_url=BASE) as mock:
        mock.get("/cli/v1/oauth/introspect").mock(
            return_value=Response(200, json={"active": True, "sub": "99"})
        )
        verifier = ActorioTokenVerifier(django_base_url=BASE)
        token = await verifier.verify_token("act_no_client")
    assert token is not None
    assert token.client_id == "cli"


# ---------------------------------------------------------------------------
# OAuth provider — internal endpoints.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_client_returns_none_on_404(provider):
    with respx.mock(base_url=BASE) as mock:
        mock.get("/cli/v1/oauth/internal/clients/unknown-client").mock(
            return_value=Response(404)
        )
        result = await provider.get_client("unknown-client")
    assert result is None


@pytest.mark.asyncio
async def test_get_client_returns_client_info(provider):
    with respx.mock(base_url=BASE) as mock:
        mock.get("/cli/v1/oauth/internal/clients/client-abc").mock(
            return_value=Response(
                200,
                json={
                    "client_id": "client-abc",
                    "client_secret": "secret-123",
                    "client_name": "ChatGPT Connector",
                    "redirect_uris": ["https://chatgpt.example/callback"],
                    "grant_types": ["authorization_code"],
                    "response_types": ["code"],
                    "token_endpoint_auth_method": "client_secret_post",
                    "scope": "",
                },
            )
        )
        result = await provider.get_client("client-abc")
    assert result is not None
    assert result.client_id == "client-abc"
    assert result.client_name == "ChatGPT Connector"


@pytest.mark.asyncio
async def test_exchange_code_error_raises_token_error(provider):
    from mcp.server.auth.provider import AuthorizationCode, TokenError
    from pydantic import AnyUrl

    auth_code = AuthorizationCode(
        code="expired-code", scopes=[], expires_at=0.0, client_id="client-abc",
        code_challenge="c", redirect_uri=AnyUrl("https://example.com/cb"),
        redirect_uri_provided_explicitly=True, subject="42",
    )
    with respx.mock(base_url=BASE) as mock:
        mock.post("/cli/v1/oauth/internal/codes/exchange").mock(
            return_value=Response(400, json={"error": "invalid_grant"})
        )
        with pytest.raises(TokenError) as exc:
            await provider.exchange_authorization_code(
                client=None, authorization_code=auth_code
            )
    assert exc.value.error == "invalid_grant"


@pytest.mark.asyncio
async def test_exchange_refresh_token_always_raises(provider):
    """Actorio tokens never expire — there is no refresh_token support and
    asking for one should raise a clear error."""
    from mcp.server.auth.provider import RefreshToken, TokenError

    with pytest.raises(TokenError) as exc:
        await provider.exchange_refresh_token(client=None, refresh_token=None, scopes=[])
    assert "unsupported_grant_type" in exc.value.error


@pytest.mark.asyncio
async def test_load_refresh_token_always_returns_none(provider):
    result = await provider.load_refresh_token(client=None, refresh_token="anything")
    assert result is None


@pytest.mark.asyncio
async def test_load_access_token_delegates_to_verifier(provider):
    """load_access_token calls through to the TokenVerifier, same as
    introspect does."""
    with respx.mock(base_url=BASE) as mock:
        mock.get("/cli/v1/oauth/introspect").mock(
            return_value=Response(200, json={"active": True, "sub": "42"})
        )
        token = await provider.load_access_token("act_valid")
    assert token is not None
    assert token.subject == "42"


# ---------------------------------------------------------------------------
# authorize — creates a consent request and returns the consent URL.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_authorize_returns_consent_url(provider):
    from mcp.server.auth.provider import AuthorizationParams
    from mcp.shared.auth import OAuthClientInformationFull
    from pydantic import AnyUrl

    client = OAuthClientInformationFull(
        client_id="client-abc",
        client_secret="s",
        redirect_uris=[AnyUrl("https://chatgpt.example/callback")],
        grant_types=["authorization_code"],
        response_types=["code"],
        token_endpoint_auth_method="client_secret_post",
        client_name="Test App",
        scope="",
    )
    with respx.mock(base_url=BASE) as mock:
        mock.post("/cli/v1/oauth/internal/authorize-requests").mock(
            return_value=Response(
                201,
                json={
                    "request_id": "req-xyz",
                    "consent_url": "https://api.example.com/cli/v1/oauth/consent?request_id=req-xyz",
                },
            )
        )
        url = await provider.authorize(
            client=client,
            params=AuthorizationParams(
                client_id="client-abc",
                redirect_uri=AnyUrl("https://chatgpt.example/callback"),
                redirect_uri_provided_explicitly=True,
                code_challenge="pkce-challenge",
                scopes=[],
                state="state-xyz",
            ),
        )
    assert "consent" in url
    assert "req-xyz" in url


@pytest.mark.asyncio
async def test_load_authorization_code_returns_none_on_404(provider):
    with respx.mock(base_url=BASE) as mock:
        mock.get("/cli/v1/oauth/internal/codes/load").mock(return_value=Response(404))
        result = await provider.load_authorization_code(
            client=None, authorization_code="unknown-code"
        )
    assert result is None


@pytest.mark.asyncio
async def test_register_client(provider):
    from mcp.shared.auth import OAuthClientInformationFull
    from pydantic import AnyUrl

    client_info = OAuthClientInformationFull(
        client_id="new-client",
        client_secret="new-secret",
        redirect_uris=[AnyUrl("https://example.com/cb")],
        grant_types=["authorization_code"],
        response_types=["code"],
        token_endpoint_auth_method="client_secret_post",
        client_name="New App",
        scope="",
    )
    with respx.mock(base_url=BASE) as mock:
        route = mock.post("/cli/v1/oauth/internal/clients").mock(
            return_value=Response(201)
        )
        await provider.register_client(client_info)
    assert route.called
    assert route.calls.last.request.headers["x-mcp-internal-secret"] == "s3cret"
