import pytest
import httpx
import respx
from actorio_cli.client import Client, ApiError

BASE = "https://actorio.example"


def make_client(token="act_t"):
    return Client(base_url=BASE, token=token)


@respx.mock
def test_search_returns_parsed_json():
    respx.get(f"{BASE}/cli/v1/products/search").mock(
        return_value=httpx.Response(200, json={
            "results": [{"id": 1}],
            "pagination": {"page": 1, "per_page": 20, "total": 1, "has_more": False},
        })
    )
    data = make_client().search("products", {"keywords": "lego", "country": "DE"}, page=1)
    assert data["results"] == [{"id": 1}]


@respx.mock
def test_401_raises_api_error():
    respx.get(f"{BASE}/cli/v1/products/search").mock(
        return_value=httpx.Response(401, json={"error": {"code": "unauthorized", "message": "bad"}})
    )
    with pytest.raises(ApiError) as exc:
        make_client().search("products", {}, page=1)
    assert exc.value.code == "unauthorized"
    assert exc.value.status == 401


@respx.mock
def test_device_start_and_poll():
    respx.post(f"{BASE}/cli/v1/auth/device/start").mock(
        return_value=httpx.Response(200, json={
            "device_code": "dc", "user_code": "UC", "verification_url": f"{BASE}/x",
            "expires_in": 600, "interval": 2,
        })
    )
    respx.post(f"{BASE}/cli/v1/auth/device/poll").mock(
        return_value=httpx.Response(200, json={"token": "act_new"})
    )
    c = Client(base_url=BASE, token=None)
    start = c.device_start(label="laptop")
    assert start["user_code"] == "UC"
    assert c.device_poll("dc") == {"token": "act_new"}


@respx.mock
def test_search_passes_bearer_header():
    route = respx.get(f"{BASE}/cli/v1/favorites/search").mock(
        return_value=httpx.Response(200, json={"results": [], "pagination": {"page": 1, "per_page": 20, "total": 0, "has_more": False}})
    )
    make_client("act_xyz").search("favorites", {}, page=1)
    assert route.called
    assert route.calls[0].request.headers["authorization"] == "Bearer act_xyz"


# ---------------------------------------------------------------------------
# Credit header capture — _capture_credits / last_credits.
# ---------------------------------------------------------------------------


@respx.mock
def test_capture_credits_from_headers():
    """X-Credits-* response headers populate last_credits on every call."""
    respx.get(f"{BASE}/cli/v1/usage").mock(
        return_value=httpx.Response(
            200,
            json={"effective_remaining": 500},
            headers={
                "X-Credits-Cost": "0",
                "X-Credits-Remaining": "500",
                "X-Credits-Reset": "2026-06-01",
                "X-Credits-Warning": "Low balance",
            },
        )
    )
    c = make_client()
    c.usage()
    assert c.last_credits == {
        "cost": 0,
        "remaining": 500,
        "reset": "2026-06-01",
        "warning": "Low balance",
    }


@respx.mock
def test_no_credits_headers_leaves_last_credits_unchanged():
    """When the server doesn't send X-Credits headers, last_credits stays None."""
    respx.get(f"{BASE}/cli/v1/usage").mock(
        return_value=httpx.Response(200, json={"effective_remaining": 500})
    )
    c = make_client()
    assert c.last_credits is None
    c.usage()
    assert c.last_credits is None


@respx.mock
def test_partial_credits_headers():
    """Only X-Credits-Cost is required; remaining/reset/warning are optional."""
    respx.get(f"{BASE}/cli/v1/products/search").mock(
        return_value=httpx.Response(
            200,
            json={"results": [], "pagination": {}},
            headers={"X-Credits-Cost": "1"},
        )
    )
    c = make_client()
    c.search("products", {"keywords": "test"}, page=1)
    assert c.last_credits["cost"] == 1
    assert c.last_credits["remaining"] == 0  # default from int()
    assert c.last_credits["reset"] == ""
    assert c.last_credits["warning"] is None


# ---------------------------------------------------------------------------
# export — download path with error handling.
# ---------------------------------------------------------------------------


