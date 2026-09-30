import json
import os
import pytest
from unittest.mock import patch, MagicMock
from actorio_cli.config import Config, save_config


@pytest.mark.asyncio
async def test_stdio_transport_never_touches_access_token(isolated_config_path):
    """Locks in the branch split itself: with PUBLIC_BASE_URL unset (the
    stdio default), _tool_handler must use load_config() and must not call
    get_access_token — stdio's per-user ~/.actorio/config.json flow stays
    completely untouched by the new OAuth/HTTP path."""
    import actorio_cli.mcp_server as mcp_server
    assert mcp_server.PUBLIC_BASE_URL is None
    save_config(Config(base_url="https://a", token="t", token_label="l"))
    with patch("actorio_cli.mcp_server.load_config") as mock_load_config, \
         patch("mcp.server.auth.middleware.auth_context.get_access_token") as mock_get_token, \
         patch("actorio_cli.mcp_server.Client") as mock_cls:
        mock_load_config.return_value = Config(base_url="https://a", token="t", token_label="l")
        client = MagicMock()
        client.usage.return_value = {"effective_remaining": 10}
        client.last_credits = None
        mock_cls.return_value = client
        await mcp_server._tool_handler("get_usage", {})
    mock_load_config.assert_called_once()
    mock_get_token.assert_not_called()


@pytest.mark.asyncio
async def test_search_products_tool_returns_json(isolated_config_path):
    save_config(Config(base_url="https://a", token="t", token_label="l"))
    from actorio_cli.mcp_server import _tool_handler
    resp_data = {
        "results": [{"id": 1, "title": "Lego"}],
        "pagination": {"page": 1, "per_page": 20, "total": 1, "has_more": False},
    }
    with patch("actorio_cli.mcp_server.Client") as mock_cls:
        client = MagicMock()
        client.search.return_value = resp_data
        mock_cls.return_value = client
        result = await _tool_handler("search_products", {"query": "lego", "country": "DE"})
    text = result[0].text
    parsed = json.loads(text)
    assert parsed["results"] == resp_data["results"]
    assert client.search.call_args.args[0] == "products"
    assert "keywords" in str(client.search.call_args.args[1])


@pytest.mark.asyncio
async def test_tool_includes_credit_meta_when_present(isolated_config_path):
    save_config(Config(base_url="https://a", token="t", token_label="l"))
    from actorio_cli.mcp_server import _tool_handler
    with patch("actorio_cli.mcp_server.Client") as mock_cls:
        client = MagicMock()
        client.search.return_value = {"results": [], "pagination": {}}
        client.last_credits = {"cost": 1, "remaining": 999, "reset": "x", "warning": None}
        mock_cls.return_value = client
        result = await _tool_handler("search_products", {})
    parsed = json.loads(result[0].text)
    assert parsed["_meta"]["credits"]["cost"] == 1
    assert parsed["_meta"]["credits"]["remaining"] == 999


@pytest.mark.asyncio
async def test_tool_out_of_credits_message(isolated_config_path):
    save_config(Config(base_url="https://a", token="t", token_label="l"))
    from actorio_cli.client import ApiError
    from actorio_cli.mcp_server import _tool_handler
    with patch("actorio_cli.mcp_server.Client") as mock_cls:
        client = MagicMock()
        client.search.side_effect = ApiError(code="out_of_credits", message="0 left", status=402)
        mock_cls.return_value = client
        result = await _tool_handler("search_products", {})
    assert "out of credits" in result[0].text.lower()
    assert "billing" in result[0].text.lower() or "top up" in result[0].text.lower()


@pytest.mark.asyncio
async def test_tool_without_login_returns_error(isolated_config_path):
    from actorio_cli.mcp_server import _tool_handler
    result = await _tool_handler("search_products", {})
    assert "login" in result[0].text.lower()


@pytest.mark.asyncio
async def test_unknown_tool_returns_error(isolated_config_path):
    save_config(Config(base_url="https://a", token="t", token_label="l"))
    from actorio_cli.mcp_server import _tool_handler
    result = await _tool_handler("nonexistent_tool", {})
    assert "unknown" in result[0].text.lower()


@pytest.mark.asyncio
async def test_export_format_skips_search_calls_export_only(isolated_config_path):
    """When export_format is passed, client.search is NOT called — only
    export_link. This avoids charging for a redundant search when the user
    already saw results and just wants the file."""
    save_config(Config(base_url="https://a", token="t", token_label="l"))
    from actorio_cli.mcp_server import _tool_handler

    export_data = {
        "filename": "actorio-products.csv",
        "content_type": "text/csv; charset=utf-8",
        "bytes": 12345,
        "download_url": "https://a/cli/v1/exports/abc/actorio-products.csv",
    }

    with patch("actorio_cli.mcp_server.Client") as mock_cls:
        client = MagicMock()
        client.export_link.return_value = export_data
        client.last_credits = {"cost": 5, "remaining": 994, "reset": "x", "warning": None}
        mock_cls.return_value = client
        result = await _tool_handler(
            "search_products", {"query": "widget", "export_format": "csv"}
        )

    parsed = json.loads(result[0].text)
    # Only export info, no search results
    assert "results" not in parsed
    assert parsed["_export"]["download_url"] == export_data["download_url"]
    assert parsed["_export"]["filename"] == "actorio-products.csv"
    assert parsed["_meta"]["credits"]["cost"] == 5
    assert parsed["_meta"]["credits"]["remaining"] == 994
    # search was NOT called (saves 1 credit)
    client.export_link.assert_called_once()
    client.search.assert_not_called()


