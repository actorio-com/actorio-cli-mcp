import base64
import json
from typing import Any

from pydantic import AnyUrl

from mcp.server import Server
from mcp.types import (
    BlobResourceContents,
    EmbeddedResource,
    Icon,
    ResourceLink,
    TextContent,
    TextResourceContents,
    Tool,
    ToolAnnotations,
)

from actorio_cli.client import Client, ApiError
from actorio_cli.commands._filters import build_params
from actorio_cli.config import load_config

# Both set by run_http() when serving over Streamable HTTP.
# PUBLIC_BASE_URL: this service's own public URL (an ngrok https URL for
#   local testing), used as the OAuth issuer.
# DJANGO_BASE_URL: where the actual Actorio API lives — HTTP-transport
#   calls use the OAuth-verified caller's own token against this, instead
#   of stdio's single ~/.actorio/config.json. Export downloads over HTTP
#   transport, export download URLs are rewritten from DJANGO_BASE_URL to
#   PUBLIC_BASE_URL and proxied back to Django by _handle_export_download.
PUBLIC_BASE_URL: str | None = None
DJANGO_BASE_URL: str | None = None


# ---------------------------------------------------------------------------
# Filter schemas — mirror the webapp filtersets (ecommercer/filters.py), the
# same query params the CLI flags map to. Anything the web UI can filter on,
# an agent can too.
# ---------------------------------------------------------------------------

_PAGINATION_PROPS = {
    "limit": {
        "type": "integer",
        "description": "Results per request (server default: 20, or 16 for reverse search; max 100)",
    },
    "offset": {
        "type": "integer",
        "default": 0,
        "description": "Skip this many results",
    },
}

_LOGIC = {
    "type": "string",
    "enum": ["all"],
    "description": "Omit for ANY marketplace; 'all' requires every marketplace to match",
}

_RANGE_FILTER_PROPS = {
    "price_min": {"type": "number", "description": "Min supplier price, VAT incl. (gross)"},
    "price_max": {"type": "number", "description": "Max supplier price, VAT incl. (gross)"},
    "competitive_price_min": {"type": "number"},
    "competitive_price_max": {"type": "number"},
    "competitive_price_logic": _LOGIC,
    "profit_min": {"type": "number", "description": "Min estimated profit per unit"},
    "profit_max": {"type": "number"},
    "profit_logic": _LOGIC,
    "roi_min": {"type": "number", "description": "Min ROI (%)"},
    "roi_max": {"type": "number"},
    "roi_logic": _LOGIC,
    "profit_month_min": {"type": "number", "description": "Min estimated monthly profit"},
    "profit_month_max": {"type": "number"},
    "profit_month_logic": _LOGIC,
    "sales_month_min": {"type": "number", "description": "Min estimated monthly sales"},
    "sales_month_max": {"type": "number"},
    "sales_month_logic": _LOGIC,
}

_COMMON_FILTER_PROPS = {
    "query": {"type": "string", "description": "Keywords (title search)"},
    "upc_list": {"type": "string", "description": "Comma/space separated UPC/EANs"},
    "asin_list": {"type": "string", "description": "Comma/space separated ASINs"},
    "marketplace": {
        "type": "string",
        "enum": ["DE", "ES", "FR", "GB", "IT"],
        "description": "Target Amazon marketplace to compare against (omit = ALL)",
    },
    "price_reference": {
        "type": "string",
        "enum": ["avg30"],
        "description": "Use 30-day average Amazon prices instead of live prices",
    },
    "last_update": {
        "type": "string",
        "enum": ["24", "48"],
        "description": "Only products updated in the last N hours",
    },
    "missing_fba": {"type": "boolean", "description": "Only listings with complete FBA data (excludes incomplete listings)"},
    "exclude_multipack": {"type": "boolean", "description": "Exclude multipacks (pack quantity > 1)"},
    "size": {
        "type": "array",
        "items": {"type": "string"},
        "description": "Size category codes, e.g. LGT_ENV, STD_ENV, SML_PAR",
    },
    "category": {
        "type": "array",
        "items": {"type": "string"},
        "description": "Amazon category codes",
    },
    "sort": {
        "type": "string",
        "description": (
            "Sort key, e.g. profit, -profit (prefix '-' = descending). "
            "Valid keys: identifiers, store_image, store_price, price, "
            "amazon_price, profit, roi, margin, sales_rank, profit_month, "
            "sales_month, last_scan, last_update."
        ),
    },
    **_RANGE_FILTER_PROPS,
}