@respx.mock
def test_export_csv_returns_content_and_filename():
    respx.get(f"{BASE}/cli/v1/products/export").mock(
        return_value=httpx.Response(
            200,
            content=b"col1,col2\nval1,val2\n",
            headers={
                "Content-Disposition": 'attachment; filename="actorio-products.csv"',
            },
        )
    )
    content, filename = make_client().export("products", {"keywords": "test"})
    assert content == b"col1,col2\nval1,val2\n"
    assert filename == "actorio-products.csv"


@respx.mock
def test_export_parses_filename_from_header():
    respx.get(f"{BASE}/cli/v1/amazon/export").mock(
        return_value=httpx.Response(
            200,
            content=b"x",
            headers={"Content-Disposition": 'attachment; filename="my-flips.csv"'},
        )
    )
    _, filename = make_client().export("amazon", {})
    assert filename == "my-flips.csv"


@respx.mock
def test_export_fallback_filename():
    """No Content-Disposition header → falls back to actorio-{kind}.{format}."""
    respx.get(f"{BASE}/cli/v1/products/export").mock(
        return_value=httpx.Response(200, content=b"x")
    )
    _, filename = make_client().export("products", {}, export_format="csv")
    assert filename == "actorio-products.csv"


@respx.mock
def test_export_xlsx_fallback_filename():
    respx.get(f"{BASE}/cli/v1/products/export").mock(
        return_value=httpx.Response(200, content=b"x")
    )
    _, filename = make_client().export("products", {}, export_format="xlsx")
    assert filename == "actorio-products.xlsx"


@respx.mock
def test_export_api_error():
    """export surfaces API errors as ApiError (not swallowed)."""
    respx.get(f"{BASE}/cli/v1/products/export").mock(
        return_value=httpx.Response(
            402, json={"error": {"code": "out_of_credits", "message": "Export costs 5"}}
        )
    )
    with pytest.raises(ApiError) as exc:
        make_client().export("products", {})
    assert exc.value.code == "out_of_credits"
    assert exc.value.status == 402


@respx.mock
def test_export_non_json_error_body():
    """If the error response body isn't JSON, export still raises ApiError."""
    respx.get(f"{BASE}/cli/v1/products/export").mock(
        return_value=httpx.Response(502, text="Bad Gateway")
    )
    with pytest.raises(ApiError) as exc:
        make_client().export("products", {})
    assert exc.value.code == "unknown"
    assert "Bad Gateway" in exc.value.message


# ---------------------------------------------------------------------------
# export_link — remote download URL path.
# ---------------------------------------------------------------------------


@respx.mock
def test_export_link():
    respx.get(f"{BASE}/cli/v1/products/export-link").mock(
        return_value=httpx.Response(
            200,
            json={
                "filename": "actorio-products.csv",
                "content_type": "text/csv",
                "bytes": 1234,
                "download_url": f"{BASE}/cli/v1/exports/abc/actorio-products.csv",
            },
        )
    )
    data = make_client().export_link("products", {"keywords": "test"})
    assert data["filename"] == "actorio-products.csv"
    assert data["bytes"] == 1234
    assert data["download_url"] == f"{BASE}/cli/v1/exports/abc/actorio-products.csv"


@respx.mock
def test_export_link_credits():
    """export_link also captures credit headers (same as any _handle call)."""
    respx.get(f"{BASE}/cli/v1/products/export-link").mock(
        return_value=httpx.Response(
            200,
            json={"filename": "x.csv", "content_type": "text/csv", "bytes": 0, "download_url": "https://x"},
            headers={"X-Credits-Cost": "5", "X-Credits-Remaining": "995"},
        )
    )
    c = make_client()
    c.export_link("products", {})
    assert c.last_credits["cost"] == 5


# ---------------------------------------------------------------------------
# download_export — unauthenticated cached-file fetch.
# ---------------------------------------------------------------------------


@respx.mock
def test_download_export():
    """download_export fetches the cached file from Django's unauthenticated
    endpoint and returns (content, content_type, filename)."""
    csv_bytes = b"id,name\n1,widget\n"
    respx.get(f"{BASE}/cli/v1/exports/tok123/actorio-products.csv").mock(
        return_value=httpx.Response(
            200,
            content=csv_bytes,
            headers={
                "Content-Type": "text/csv; charset=utf-8",
                "Content-Disposition": 'attachment; filename="actorio-products.csv"',
            },
        )
    )
    content, content_type, filename = make_client().download_export(
        "tok123", "actorio-products.csv"
    )
    assert content == csv_bytes
    assert content_type == "text/csv; charset=utf-8"
    assert filename == "actorio-products.csv"