@pytest.mark.asyncio
async def test_search_without_export_format_skips_export(isolated_config_path):
    """Without export_format, no export is generated — search only, 1 credit."""
    save_config(Config(base_url="https://a", token="t", token_label="l"))
    from actorio_cli.mcp_server import _tool_handler

    with patch("actorio_cli.mcp_server.Client") as mock_cls:
        client = MagicMock()
        client.search.return_value = {
            "results": [{"id": 1}, {"id": 2}, {"id": 3}],
            "pagination": {"page": 1, "per_page": 20, "total": 3, "has_more": False},
        }
        client.last_credits = {"cost": 1, "remaining": 999, "reset": "x", "warning": None}
        mock_cls.return_value = client
        result = await _tool_handler("search_products", {"query": "rare-item"})

    parsed = json.loads(result[0].text)
    assert "_export" not in parsed
    assert parsed["_meta"]["credits"]["cost"] == 1
    client.export_link.assert_not_called()


@pytest.mark.asyncio
async def test_export_format_error_surfaces_to_caller(isolated_config_path):
    """When export_link raises an ApiError, it's surfaced as a readable
    error message (same as any other tool error)."""
    save_config(Config(base_url="https://a", token="t", token_label="l"))
    from actorio_cli.client import ApiError
    from actorio_cli.mcp_server import _tool_handler

    with patch("actorio_cli.mcp_server.Client") as mock_cls:
        client = MagicMock()
        client.export_link.side_effect = ApiError(
            code="out_of_credits", message="Need 5 credits, have 2", status=402
        )
        mock_cls.return_value = client
        result = await _tool_handler(
            "search_products", {"query": "lego", "export_format": "csv"}
        )

    assert "out of credits" in result[0].text.lower()
    assert "top up" in result[0].text.lower()


@pytest.mark.asyncio
async def test_export_format_explicit_xlsx(isolated_config_path):
    """export_format='xlsx' is passed through to export_link."""
    save_config(Config(base_url="https://a", token="t", token_label="l"))
    from actorio_cli.mcp_server import _tool_handler

    with patch("actorio_cli.mcp_server.Client") as mock_cls:
        client = MagicMock()
        client.search.return_value = {"results": [], "pagination": {"total": 0}}
        client.last_credits = None
        client.export_link.return_value = {
            "filename": "actorio-products.xlsx",
            "content_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "bytes": 999,
            "download_url": "https://a/exports/x/products.xlsx",
        }
        mock_cls.return_value = client
        await _tool_handler("search_products", {"export_format": "xlsx"})

    assert client.export_link.call_args.kwargs["export_format"] == "xlsx"


@pytest.fixture
def authenticated_http_context():
    """Simulates what AuthContextMiddleware does for a real OAuth-verified
    request — sets the same contextvar _tool_handler's get_access_token()
    reads, with a fake per-caller access token (as if issued via the OAuth
    flow in oauth_provider.py)."""
    from mcp.server.auth.middleware.auth_context import auth_context_var
    from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser
    from mcp.server.auth.provider import AccessToken

    access_token = AccessToken(token="act_test123", client_id="client-abc", scopes=[], subject="42")
    reset_token = auth_context_var.set(AuthenticatedUser(access_token))
    try:
        yield access_token
    finally:
        auth_context_var.reset(reset_token)


@pytest.mark.asyncio
async def test_search_with_export_format_over_http(isolated_config_path, authenticated_http_context):
    """Over HTTP transport, search with export_format calls export_link and
    uses the OAuth caller's token against DJANGO_BASE_URL.  The download_url
    is rewritten from DJANGO_BASE_URL to PUBLIC_BASE_URL so the MCP client
    can reach the download proxy route."""
    import actorio_cli.mcp_server as mcp_server
    mcp_server.PUBLIC_BASE_URL = "https://example.ngrok-free.app"
    mcp_server.DJANGO_BASE_URL = "https://app.actorio.example"
    try:
        with patch("actorio_cli.mcp_server.Client") as mock_cls:
            client = MagicMock()
            client.last_credits = {"cost": 4, "remaining": 995, "reset": "x"}
            client.redeem_quote.return_value = {
                "filename": "actorio-products.csv",
                "rows": 100,
                "bytes": 17,
                "credits_charged": 4,
                "expires_in": 900,
                "download_url": "https://app.actorio.example/cli/v1/exports/abc123/actorio-products.csv",
            }
            mock_cls.return_value = client
            result = await mcp_server._tool_handler(
                "export_results", {"quote_id": "q123"}
            )

        mock_cls.assert_called_once_with(
            base_url="https://app.actorio.example", token="act_test123"
        )
        client.redeem_quote.assert_called_once_with("q123")
        client.export.assert_not_called()
        parsed = json.loads(result[0].text)
        assert parsed["download_url"] == (
            "https://example.ngrok-free.app/cli/v1/exports/abc123/actorio-products.csv"
        )
    finally:
        mcp_server.PUBLIC_BASE_URL = None
        mcp_server.DJANGO_BASE_URL = None


@pytest.mark.asyncio
async def test_export_url_not_rewritten_when_urls_match(
    isolated_config_path, authenticated_http_context,
):
    """When PUBLIC_BASE_URL == DJANGO_BASE_URL (production — the MCP service
    and Django are behind the same domain), the download_url is passed
    through as-is since no rewrite is needed."""
    import actorio_cli.mcp_server as mcp_server
    # Same URL for both — typical prod setup behind a single reverse proxy.
    mcp_server.PUBLIC_BASE_URL = "https://api.actorio.com"
    mcp_server.DJANGO_BASE_URL = "https://api.actorio.com"
    try:
        with patch("actorio_cli.mcp_server.Client") as mock_cls:
            client = MagicMock()
            client.redeem_quote.return_value = {
                "filename": "f.csv",
                "rows": 1,
                "bytes": 5,
                "credits_charged": 1,
                "expires_in": 900,
                "download_url": "https://api.actorio.com/cli/v1/exports/t/f.csv",
            }
            mock_cls.return_value = client
            result = await mcp_server._tool_handler(
                "export_results", {"quote_id": "q1"}
            )

        parsed = json.loads(result[0].text)
        # URL unchanged — same domain, no proxy needed.
        assert parsed["download_url"] == (
            "https://api.actorio.com/cli/v1/exports/t/f.csv"
        )
    finally:
        mcp_server.PUBLIC_BASE_URL = None
        mcp_server.DJANGO_BASE_URL = None