_PRODUCTS_FILTER_PROPS = {
    **_COMMON_FILTER_PROPS,
    "country": {"type": "string", "description": "Source country code, e.g. DE, ES, GB"},
    "type": {
        "type": "string",
        "enum": ["RTL", "WHL", "UPL", "EXC"],
        "description": "Supplier type: retailer, wholesaler, uploaded, exclusive",
    },
    "store": {
        "type": "array",
        "items": {"type": "string"},
        "description": "Supplier store names",
    },
    "exclude_variations": {"type": "boolean", "description": "Exclude listings with variations"},
    "exclude_hazmat": {"type": "boolean", "description": "Exclude hazmat products"},
    "exclude_suppressed_buybox": {"type": "boolean", "description": "Exclude suppressed-buybox listings"},
    "similarity": {"type": "integer", "description": "Match similarity level (0-3)"},
}

_AMAZON_FILTER_PROPS = {
    **_COMMON_FILTER_PROPS,
    "store": {
        "type": "string",
        "enum": ["amazon.de", "amazon.es", "amazon.fr", "amazon.co.uk", "amazon.it"],
        "description": "Source Amazon marketplace to buy from",
    },
}

_REVERSE_FILTER_PROPS = {
    "asins": {"type": "string", "description": "One or more ASINs, comma/space separated"},
    "actorio_only": {"type": "boolean", "description": "Only return ASINs with an Actorio supplier match"},
}

_CREDITS_NOTE = (
    "The response includes _meta.credits (cost of this call, credits "
    "remaining, reset date) — always tell the user their remaining balance "
    "after reporting the results, not just on request."
)


_BUY_PROP = {
    "buy_quote_id": {
        "type": "string",
        "description": (
            "Redeem a quote from a previous search and return the download "
            "link for the complete result set. CHARGES the credits the quote "
            "named — only pass this after the user has explicitly agreed to "
            "that price. When set, all other parameters are ignored."
        ),
    },
}

def _export_format_prop(free_search: bool) -> dict:
    """The export_format parameter. Over HTTP transport the search itself
    is free and the quote is the thing the format affects; over stdio the
    search costs 1 credit and the export is priced by tier — descriptions
    must match whichever flow the transport actually runs."""
    quote_text = (
        "Format to quote the downloadable file in: 'csv' (default) or "
        "'xlsx'. Only affects the quote — searching is free either way."
        if free_search
        else "Format for the downloadable file: 'csv' (default) or 'xlsx'. "
        "The search itself costs 1 credit; the export costs extra credits "
        "tiered by row count."
    )
    return {
        "export_format": {
            "type": "string",
            "enum": ["csv", "xlsx"],
            "description": quote_text,
        },
    }


# Transport-dependent notes appended to the search-tool descriptions.
# The free aggregate+quote flow only exists over HTTP (see _tool_handler);
# over stdio every search is a paid, full-row search — describing it as
# free would make AI agents mis-plan the user's credit spend.

_FREE_SEARCH_NOTE_HTTP = (
    "This search is FREE and returns no identifiable products: aggregate "
    "figures over all matches, anonymised sample numbers, and a quote saying "
    "how many rows the full list has and what it costs in credits. Report the "
    "summary, then ASK the user whether they want the full list at the quoted "
    "price. If they agree, GIVE THE USER the purchase_url link from the "
    "response — they click it to buy in their browser. Do not call a tool to "
    "charge credits. Never compose a download URL yourself."
)

_FREE_SEARCH_NOTE_STDIO = (
    "This search costs 1 credit and returns full product rows (up to "
    "`limit`, default 20; large pages may be truncated by the host). The "
    "response includes _meta.credits (cost of this call, remaining balance, "
    "reset date) — report the user's remaining balance along with the "
    "results. For the complete match set as a spreadsheet, call again with "
    "the same filters plus export_format='csv' (costs extra credits, tiered "
    "by row count)."
)


