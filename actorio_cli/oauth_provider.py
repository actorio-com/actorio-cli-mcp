"""OAuth 2.1 authorization server + resource server glue for the MCP HTTP
transport (run_http() in mcp_server.py).

This module is deliberately thin: it holds no identity/credential logic and
no database access of its own. Every method here is an httpx call to a new
"internal" endpoint on the Django API (cli_api/views.py's oauth_internal_*
views), authenticated with a shared secret (MCP_OAUTH_INTERNAL_SECRET) —
Django owns CliToken minting, session login, and the consent UI; this class
just relays the MCP SDK's OAuthAuthorizationServerProvider protocol calls to
it and translates the responses back into the SDK's pydantic types.

The access token handed back to MCP clients (ChatGPT, Claude.ai, etc.) is a
real CliToken raw value — the same kind actorio_cli.config's device-code
login produces — so cli_api's existing CliTokenAuthentication verifies it
everywhere else with zero new code.
"""
from typing import Any

import httpx
from pydantic import AnyUrl

from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    OAuthAuthorizationServerProvider,
    RefreshToken,
    TokenError,
    TokenVerifier,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken


class ActorioTokenVerifier(TokenVerifier):
    """Verifies a bearer token by asking Django (the one place CliToken
    actually lives) rather than touching any database directly."""

    def __init__(self, django_base_url: str):
        self._base = django_base_url.rstrip("/")

    async def verify_token(self, token: str) -> AccessToken | None:
        async with httpx.AsyncClient(timeout=5.0) as http:
            try:
                resp = await http.get(
                    f"{self._base}/cli/v1/oauth/introspect",
                    headers={"Authorization": f"Bearer {token}"},
                )
            except httpx.HTTPError:
                return None
        if resp.status_code != 200:
            return None
        data = resp.json()
        return AccessToken(
            token=token,
            client_id=data.get("oauth_client_id") or "cli",
            scopes=[],
            subject=data["sub"],
            claims={"username": data.get("username")},
        )


class ActorioOAuthProvider(OAuthAuthorizationServerProvider[AuthorizationCode, RefreshToken, AccessToken]):
    def __init__(self, django_base_url: str, internal_secret: str):
        self._base = django_base_url.rstrip("/")
        self._headers = {"X-MCP-Internal-Secret": internal_secret}
        self._verifier = ActorioTokenVerifier(django_base_url)

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=10.0, headers=self._headers)

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        async with self._client() as http:
            resp = await http.get(f"{self._base}/cli/v1/oauth/internal/clients/{client_id}")
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return OAuthClientInformationFull.model_validate(resp.json())

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        async with self._client() as http:
            resp = await http.post(
                f"{self._base}/cli/v1/oauth/internal/clients",
                json=client_info.model_dump(mode="json", exclude_none=True),
            )
        resp.raise_for_status()

    async def authorize(self, client: OAuthClientInformationFull, params: AuthorizationParams) -> str:
        async with self._client() as http:
            resp = await http.post(
                f"{self._base}/cli/v1/oauth/internal/authorize-requests",
                json={
                    "client_id": client.client_id,
                    "redirect_uri": str(params.redirect_uri),
                    "code_challenge": params.code_challenge,
                    "scope": " ".join(params.scopes) if params.scopes else "",
                    "state": params.state or "",
                    "resource": params.resource or "",
                },
            )
        resp.raise_for_status()
        # Send the browser to Django's session-authenticated consent page —
        # login + approve/deny happen entirely there, out of this process.
        return resp.json()["consent_url"]

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> AuthorizationCode | None:
        async with self._client() as http:
            resp = await http.get(
                f"{self._base}/cli/v1/oauth/internal/codes/load",
                params={"code": authorization_code},
            )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        data = resp.json()
        return AuthorizationCode(
            code=authorization_code,
            scopes=data["scope"].split() if data["scope"] else [],
            expires_at=data["expires_at"],
            client_id=data["client_id"],
            code_challenge=data["code_challenge"],
            redirect_uri=AnyUrl(data["redirect_uri"]),
            # Django always stores a concrete redirect_uri (resolved by the
            # SDK's own AuthorizationHandler before authorize() ran), so
            # this is always effectively true from our side.
            redirect_uri_provided_explicitly=True,
            subject=data["subject"],
        )

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: AuthorizationCode
    ) -> OAuthToken:
        async with self._client() as http:
            resp = await http.post(
                f"{self._base}/cli/v1/oauth/internal/codes/exchange",
                json={"code": authorization_code.code},
            )
        if resp.status_code != 200:
            raise TokenError(
                error="invalid_grant",
                error_description="Authorization code could not be exchanged (expired or already used)",
            )
        data = resp.json()
        # No expires_in / refresh_token: CliToken never expires (only
        # revoked), same as every device-code-issued token today.
        return OAuthToken(access_token=data["access_token"], token_type="Bearer")

    async def load_refresh_token(self, client: OAuthClientInformationFull, refresh_token: str) -> RefreshToken | None:
        return None

    async def exchange_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: RefreshToken, scopes: list[str]
    ) -> OAuthToken:
        raise TokenError(
            error="unsupported_grant_type",
            error_description="Actorio access tokens do not expire; there is nothing to refresh",
        )

    async def load_access_token(self, token: str) -> AccessToken | None:
        return await self._verifier.verify_token(token)

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        # Only ever called with an AccessToken in practice — we never issue
        # refresh tokens (see exchange_refresh_token above). Per RFC 7009,
        # revoking an unknown/already-revoked token is not an error, and
        # Django's endpoint is idempotent to match.
        async with self._client() as http:
            resp = await http.post(
                f"{self._base}/cli/v1/oauth/internal/revoke",
                json={"token": token.token},
            )
        resp.raise_for_status()