@pytest.mark.asyncio
async def test_http_transport_rejects_unauthenticated_call(isolated_config_path):
    """PUBLIC_BASE_URL set (HTTP transport) but no access token in context
    (RequireAuthMiddleware would normally have rejected this before it ever
    reached here) — _tool_handler must not fall back to any shared config."""
    import actorio_cli.mcp_server as mcp_server
    mcp_server.PUBLIC_BASE_URL = "https://example.ngrok-free.app"
    try:
        result = await mcp_server._tool_handler("get_usage", {})
    finally:
        mcp_server.PUBLIC_BASE_URL = None
    assert "not authenticated" in result[0].text.lower()


@pytest.mark.asyncio
async def test_reverse_lookup_maps_asins(isolated_config_path):
    save_config(Config(base_url="https://a", token="t", token_label="l"))
    from actorio_cli.mcp_server import _tool_handler
    with patch("actorio_cli.mcp_server.Client") as mock_cls:
        client = MagicMock()
        client.search.return_value = {"results": [], "pagination": {}}
        client.last_credits = None
        mock_cls.return_value = client
        await _tool_handler("reverse_lookup", {"asins": "B000000001 B000000002"})
    params = client.search.call_args.args[1]
    assert params["asin_list"] == "B000000001 B000000002"


@pytest.mark.asyncio
async def test_get_usage_tool(isolated_config_path):
    save_config(Config(base_url="https://a", token="t", token_label="l"))
    from actorio_cli.mcp_server import _tool_handler
    with patch("actorio_cli.mcp_server.Client") as mock_cls:
        client = MagicMock()
        client.usage.return_value = {"monthly_included": 2000, "effective_remaining": 1500}
        mock_cls.return_value = client
        result = await _tool_handler("get_usage", {})
    parsed = json.loads(result[0].text)
    assert parsed["effective_remaining"] == 1500


@pytest.mark.asyncio
async def test_all_tools_have_schemas(isolated_config_path):
    from actorio_cli.mcp_server import TOOLS
    names = {t.name for t in TOOLS}
    assert names == {
        "search_products", "search_favorites", "search_amazon",
        "reverse_lookup", "export_results", "get_usage",
    }
    products = next(t for t in TOOLS if t.name == "search_products")
    props = products.inputSchema["properties"]
    for key in ("roi_min", "profit_month_max", "missing_fba", "category", "sort",
                "export_format", "exclude_multipack", "exclude_variations",
                "exclude_hazmat", "exclude_suppressed_buybox"):
        assert key in props, f"missing {key}"


def test_stdio_tool_descriptions_say_search_costs_credit():
    """Over stdio the description must not claim searches are free — agents
    plan credit spend from it, and stdio searches cost 1 credit."""
    from actorio_cli.mcp_server import TOOLS

    products = next(t for t in TOOLS if t.name == "search_products")
    assert "FREE" not in products.description
    assert "1 credit" in products.description
    favorites = next(t for t in TOOLS if t.name == "search_favorites")
    assert "FREE" not in favorites.description
    export_prop = products.inputSchema["properties"]["export_format"]
    assert "free either way" not in export_prop["description"]


def test_http_tool_descriptions_say_search_is_free():
    """Over HTTP the free aggregate+quote flow is real, so the description
    keeps the free wording."""
    from actorio_cli.mcp_server import _build_tools

    tools = _build_tools(free_search=True)
    products = next(t for t in tools if t.name == "search_products")
    assert "FREE" in products.description
    export_prop = products.inputSchema["properties"]["export_format"]
    assert "free either way" in export_prop["description"]


def test_exclude_flag_aliases_map_to_api_params():
    """exclude_* tool args map to the webapp filterset's param names; the
    old un-prefixed names still work for backward compatibility."""
    from actorio_cli.mcp_server import _to_query_params

    assert _to_query_params({"exclude_multipack": True}) == {"multipack": "true"}
    assert _to_query_params({"multipack": True}) == {"multipack": "true"}
    assert _to_query_params(
        {"exclude_variations": True, "exclude_hazmat": True}
    ) == {"variations": "true", "hazmat": "true"}
    # prefixed wins over legacy when both are present
    assert _to_query_params(
        {"multipack": True, "exclude_multipack": False}
    ) == {}


@pytest.mark.asyncio
async def test_search_schema_accepts_export_format():
    """search_products schema must accept export_format='csv' — the jsonschema
    validation happens before _tool_handler runs."""
    import jsonschema
    from actorio_cli.mcp_server import TOOLS

    products = next(t for t in TOOLS if t.name == "search_products")
    jsonschema.validate(
        instance={"query": "lego", "export_format": "csv"},
        schema=products.inputSchema,
    )
    jsonschema.validate(
        instance={"query": "lego", "export_format": "xlsx"},
        schema=products.inputSchema,
    )


# ---------------------------------------------------------------------------
# HTTP transport search paths — exercises the PUBLIC_BASE_URL branch for
# search tools (not just exports), ensuring the OAuth access token is used
# against DJANGO_BASE_URL for every tool call.
# ---------------------------------------------------------------------------