def _build_tools(free_search: bool) -> list[Tool]:
    search_note = _FREE_SEARCH_NOTE_HTTP if free_search else _FREE_SEARCH_NOTE_STDIO
    export_format_prop = _export_format_prop(free_search)

    return [
        Tool(
            name="search_products",
            description=(
                "Search Actorio's product catalog (EU retailers/wholesalers matched "
                "to Amazon listings with profit/ROI estimates). Supports every filter "
                "the web UI has. " + search_note
            ),
            inputSchema={
                "type": "object",
                "properties": {**_PRODUCTS_FILTER_PROPS, **export_format_prop, **_BUY_PROP, **_PAGINATION_PROPS},
            },
            annotations=ToolAnnotations(readOnlyHint=True),
        ),
        Tool(
            name="search_favorites",
            description=(
                "Search the current user's favorited products (same filters as "
                "search_products). " + search_note
            ),
            inputSchema={
                "type": "object",
                "properties": {**_PRODUCTS_FILTER_PROPS, **export_format_prop, **_BUY_PROP, **_PAGINATION_PROPS},
            },
            annotations=ToolAnnotations(readOnlyHint=True),
        ),
        Tool(
            name="search_amazon",
            description=(
                "Amazon Flip search: Amazon-to-Amazon EU arbitrage (buy on one "
                "marketplace, sell on another) with fees, buybox and profit data. "
                "Pass export_format='csv' to get a downloadable file alongside "
                "the summary. " + _CREDITS_NOTE
            ),
            inputSchema={
                "type": "object",
                "properties": {**_AMAZON_FILTER_PROPS, **export_format_prop, **_BUY_PROP, **_PAGINATION_PROPS},
            },
            annotations=ToolAnnotations(readOnlyHint=True),
        ),
        Tool(
            name="reverse_lookup",
            description=(
                "Reverse search: given ASINs, find whether Actorio knows profitable "
                "supplier matches. Source-store details are intentionally hidden. "
                "Pass export_format='csv' to get a downloadable file alongside "
                "the summary. " + _CREDITS_NOTE
            ),
            inputSchema={
                "type": "object",
                "required": ["asins"],
                "properties": {**_REVERSE_FILTER_PROPS, **export_format_prop, **_BUY_PROP, **_PAGINATION_PROPS},
            },
            annotations=ToolAnnotations(readOnlyHint=True),
        ),
        Tool(
            name="export_results",
            description=(
                "Buy the full result set that a previous search quoted, and get a "
                "download link for it. CHARGES the user the number of credits the "
                "quote named — only call this after the user has explicitly agreed "
                "to that price. The link is the complete list; give it to them. "
                + _CREDITS_NOTE
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "quote_id": {
                        "type": "string",
                        "description": "The quote_id from the search you are buying the results of",
                    },
                },
                "required": ["quote_id"],
            },
            # readOnlyHint=False alone is not enough: per the MCP spec
            # destructiveHint and openWorldHint both DEFAULT TO TRUE once a tool
            # is not read-only, so leaving them unset declared this as a
            # destructive, open-world operation. ChatGPT showed it as
            # "PUBLIC WRITE / OPEN WORLD / DESTRUCTIVE" and would not let the
            # model call it. It destroys nothing (it renders a file and charges
            # credits) and touches only Actorio, so both are false. It is NOT
            # idempotent: redeeming the same quote twice charges twice.
            annotations=ToolAnnotations(
                readOnlyHint=False,
                destructiveHint=False,
                idempotentHint=False,
                openWorldHint=False,
            ),
        ),
        Tool(
            name="get_usage",
            description="Get the user's CLI credit balance, monthly allowance and period reset date.",
            inputSchema={"type": "object", "properties": {}},
            annotations=ToolAnnotations(readOnlyHint=True),
        ),
    ]


# Module-level stdio variant, kept for imports/tests; `list_tools` builds
# the transport-correct list at request time.
TOOLS: list[Tool] = _build_tools(free_search=False)

_KIND_BY_TOOL = {
    "search_products": "products",
    "search_favorites": "favorites",
    "search_amazon": "amazon",
    "reverse_lookup": "reverse",
}