@respx.mock
def test_download_export_not_found():
    """When the cache entry expired or the token is invalid, Django returns
    404 — download_export surfaces it as an ApiError."""
    respx.get(f"{BASE}/cli/v1/exports/tok123/x.csv").mock(
        return_value=httpx.Response(
            404,
            json={"error": {"code": "export_not_found", "message": "Export not found or expired"}},
        )
    )
    with pytest.raises(ApiError) as exc:
        make_client().download_export("tok123", "x.csv")
    assert exc.value.code == "export_not_found"
    assert exc.value.status == 404


@respx.mock
def test_download_export_without_token_still_omits_auth():
    """download_export is unauthenticated (the URL token IS the auth) —
    creating a Client with token=None still works."""
    csv_bytes = b"a,b\n1,2\n"
    respx.get(f"{BASE}/cli/v1/exports/tok/a.csv").mock(
        return_value=httpx.Response(200, content=csv_bytes)
    )
    # token=None → no Authorization header
    c = Client(base_url=BASE, token=None)
    content, _, _ = c.download_export("tok", "a.csv")
    assert content == csv_bytes


# ---------------------------------------------------------------------------
# purchase_info.
# ---------------------------------------------------------------------------


@respx.mock
def test_purchase_info():
    respx.get(f"{BASE}/cli/v1/credits/purchase-info").mock(
        return_value=httpx.Response(
            200, json={"purchase_url": "https://app.actorio.com/subscriptions/cli_credits/"}
        )
    )
    data = make_client().purchase_info()
    assert "cli_credits" in data["purchase_url"]


# ---------------------------------------------------------------------------
# usage endpoint.
# ---------------------------------------------------------------------------


@respx.mock
def test_usage():
    respx.get(f"{BASE}/cli/v1/usage").mock(
        return_value=httpx.Response(
            200,
            json={
                "monthly_included": 2000,
                "monthly_used": 500,
                "monthly_remaining": 1500,
                "pack_balance": 100,
                "effective_remaining": 1600,
            },
        )
    )
    data = make_client().usage()
    assert data["effective_remaining"] == 1600


@respx.mock
def test_usage_api_error():
    respx.get(f"{BASE}/cli/v1/usage").mock(
        return_value=httpx.Response(401, json={"error": {"code": "unauthorized", "message": "bad token"}})
    )
    with pytest.raises(ApiError) as exc:
        make_client().usage()
    assert exc.value.code == "unauthorized"


# ---------------------------------------------------------------------------
# ApiError string representation.
# ---------------------------------------------------------------------------


def test_api_error_str():
    e = ApiError(code="test_code", message="Something went wrong", status=500)
    assert str(e) == "[test_code] Something went wrong"


# ---------------------------------------------------------------------------
# search — limit/offset vs page pagination.
# ---------------------------------------------------------------------------


@respx.mock
def test_search_limit_offset():
    route = respx.get(f"{BASE}/cli/v1/products/search").mock(
        return_value=httpx.Response(200, json={"results": [], "pagination": {}})
    )
    make_client().search("products", {"keywords": "x"}, limit=50, offset=100)
    assert "limit=50" in str(route.calls[0].request.url)
    assert "offset=100" in str(route.calls[0].request.url)


@respx.mock
def test_search_page_pagination():
    route = respx.get(f"{BASE}/cli/v1/products/search").mock(
        return_value=httpx.Response(200, json={"results": [], "pagination": {}})
    )
    make_client().search("products", {"keywords": "x"}, page=3)
    assert "page=3" in str(route.calls[0].request.url)


@respx.mock
def test_client_no_token_omits_auth_header():
    """When token is None, no Authorization header is sent."""
    route = respx.post(f"{BASE}/cli/v1/auth/device/start").mock(
        return_value=httpx.Response(200, json={"device_code": "x"})
    )
    Client(base_url=BASE, token=None).device_start(label="test")
    assert "authorization" not in route.calls[0].request.headers