@pytest.fixture
def http_context():
    """Sets PUBLIC_BASE_URL + DJANGO_BASE_URL to simulate HTTP transport."""
    import actorio_cli.mcp_server as mcp_server

    mcp_server.PUBLIC_BASE_URL = "https://example.ngrok-free.app"
    mcp_server.DJANGO_BASE_URL = "https://app.actorio.example"
    try:
        yield
    finally:
        mcp_server.PUBLIC_BASE_URL = None
        mcp_server.DJANGO_BASE_URL = None


@pytest.fixture
def http_auth_context():
    """Simulates an OAuth-verified HTTP request context (same pattern as
    authenticated_http_context above)."""
    from mcp.server.auth.middleware.auth_context import auth_context_var
    from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser
    from mcp.server.auth.provider import AccessToken

    access_token = AccessToken(
        token="act_http_test", client_id="client-xyz", scopes=[], subject="99"
    )
    reset_token = auth_context_var.set(AuthenticatedUser(access_token))
    try:
        yield access_token
    finally:
        auth_context_var.reset(reset_token)


@pytest.mark.asyncio
async def test_http_transport_search_products(isolated_config_path, http_context, http_auth_context):
    """Over HTTP transport, search_products uses the OAuth caller's token
    against DJANGO_BASE_URL, not the local config file."""
    import actorio_cli.mcp_server as mcp_server

    with patch("actorio_cli.mcp_server.Client") as mock_cls:
        client = MagicMock()
        client.mcp_search.return_value = {
            "summary": {"total": 1},
            "teaser": [{"price": 9.99, "max_profit": 3.5}],
            "free": True,
            "quote": {"quote_id": "q9", "rows": 1, "credits": 1,
                      "format": "csv", "expires_in": 900},
        }
        client.last_credits = {"cost": 0, "remaining": 499, "reset": "x", "warning": None}
        mock_cls.return_value = client
        result = await mcp_server._tool_handler(
            "search_products", {"query": "widget", "country": "DE", "limit": 10}
        )

    mock_cls.assert_called_once_with(
        base_url="https://app.actorio.example", token="act_http_test"
    )
    parsed = json.loads(result[0].text)
    assert parsed["free"] is True
    assert parsed["quote"]["credits"] == 1
    assert parsed["teaser"][0]["max_profit"] == 3.5
    # the teaser must never carry sourcing identifiers
    assert "asin" not in parsed["teaser"][0]
    assert parsed["_meta"]["credits"]["remaining"] == 499


@pytest.mark.asyncio
async def test_http_transport_get_usage(isolated_config_path, http_context, http_auth_context):
    """get_usage over HTTP transport — same OAuth token path as search."""
    import actorio_cli.mcp_server as mcp_server

    with patch("actorio_cli.mcp_server.Client") as mock_cls:
        client = MagicMock()
        client.usage.return_value = {"effective_remaining": 1234}
        mock_cls.return_value = client
        result = await mcp_server._tool_handler("get_usage", {})

    mock_cls.assert_called_once_with(
        base_url="https://app.actorio.example", token="act_http_test"
    )
    parsed = json.loads(result[0].text)
    assert parsed["effective_remaining"] == 1234


@pytest.mark.asyncio
async def test_http_transport_search_with_export_format(
    isolated_config_path, http_context, http_auth_context
):
    """Search with export_format over HTTP — credit meta from export_link is included."""
    import actorio_cli.mcp_server as mcp_server

    with patch("actorio_cli.mcp_server.Client") as mock_cls:
        client = MagicMock()
        payload = {
            "filename": "actorio-products.csv",
            "rows": 50,
            "bytes": 99,
            "credits_charged": 2,
            "expires_in": 900,
            "download_url": "https://app.actorio.example/cli/v1/exports/x/products.csv",
        }
        # Redemption is what spends credits; the search before it was free.
        def _redeem_side_effect(*args, **kwargs):
            client.last_credits = {"cost": 2, "remaining": 495, "reset": "x", "warning": None}
            return payload
        client.redeem_quote.side_effect = _redeem_side_effect

        mock_cls.return_value = client
        result = await mcp_server._tool_handler(
            "export_results", {"quote_id": "qx"}
        )

    parsed = json.loads(result[0].text)
    assert parsed["_meta"]["credits"]["cost"] == 2
    assert parsed["_meta"]["credits"]["remaining"] == 495
    assert parsed["download_url"].endswith("products.csv")


# ---------------------------------------------------------------------------
# Error handling — every ApiError code path, not just out_of_credits.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tool_upgrade_required_message(isolated_config_path):
    save_config(Config(base_url="https://a", token="t", token_label="l"))
    from actorio_cli.client import ApiError
    from actorio_cli.mcp_server import _tool_handler

    with patch("actorio_cli.mcp_server.Client") as mock_cls:
        client = MagicMock()
        client.search.side_effect = ApiError(
            code="upgrade_required", message="Needs Pro plan", status=402
        )
        mock_cls.return_value = client
        result = await _tool_handler("search_products", {})
    assert "upgrade required" in result[0].text.lower()
    assert "pro plan" in result[0].text.lower()


@pytest.mark.asyncio
async def test_tool_generic_api_error(isolated_config_path):
    save_config(Config(base_url="https://a", token="t", token_label="l"))
    from actorio_cli.client import ApiError
    from actorio_cli.mcp_server import _tool_handler

    with patch("actorio_cli.mcp_server.Client") as mock_cls:
        client = MagicMock()
        client.search.side_effect = ApiError(
            code="internal_error", message="Backend is down", status=500
        )
        mock_cls.return_value = client
        result = await _tool_handler("search_products", {})
    assert "internal_error" in result[0].text
    assert "Backend is down" in result[0].text