# MCP schema param name → API query param name. The tool schema exposes the
# filters as what they do ("exclude multipacks"), while the API speaks the
# webapp filterset's names. The old un-prefixed names still work in
# arguments for backward compatibility; the prefixed ones win.
_FLAG_ALIASES = {
    "exclude_multipack": "multipack",
    "exclude_variations": "variations",
    "exclude_hazmat": "hazmat",
    "exclude_suppressed_buybox": "suppressed_buybox",
}


def _to_query_params(args: dict) -> dict:
    """Map tool arguments to webapp query params (same rules as CLI flags)."""
    args = dict(args or {})
    if "query" in args:
        args["keywords"] = args.pop("query")
    if "asins" in args:
        args["asin_list"] = args.pop("asins")
    for new_key, api_key in _FLAG_ALIASES.items():
        if new_key in args:
            args[api_key] = args.pop(new_key)
    return build_params(**args)


def _error_text(e: ApiError) -> str:
    if e.code == "out_of_credits":
        return (
            f"Out of credits: {e.message}. The user can run `actorio buy-credits` "
            "or visit their Actorio billing page to top up."
        )
    if e.code == "upgrade_required":
        return f"Upgrade required: {e.message}. This feature needs a higher Actorio plan."
    return f"Error [{e.code}]: {e.message}"


async def _redeem_quote(client, quote_id: str) -> list:
    """Charge a quote and hand back the file. Reached two ways — the
    buy_quote_id parameter on a search tool, and the export_results tool —
    because not every host exposes both."""
    try:
        data = client.redeem_quote(quote_id)
    except ApiError as e:
        return [TextContent(type="text", text=_error_text(e))]
    out = {}
    if client.last_credits:
        out["_meta"] = {"credits": client.last_credits}
    url = data["download_url"]
    if DJANGO_BASE_URL and PUBLIC_BASE_URL and DJANGO_BASE_URL != PUBLIC_BASE_URL:
        url = url.replace(DJANGO_BASE_URL, PUBLIC_BASE_URL, 1)
    out["_hint"] = (
        f"Charged {data.get('credits_charged')} credits. Give the user this "
        f"link — it is the complete set of {data.get('rows')} rows and expires "
        f"in {data.get('expires_in')} seconds."
    )
    out["download_url"] = url
    out["rows"] = data.get("rows")
    out["filename"] = data.get("filename")
    out["bytes"] = data.get("bytes")
    # Also hand the link back as a first-class resource_link, not just a
    # URL inside a JSON string. A model asked to reproduce a URL in prose
    # will sometimes "correct" it to whatever domain looks canonical —
    # observed in the wild, an api-dev host rewritten to the production
    # one. A resource_link is structured data the host renders itself, so
    # the model never retypes it.
    return [
        TextContent(type="text", text=json.dumps(out, default=str)),
        ResourceLink(
            type="resource_link",
            uri=AnyUrl(url),
            name=data.get("filename") or "export",
            title=f"{data.get('rows')} products ({data.get('filename')})",
            description=(
                "Complete result set. Give this link to the user exactly as "
                "provided — do not retype or shorten the URL."
            ),
            mimeType="text/csv" if str(data.get("filename", "")).endswith(".csv")
            else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            size=data.get("bytes"),
        ),
    ]