@pytest.mark.asyncio
async def test_export_format_out_of_credits(isolated_config_path):
    """export_format path surfaces out_of_credits with a helpful message."""
    save_config(Config(base_url="https://a", token="t", token_label="l"))
    from actorio_cli.client import ApiError
    from actorio_cli.mcp_server import _tool_handler

    with patch("actorio_cli.mcp_server.Client") as mock_cls:
        client = MagicMock()
        client.export_link.side_effect = ApiError(
            code="out_of_credits", message="0 credits left", status=402
        )
        mock_cls.return_value = client
        result = await _tool_handler(
            "search_products", {"query": "lego", "export_format": "csv"}
        )

    assert "out of credits" in result[0].text.lower()


@pytest.mark.asyncio
async def test_export_format_out_of_credits_over_http(
    isolated_config_path, http_context, http_auth_context
):
    """export_format over HTTP — out_of_credits is surfaced, not swallowed."""
    import actorio_cli.mcp_server as mcp_server
    from actorio_cli.client import ApiError

    with patch("actorio_cli.mcp_server.Client") as mock_cls:
        client = MagicMock()
        client.mcp_search.side_effect = ApiError(
            code="out_of_credits", message="Export costs 5 credits", status=402
        )
        mock_cls.return_value = client
        result = await mcp_server._tool_handler(
            "search_products", {"query": "lego", "export_format": "csv"}
        )

    assert "out of credits" in result[0].text.lower()


@pytest.mark.asyncio
async def test_get_usage_api_error(isolated_config_path):
    save_config(Config(base_url="https://a", token="t", token_label="l"))
    from actorio_cli.client import ApiError
    from actorio_cli.mcp_server import _tool_handler

    with patch("actorio_cli.mcp_server.Client") as mock_cls:
        client = MagicMock()
        client.usage.side_effect = ApiError(
            code="unauthorized", message="Token revoked", status=401
        )
        mock_cls.return_value = client
        result = await _tool_handler("get_usage", {})
    assert "unauthorized" in result[0].text.lower()


# ---------------------------------------------------------------------------
# make_server — server metadata and decorator wiring.
# ---------------------------------------------------------------------------


def test_make_server_metadata():
    """Server name, version, website_url, and icons are set correctly."""
    from actorio_cli.mcp_server import make_server

    server = make_server()
    assert server.name == "actorio"
    assert server.version == "0.1.0"
    assert server.instructions is None  # not set
    assert server.website_url == "https://actorio.com"
    assert len(server.icons) == 1
    icon = server.icons[0]
    assert "favicon.ico" in icon.src
    assert "16x16" in icon.sizes
    assert "32x32" in icon.sizes


@pytest.mark.asyncio
async def test_make_server_list_tools():
    """The list_tools decorator registers a handler that returns all TOOLS."""
    from mcp.types import ListToolsRequest
    from actorio_cli.mcp_server import make_server, TOOLS

    server = make_server()
    handler = server.request_handlers[ListToolsRequest]
    result = await handler(ListToolsRequest(method="tools/list"))
    # result is a ServerResult (pydantic model) wrapping ListToolsResult in .root
    assert result.root.tools == TOOLS


# ---------------------------------------------------------------------------
# Query param mapping — _to_query_params edge cases.
# ---------------------------------------------------------------------------


def test_to_query_params_remaps_query_to_keywords():
    from actorio_cli.mcp_server import _to_query_params

    params = _to_query_params({"query": "lego set", "country": "DE"})
    assert "query" not in params
    assert params["keywords"] == "lego set"
    assert params["country"] == "DE"


def test_to_query_params_remaps_asins_to_asin_list():
    from actorio_cli.mcp_server import _to_query_params

    params = _to_query_params({"asins": "B001 B002"})
    assert "asins" not in params
    assert params["asin_list"] == "B001 B002"


def test_to_query_params_handles_empty_and_none():
    from actorio_cli.mcp_server import _to_query_params

    assert _to_query_params({}) == {}
    assert _to_query_params(None) == {}


# ---------------------------------------------------------------------------
# build_http_app — additional OAuth wiring tests.
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _mcp_internal_secret(monkeypatch):
    """All build_http_app tests need MCP_OAUTH_INTERNAL_SECRET set in the env."""
    monkeypatch.setenv("MCP_OAUTH_INTERNAL_SECRET", "test-secret")


def test_build_http_app_sets_module_globals():
    """build_http_app must set PUBLIC_BASE_URL and DJANGO_BASE_URL so
    _tool_handler picks them up."""
    import actorio_cli.mcp_server as mcp_server

    try:
        app = mcp_server.build_http_app(
            host="127.0.0.1",
            port=9999,
            public_url="https://my-ngrok.ngrok-free.app",
            api_base_url="https://api.actorio.com",
        )
        assert mcp_server.PUBLIC_BASE_URL == "https://my-ngrok.ngrok-free.app"
        assert mcp_server.DJANGO_BASE_URL == "https://api.actorio.com"
    finally:
        mcp_server.PUBLIC_BASE_URL = None
        mcp_server.DJANGO_BASE_URL = None


def test_build_http_app_defaults_api_base_url():
    """Without api_base_url, defaults to http://127.0.0.1:9000."""
    import actorio_cli.mcp_server as mcp_server

    try:
        app = mcp_server.build_http_app(host="127.0.0.1", port=8888)
        assert mcp_server.DJANGO_BASE_URL == "http://127.0.0.1:9000"
    finally:
        mcp_server.PUBLIC_BASE_URL = None
        mcp_server.DJANGO_BASE_URL = None


def test_build_http_app_missing_secret_raises(monkeypatch):
    """build_http_app must raise if MCP_OAUTH_INTERNAL_SECRET is unset."""
    import actorio_cli.mcp_server as mcp_server

    monkeypatch.delenv("MCP_OAUTH_INTERNAL_SECRET", raising=False)
    with pytest.raises(RuntimeError, match="MCP_OAUTH_INTERNAL_SECRET"):
        mcp_server.build_http_app()


def test_build_http_app_well_known_endpoints_exist():
    """All expected OAuth well-known + MCP routes are mounted."""
    from starlette.testclient import TestClient
    import actorio_cli.mcp_server as mcp_server

    try:
        app = mcp_server.build_http_app(
            public_url="https://example.ngrok-free.app",
            api_base_url="https://api.example.com",
        )
        with TestClient(app) as client:
            # OAuth authorization server metadata
            resp = client.get("/.well-known/oauth-authorization-server")
            assert resp.status_code == 200
            # Protected resource metadata
            resp = client.get("/.well-known/oauth-protected-resource/mcp")
            assert resp.status_code == 200
    finally:
        mcp_server.PUBLIC_BASE_URL = None
        mcp_server.DJANGO_BASE_URL = None


def test_build_http_app_revocation_endpoint_exists():
    """The revocation endpoint is mounted and rejects unauthenticated calls
    (it requires a valid bearer token, not an internal secret — our
    internal_secret header is only for the /oauth/internal/... backend calls)."""
    from starlette.testclient import TestClient
    import actorio_cli.mcp_server as mcp_server

    try:
        app = mcp_server.build_http_app(
            public_url="https://example.ngrok-free.app",
            api_base_url="https://api.example.com",
        )
        with TestClient(app) as client:
            resp = client.post("/revoke", json={"token": "x"})
            # 401 because no bearer token; proves the endpoint exists and is
            # protected, not that it's broken.
            assert resp.status_code == 401
    finally:
        mcp_server.PUBLIC_BASE_URL = None
        mcp_server.DJANGO_BASE_URL = None


# ---------------------------------------------------------------------------
# Tool schema validation — ensure all tool schemas are valid JSON Schema.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "tool_name,required_keys",
    [
        ("search_products", []),
        ("search_favorites", []),
        ("search_amazon", []),
        ("reverse_lookup", ["asins"]),
        ("get_usage", []),
    ],
)
def test_tool_schema_required_fields(tool_name, required_keys):
    """Each tool declares the correct required fields in its inputSchema."""
    from actorio_cli.mcp_server import TOOLS

    tool = next(t for t in TOOLS if t.name == tool_name)
    assert tool.inputSchema.get("required", []) == required_keys


def test_reverse_lookup_requires_asins():
    """reverse_lookup must require 'asins' — it's the only way to specify what
    to look up."""
    from actorio_cli.mcp_server import TOOLS

    reverse = next(t for t in TOOLS if t.name == "reverse_lookup")
    assert "asins" in reverse.inputSchema.get("required", [])


def test_get_usage_schema_is_minimal():
    """get_usage has no required params and no filter properties."""
    from actorio_cli.mcp_server import TOOLS

    usage = next(t for t in TOOLS if t.name == "get_usage")
    assert usage.inputSchema == {"type": "object", "properties": {}}


def test_all_search_tools_have_pagination_props():
    """Every search tool exposes limit/offset for pagination."""
    from actorio_cli.mcp_server import TOOLS

    for tool in TOOLS:
        if tool.name in ("get_usage", "export_results"):
            continue
        props = tool.inputSchema["properties"]
        assert "limit" in props, f"{tool.name} missing limit"
        assert "offset" in props, f"{tool.name} missing offset"


def test_tool_annotations_read_only():
    """Searches are readOnlyHint=True; export_results is not, because it
    spends the user's credits — a host that treats it as read-only might
    call it without asking, which is exactly what must not happen."""
    from actorio_cli.mcp_server import TOOLS

    for tool in TOOLS:
        assert tool.annotations is not None, f"{tool.name} missing annotations"
        expected = tool.name != "export_results"
        assert tool.annotations.readOnlyHint is expected, (
            f"{tool.name} should be readOnlyHint={expected}"
        )
        if not expected:
            # destructiveHint/openWorldHint default to TRUE for non-read-only
            # tools, which made ChatGPT render this as DESTRUCTIVE and refuse
            # to expose it. Both must be explicitly false.
            assert tool.annotations.destructiveHint is False
            assert tool.annotations.openWorldHint is False


# ---------------------------------------------------------------------------
# Search param round-trip — filter params reach the client correctly.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_passes_range_filters(isolated_config_path):
    save_config(Config(base_url="https://a", token="t", token_label="l"))
    from actorio_cli.mcp_server import _tool_handler

    with patch("actorio_cli.mcp_server.Client") as mock_cls:
        client = MagicMock()
        client.search.return_value = {
            "results": [],
            "pagination": {"page": 1, "per_page": 20, "total": 0, "has_more": False},
        }
        client.last_credits = None
        mock_cls.return_value = client
        await _tool_handler(
            "search_products",
            {
                "roi_min": 30,
                "profit_min": 5.5,
                "price_max": 100,
                "sales_month_min": 50,
            },
        )

    params = client.search.call_args.args[1]
    assert params["roi_min"] == 30
    assert params["profit_min"] == 5.5
    assert params["price_max"] == 100
    assert params["sales_month_min"] == 50