async def _tool_handler(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    if PUBLIC_BASE_URL:
        # HTTP transport: the caller authenticated via OAuth (see
        # oauth_provider.py); use *their* token, not a shared local one.
        from mcp.server.auth.middleware.auth_context import get_access_token

        access_token = get_access_token()
        if access_token is None:
            return [TextContent(type="text", text="Error: not authenticated.")]
        client = Client(base_url=DJANGO_BASE_URL, token=access_token.token)
    else:
        # stdio transport: unchanged — each user's own `actorio login`.
        cfg = load_config()
        if cfg is None:
            return [TextContent(type="text", text="Error: not logged in. Run `actorio login` in a terminal first.")]
        client = Client(base_url=cfg.base_url, token=cfg.token)

    if name == "export_results":
        quote_id = (arguments or {}).get("quote_id")
        if not quote_id:
            return [TextContent(type="text", text="Error: quote_id is required. Run a search first to get one.")]
        return await _redeem_quote(client, str(quote_id))

    if name == "get_usage":
        try:
            data = client.usage()
        except ApiError as e:
            return [TextContent(type="text", text=_error_text(e))]
        return [TextContent(type="text", text=json.dumps(data, default=str))]

    # Search tools with optional export_format
    kind = _KIND_BY_TOOL.get(name)
    if kind is None:
        return [TextContent(type="text", text=f"Unknown tool: {name}")]

    args = dict(arguments or {})

    # Buying the rows is a parameter on the search tool, not a separate tool.
    # It was a separate tool briefly; ChatGPT never exposed it to the model,
    # which then invented plausible download URLs rather than admitting it
    # could not call it. A parameter on a tool the client already has cannot
    # go missing, and needs no connector refresh to appear.
    buy_quote_id = args.pop("buy_quote_id", None)
    if buy_quote_id:
        return await _redeem_quote(client, str(buy_quote_id))

    # Pull out pagination + export_format before query-param conversion
    raw_limit = args.pop("limit", None)
    limit = int(raw_limit) if raw_limit is not None else None
    offset = int(args.pop("offset", 0))
    export_format = args.pop("export_format", None)
    params = _to_query_params(args)

    # Default path over HTTP transport: a free search that describes the
    # whole match set and quotes what the rows would cost. Nothing is
    # charged and no file is rendered until the user says yes — searching
    # tells you how many and how much, buying gets you the data.
    if PUBLIC_BASE_URL and not offset:
        try:
            data = client.mcp_search(
                kind, params, export_format=(export_format or "csv")
            )
        except ApiError as e:
            return [TextContent(type="text", text=_error_text(e))]
        out = {}
        if client.last_credits:
            out["_meta"] = {"credits": client.last_credits}
        summary = data.get("summary") or {}
        quote = data.get("quote")
        total = summary.get("total") or 0
        if quote:
            out["_hint"] = (
                f"{total} products matched. This search was FREE. Tell the user "
                f"the summary figures, then ask whether they want the full list "
                f"of {quote['rows']} rows for {quote['credits']} credits. If they "
                f"agree, give them this link to click in their browser: "
                f"{quote.get('purchase_url', '')} "
                f"Do NOT call a tool to buy — a human clicks a button on that "
                f"page to spend credits. Never compose a download URL yourself; "
                f"the page gives them the real one. `teaser` is anonymised sample "
                f"figures, not products you can name."
            )
        else:
            out["_hint"] = (
                f"No products matched, so there is nothing to buy. This search "
                f"was free. Suggest loosening the filters."
            )
        out["free"] = True
        out["summary"] = summary
        if quote:
            out["quote"] = quote
        out["teaser"] = data.get("teaser", [])
        return [TextContent(type="text", text=json.dumps(out, default=str))]

    # stdio transport with export_format: unchanged behaviour for local
    # callers (Claude Code, Codex), which hold their own token and get the
    # file directly rather than going through the quote flow. The free
    # search + quote shape above is specific to remote hosts, where the
    # person paying is on the other end of a conversation and has to be
    # asked before their credits are spent.
    if export_format:
        try:
            data = client.export_link(kind, params, export_format=export_format)
        except ApiError as e:
            return [TextContent(type="text", text=_error_text(e))]
        download_url = data["download_url"]
        if DJANGO_BASE_URL and PUBLIC_BASE_URL and DJANGO_BASE_URL != PUBLIC_BASE_URL:
            download_url = download_url.replace(DJANGO_BASE_URL, PUBLIC_BASE_URL, 1)
        result = {}
        if client.last_credits:
            result["_meta"] = {"credits": client.last_credits}
        result["_export"] = {
            "download_url": download_url,
            "filename": data["filename"],
            "bytes": data["bytes"],
        }
        return [TextContent(type="text", text=json.dumps(result, default=str))]

    # Search-only path (no export_format) — 1 credit
    try:
        data = client.search(kind, params, limit=limit, offset=offset)
    except ApiError as e:
        return [TextContent(type="text", text=_error_text(e))]

    data = dict(data)
    pagination = data.get("pagination") or {}
    total = pagination.get("total") or 0
    shown = len(data.get("results") or [])

    # Order matters here. A full-fidelity product row is ~5KB (186 fields),
    # so a 10-result page is ~50KB / ~12k tokens, and MCP hosts truncate
    # large tool results — ChatGPT demonstrably does. json.dumps emits keys
    # in insertion order, so whatever goes last is what the model never
    # sees. Credits and the export hint are the two things it must not
    # miss, so they lead; the bulky `results` array trails.
    out = {}
    if client.last_credits:
        out["_meta"] = {"credits": client.last_credits}
    if total > shown:
        # Stated in the response body rather than left to the tool schema:
        # a model that just read 12k tokens of product rows reliably acts
        # on an instruction sitting in front of them, and much less
        # reliably on one parameter among 38 in the input schema. Without
        # this, models conclude there is no export and say so to the user.
        out["_hint"] = (
            f"Showing {shown} of {total} matches. To give the user ALL {total} "
            f"as a spreadsheet, call {name} again with the same filters plus "
            f"export_format='csv' (or 'xlsx'). That returns a download link — "
            f"there is no separate export tool, and paging with offset is not "
            f"the way to get the full set."
        )
    out.update(data)
    return [TextContent(type="text", text=json.dumps(out, default=str))]


def make_server() -> Server:
    server = Server(
        "actorio",
        version="0.1.0",
        website_url="https://actorio.com",
        icons=[
            Icon(
                src="https://static.actorio.com/favicon.ico",
                mimeType="image/vnd.microsoft.icon",
                sizes=["16x16", "32x32"],
            )
        ],
    )

    @server.list_tools()
    async def _list() -> list[Tool]:
        # Tool descriptions are transport-dependent: the free aggregate+quote
        # flow only exists over HTTP (PUBLIC_BASE_URL set); stdio searches
        # cost 1 credit and return full rows. Agents plan credit spend from
        # these descriptions, so they must match the transport they run on.
        return _build_tools(free_search=PUBLIC_BASE_URL is not None)

    @server.call_tool()
    async def _call(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        return await _tool_handler(name, arguments)

    return server


def run() -> None:
    import asyncio
    from mcp.server.stdio import stdio_server

    async def _main():
        async with stdio_server() as (read, write):
            server = make_server()
            await server.run(read, write, server.create_initialization_options())

    asyncio.run(_main())


def _detect_ngrok_public_url() -> str | None:
    """Best-effort: if ngrok's local API is up (its default web console),
    grab the https tunnel URL so callers don't have to pass --public-url
    by hand every time the tunnel restarts with a new address."""
    import httpx

    try:
        resp = httpx.get("http://127.0.0.1:4040/api/tunnels", timeout=1.0)
        for tunnel in resp.json().get("tunnels", []):
            if tunnel.get("proto") == "https":
                return tunnel["public_url"]
    except Exception:
        return None
    return None


async def _handle_export_download(request):
    """Proxy download requests to Django's internal unauthenticated export
    endpoint.  ChatGPT / Claude.ai call the public URL (rewritten by
    _tool_handler when PUBLIC_BASE_URL != DJANGO_BASE_URL); this handler
    forwards to Django and streams the cached file back."""
    from starlette.responses import JSONResponse, Response

    token = request.path_params["token"]
    filename = request.path_params["filename"]
    client = Client(base_url=DJANGO_BASE_URL, token=None)
    try:
        content, content_type, _ = client.download_export(token, filename)
    except ApiError as e:
        return JSONResponse(
            {"error": {"code": e.code, "message": e.message}},
            status_code=e.status,
        )
    return Response(
        content,
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def build_http_app(
    host: str = "127.0.0.1",
    port: int = 8765,
    public_url: str | None = None,
    api_base_url: str | None = None,
):
    """Builds the Streamable HTTP ASGI app (OAuth + /mcp routes) without
    starting a server — split out from run_http() so tests can exercise
    routing/auth wiring directly (e.g. with Starlette's TestClient) instead
    of needing a real running process."""
    import os

    from starlette.applications import Starlette
    from starlette.middleware import Middleware
    from starlette.middleware.authentication import AuthenticationMiddleware
    from starlette.routing import Route
    from pydantic import AnyHttpUrl

    from mcp.server.auth.middleware.auth_context import AuthContextMiddleware
    from mcp.server.auth.middleware.bearer_auth import BearerAuthBackend, RequireAuthMiddleware
    from mcp.server.auth.routes import (
        build_resource_metadata_url,
        create_auth_routes,
        create_protected_resource_routes,
    )
    from mcp.server.auth.settings import ClientRegistrationOptions, RevocationOptions
    from mcp.server.streamable_http_manager import StreamableHTTPSessionManager

    from actorio_cli.oauth_provider import ActorioOAuthProvider, ActorioTokenVerifier

    global PUBLIC_BASE_URL, DJANGO_BASE_URL
    PUBLIC_BASE_URL = (public_url or _detect_ngrok_public_url() or f"http://{host}:{port}").rstrip("/")
    DJANGO_BASE_URL = (api_base_url or "http://127.0.0.1:9000").rstrip("/")

    internal_secret = os.environ.get("MCP_OAUTH_INTERNAL_SECRET", "")
    if not internal_secret:
        raise RuntimeError(
            "MCP_OAUTH_INTERNAL_SECRET must be set in the environment — it's the shared "
            "secret this service uses to call Django's internal OAuth endpoints."
        )

    oauth_provider = ActorioOAuthProvider(django_base_url=DJANGO_BASE_URL, internal_secret=internal_secret)
    token_verifier = ActorioTokenVerifier(django_base_url=DJANGO_BASE_URL)

    server = make_server()
    session_manager = StreamableHTTPSessionManager(app=server, stateless=True)

    async def handle_mcp(scope, receive, send):
        await session_manager.handle_request(scope, receive, send)

    resource_metadata_url = build_resource_metadata_url(AnyHttpUrl(f"{PUBLIC_BASE_URL}/mcp"))

    routes = [
        *create_auth_routes(
            oauth_provider,
            issuer_url=AnyHttpUrl(PUBLIC_BASE_URL),
            client_registration_options=ClientRegistrationOptions(enabled=True),
            revocation_options=RevocationOptions(enabled=True),
        ),
        *create_protected_resource_routes(
            resource_url=AnyHttpUrl(f"{PUBLIC_BASE_URL}/mcp"),
            authorization_servers=[AnyHttpUrl(PUBLIC_BASE_URL)],
        ),
        # Route (exact path), not Mount — avoids Mount's bare-path 307
        # redirect and matches the SDK's own reference wiring in
        # mcp/server/fastmcp/server.py's streamable_http_app().
        Route("/mcp", endpoint=RequireAuthMiddleware(handle_mcp, required_scopes=[],
                                                      resource_metadata_url=resource_metadata_url)),
        # Proxy export downloads (unauthenticated — the URL token IS the auth).
        # ChatGPT / Claude.ai fetch this after the export_link handler rewrites
        # the download_url from DJANGO_BASE_URL to PUBLIC_BASE_URL.
        Route("/cli/v1/exports/{token}/{filename}", endpoint=_handle_export_download),
    ]

    return Starlette(
        routes=routes,
        middleware=[
            Middleware(AuthenticationMiddleware, backend=BearerAuthBackend(token_verifier)),
            Middleware(AuthContextMiddleware),
        ],
        lifespan=lambda app: session_manager.run(),
    )


def run_http(
    host: str = "127.0.0.1",
    port: int = 8765,
    public_url: str | None = None,
    api_base_url: str | None = None,
) -> None:
    """Serve over Streamable HTTP, for remote clients (e.g. ChatGPT/Claude.ai
    custom connectors) that can't launch a local stdio subprocess like
    Claude Code or Codex do. Each caller authenticates via OAuth (see
    oauth_provider.py) and gets their own Actorio account/quota — this
    process holds no per-user config file and no database of its own;
    everything about identity and billing lives in the Django API at
    api_base_url, reached only over HTTP."""
    import uvicorn

    app = build_http_app(host=host, port=port, public_url=public_url, api_base_url=api_base_url)
    print(f"MCP public base URL (OAuth issuer + export links): {PUBLIC_BASE_URL}")
    print(f"Actorio API base URL: {DJANGO_BASE_URL}")
    uvicorn.run(app, host=host, port=port)