@pytest.mark.asyncio
async def test_search_passes_boolean_filters(isolated_config_path):
    save_config(Config(base_url="https://a", token="t", token_label="l"))
    from actorio_cli.mcp_server import _tool_handler

    with patch("actorio_cli.mcp_server.Client") as mock_cls:
        client = MagicMock()
        client.search.return_value = {
            "results": [],
            "pagination": {"page": 1, "per_page": 20, "total": 0, "has_more": False},
        }
        client.last_credits = None
        mock_cls.return_value = client
        await _tool_handler(
            "search_products",
            {"missing_fba": True, "multipack": True, "hazmat": True},
        )

    params = client.search.call_args.args[1]
    assert params["missing_fba"] == "true"
    assert params["multipack"] == "true"
    assert params["hazmat"] == "true"


@pytest.mark.asyncio
async def test_search_passes_array_filters(isolated_config_path):
    save_config(Config(base_url="https://a", token="t", token_label="l"))
    from actorio_cli.mcp_server import _tool_handler

    with patch("actorio_cli.mcp_server.Client") as mock_cls:
        client = MagicMock()
        client.search.return_value = {
            "results": [],
            "pagination": {"page": 1, "per_page": 20, "total": 0, "has_more": False},
        }
        client.last_credits = None
        mock_cls.return_value = client
        await _tool_handler(
            "search_products",
            {"size": ["LGT_ENV", "STD_ENV"], "category": ["toys", "games"]},
        )

    params = client.search.call_args.args[1]
    assert params["size"] == ["LGT_ENV", "STD_ENV"]
    assert params["category"] == ["toys", "games"]


@pytest.mark.asyncio
async def test_search_amazon_tool(isolated_config_path):
    save_config(Config(base_url="https://a", token="t", token_label="l"))
    from actorio_cli.mcp_server import _tool_handler

    with patch("actorio_cli.mcp_server.Client") as mock_cls:
        client = MagicMock()
        client.search.return_value = {
            "results": [],
            "pagination": {"page": 1, "per_page": 20, "total": 0, "has_more": False},
        }
        client.last_credits = None
        mock_cls.return_value = client
        result = await _tool_handler(
            "search_amazon",
            {"marketplace": "DE", "store": "amazon.de", "roi_min": 10},
        )

    assert client.search.call_args.args[0] == "amazon"
    params = client.search.call_args.args[1]
    assert params["marketplace"] == "DE"
    assert params["store"] == "amazon.de"
    assert params["roi_min"] == 10
    parsed = json.loads(result[0].text)
    assert "results" in parsed


@pytest.mark.asyncio
async def test_search_favorites_tool(isolated_config_path):
    save_config(Config(base_url="https://a", token="t", token_label="l"))
    from actorio_cli.mcp_server import _tool_handler

    with patch("actorio_cli.mcp_server.Client") as mock_cls:
        client = MagicMock()
        client.search.return_value = {
            "results": [],
            "pagination": {"page": 1, "per_page": 20, "total": 0, "has_more": False},
        }
        client.last_credits = None
        mock_cls.return_value = client
        result = await _tool_handler("search_favorites", {"country": "GB"})

    assert client.search.call_args.args[0] == "favorites"
    parsed = json.loads(result[0].text)
    assert "results" in parsed


@pytest.mark.asyncio
async def test_search_limit_offset_stripped_from_params(isolated_config_path):
    """limit/offset control pagination (passed to client.search as kwargs),
    not API-level filter params."""
    save_config(Config(base_url="https://a", token="t", token_label="l"))
    from actorio_cli.mcp_server import _tool_handler

    with patch("actorio_cli.mcp_server.Client") as mock_cls:
        client = MagicMock()
        client.search.return_value = {
            "results": [],
            "pagination": {"page": 1, "per_page": 20, "total": 0, "has_more": False},
        }
        client.last_credits = None
        mock_cls.return_value = client
        await _tool_handler("search_products", {"limit": 50, "offset": 100, "query": "test"})

    call = client.search.call_args
    # limit/offset go as kwargs, not in the params dict
    assert call.kwargs["limit"] == 50
    assert call.kwargs["offset"] == 100
    params = call.args[1]
    assert "limit" not in params
    assert "offset" not in params
    assert params["keywords"] == "test"


@pytest.mark.asyncio
async def test_http_transport_reverse_lookup(
    isolated_config_path, http_context, http_auth_context
):
    """reverse_lookup over HTTP transport — asins are remapped correctly."""
    import actorio_cli.mcp_server as mcp_server

    with patch("actorio_cli.mcp_server.Client") as mock_cls:
        client = MagicMock()
        client.mcp_search.return_value = {
            "summary": {"total": 0}, "preview": [], "preview_count": 0,
        }
        client.last_credits = None
        mock_cls.return_value = client
        await mcp_server._tool_handler(
            "reverse_lookup", {"asins": "B000000001", "actorio_only": True}
        )

    mock_cls.assert_called_once_with(
        base_url="https://app.actorio.example", token="act_http_test"
    )
    params = client.mcp_search.call_args.args[1]
    assert params["asin_list"] == "B000000001"
    assert params["actorio_only"] == "true"


# ---------------------------------------------------------------------------
# Auto-export: when a search returns more results than the current page
# contains, _tool_handler also calls export_link so the AI can offer a
# download immediately — one interaction instead of two.
# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# Truncation resilience. ChatGPT truncates large tool results, and a
# full-fidelity product row is ~5KB (186 fields) so a 10-result page runs
# ~50KB. Whatever json.dumps emits last is what the model never reads, so
# credits and the export hint have to lead the payload, not trail it.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_meta_precedes_bulky_results_in_payload(isolated_config_path):
    save_config(Config(base_url="https://a", token="t", token_label="l"))
    from actorio_cli.mcp_server import _tool_handler
    with patch("actorio_cli.mcp_server.Client") as mock_cls:
        client = MagicMock()
        client.search.return_value = {
            "results": [{"padding": "x" * 5000} for _ in range(10)],
            "pagination": {"total": 10, "limit": 10, "offset": 0},
        }
        client.last_credits = {"cost": 1, "remaining": 999, "reset": "x", "warning": None}
        mock_cls.return_value = client
        result = await _tool_handler("search_products", {})
    text = result[0].text
    assert text.index('"_meta"') < text.index('"results"')
    # and it survives a hard truncation of the tail
    assert '"_meta"' in text[:2000]


@pytest.mark.asyncio
async def test_export_hint_when_more_matches_than_shown(isolated_config_path):
    save_config(Config(base_url="https://a", token="t", token_label="l"))
    from actorio_cli.mcp_server import _tool_handler
    with patch("actorio_cli.mcp_server.Client") as mock_cls:
        client = MagicMock()
        client.search.return_value = {
            "results": [{"a": 1} for _ in range(10)],
            "pagination": {"total": 1675, "limit": 10, "offset": 0},
        }
        client.last_credits = None
        mock_cls.return_value = client
        result = await _tool_handler("search_products", {})
    text = result[0].text
    parsed = json.loads(text)
    hint = parsed["_hint"]
    assert "1675" in hint
    assert "export_format" in hint
    assert "search_products" in hint          # names the tool to call again
    assert text.index('"_hint"') < text.index('"results"')


@pytest.mark.asyncio
async def test_no_export_hint_when_all_matches_shown(isolated_config_path):
    save_config(Config(base_url="https://a", token="t", token_label="l"))
    from actorio_cli.mcp_server import _tool_handler
    with patch("actorio_cli.mcp_server.Client") as mock_cls:
        client = MagicMock()
        client.search.return_value = {
            "results": [{"a": 1} for _ in range(3)],
            "pagination": {"total": 3, "limit": 10, "offset": 0},
        }
        client.last_credits = None
        mock_cls.return_value = client
        result = await _tool_handler("search_products", {})
    assert "_hint" not in json.loads(result[0].text)


@pytest.mark.asyncio
async def test_export_response_leads_with_meta(isolated_config_path):
    save_config(Config(base_url="https://a", token="t", token_label="l"))
    from actorio_cli.mcp_server import _tool_handler
    with patch("actorio_cli.mcp_server.Client") as mock_cls:
        client = MagicMock()
        client.export_link.return_value = {
            "download_url": "https://api-dev.example/cli/v1/exports/tok/f.csv",
            "filename": "f.csv",
            "bytes": 1329256,
        }
        client.last_credits = {"cost": 5, "remaining": 994, "reset": "x", "warning": None}
        mock_cls.return_value = client
        result = await _tool_handler("search_products", {"export_format": "csv"})
    text = result[0].text
    assert text.index('"_meta"') < text.index('"_export"')
    assert json.loads(text)["_export"]["bytes"] == 1329256


@pytest.mark.asyncio
async def test_export_returns_a_structured_resource_link(
    isolated_config_path, http_context, http_auth_context
):
    """The URL goes back as a resource_link as well as in the JSON, so the
    host renders it directly. A model retyping a URL in prose has been seen
    to 'correct' the domain to whatever looks canonical."""
    import actorio_cli.mcp_server as mcp_server

    with patch("actorio_cli.mcp_server.Client") as mock_cls:
        client = MagicMock()
        client.redeem_quote.return_value = {
            "filename": "actorio-product-search.csv",
            "rows": 1174,
            "bytes": 924354,
            "credits_charged": 8,
            "expires_in": 900,
            "download_url": "https://api-dev.getactorio.com/cli/v1/exports/tok/actorio-product-search.csv",
        }
        client.last_credits = None
        mock_cls.return_value = client
        result = await mcp_server._tool_handler("export_results", {"quote_id": "q"})

    links = [c for c in result if getattr(c, "type", None) == "resource_link"]
    assert len(links) == 1, "expected exactly one resource_link"
    link = links[0]
    # the host-rendered URL must be byte-identical to what the server issued
    assert str(link.uri) == (
        "https://api-dev.getactorio.com/cli/v1/exports/tok/actorio-product-search.csv"
    )
    assert link.mimeType == "text/csv"
    assert link.size == 924354


@pytest.mark.asyncio
async def test_buy_quote_id_parameter_redeems_on_the_search_tool(
    isolated_config_path, http_context, http_auth_context
):
    """Redemption has to be reachable via a parameter on a tool the client
    already has. As a separate tool it was never exposed to the model by
    ChatGPT, which then invented download URLs instead of saying it couldn't
    call it — a parameter cannot go missing from an existing tool."""
    import actorio_cli.mcp_server as mcp_server

    with patch("actorio_cli.mcp_server.Client") as mock_cls:
        client = MagicMock()
        client.redeem_quote.return_value = {
            "filename": "actorio-product-search.csv",
            "rows": 1174, "bytes": 924354,
            "credits_charged": 8, "expires_in": 900,
            "download_url": "https://api-dev.getactorio.com/cli/v1/exports/tok/f.csv",
        }
        client.last_credits = None
        mock_cls.return_value = client
        result = await mcp_server._tool_handler(
            "search_products", {"buy_quote_id": "q42"}
        )

    client.redeem_quote.assert_called_once_with("q42")
    client.mcp_search.assert_not_called()      # buying, not searching
    parsed = json.loads(result[0].text)
    assert parsed["download_url"].endswith("/exports/tok/f.csv")
    assert parsed["rows"] == 1174


def test_buy_quote_id_is_on_every_search_tool():
    """Whichever search a host exposes, buying must be reachable from it."""
    from actorio_cli.mcp_server import TOOLS
    for tool in TOOLS:
        if tool.name in ("get_usage", "export_results"):
            continue
        assert "buy_quote_id" in tool.inputSchema["properties"], tool.name
