from dataclasses import dataclass
import httpx


@dataclass
class ApiError(Exception):
    code: str
    message: str
    status: int

    def __str__(self) -> str:
        return f"[{self.code}] {self.message}"


class Client:
    def __init__(self, *, base_url: str, token: str | None, timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self._http = httpx.Client(timeout=timeout)
        # Populated by _handle on every response that has X-Credits-* headers
        self.last_credits: dict | None = None

    def _headers(self) -> dict:
        h = {"Accept": "application/json"}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    def _capture_credits(self, resp: httpx.Response) -> None:
        if "X-Credits-Cost" in resp.headers:
            self.last_credits = {
                "cost": int(resp.headers["X-Credits-Cost"]),
                "remaining": int(resp.headers.get("X-Credits-Remaining", 0)),
                "reset": resp.headers.get("X-Credits-Reset", ""),
                "warning": resp.headers.get("X-Credits-Warning"),
            }

    def _handle(self, resp: httpx.Response) -> dict:
        self._capture_credits(resp)
        if resp.status_code >= 400:
            try:
                err = resp.json().get("error", {})
                code = err.get("code", "unknown")
                msg = err.get("message", resp.text)
            except Exception:
                code = "unknown"
                msg = resp.text
            raise ApiError(code=code, message=msg, status=resp.status_code)
        return resp.json()

    def device_start(self, *, label: str) -> dict:
        resp = self._http.post(
            f"{self.base_url}/cli/v1/auth/device/start",
            json={"label": label},
        )
        return self._handle(resp)

    def device_poll(self, device_code: str) -> dict:
        resp = self._http.post(
            f"{self.base_url}/cli/v1/auth/device/poll",
            json={"device_code": device_code},
        )
        return self._handle(resp)

    def usage(self) -> dict:
        resp = self._http.get(
            f"{self.base_url}/cli/v1/usage",
            headers=self._headers(),
        )
        return self._handle(resp)

    def search(self, kind: str, params: dict, *, limit: int | None = None,
               offset: int | None = None, page: int | None = None) -> dict:
        q = dict(params)
        if limit is not None:
            q["limit"] = limit
        if offset is not None:
            q["offset"] = offset
        if page is not None:  # legacy page-based pagination still accepted
            q["page"] = page
        resp = self._http.get(
            f"{self.base_url}/cli/v1/{kind}/search",
            params=q,
            headers=self._headers(),
        )
        return self._handle(resp)

    def export(self, kind: str, params: dict, *, export_format: str = "csv",
               timeout: float = 180.0) -> tuple[bytes, str]:
        """Download a CSV/XLSX export. Returns (content, suggested_filename)."""
        q = dict(params)
        q["_export"] = export_format
        resp = self._http.get(
            f"{self.base_url}/cli/v1/{kind}/export",
            params=q,
            headers=self._headers(),
            timeout=timeout,
        )
        self._capture_credits(resp)
        if resp.status_code >= 400:
            try:
                err = resp.json().get("error", {})
                raise ApiError(
                    code=err.get("code", "unknown"),
                    message=err.get("message", resp.text),
                    status=resp.status_code,
                )
            except ApiError:
                raise
            except Exception:
                raise ApiError(code="unknown", message=resp.text, status=resp.status_code)

        filename = f"actorio-{kind}.{export_format}"
        disposition = resp.headers.get("Content-Disposition", "")
        if 'filename="' in disposition:
            filename = disposition.split('filename="', 1)[1].split('"', 1)[0]
        return resp.content, filename

    def export_link(self, kind: str, params: dict, *, export_format: str = "csv") -> dict:
        """Remote/HTTP-transport export: Django renders + caches the file
        and hands back a short-lived download_url instead of streaming
        bytes — used only when PUBLIC_BASE_URL is set (see mcp_server.py).
        Returns {filename, content_type, bytes, download_url}."""
        q = dict(params)
        q["_export"] = export_format
        resp = self._http.get(
            f"{self.base_url}/cli/v1/{kind}/export-link",
            params=q,
            headers=self._headers(),
        )
        return self._handle(resp)

    def mcp_search(self, kind: str, params: dict, *, export_format: str = "csv") -> dict:
        """Free, agent-shaped search: aggregates over the whole match set,
        an identifier-free teaser, and a quote for what the full list costs.

        Charges nothing — counting is not the thing of value, and the teaser
        carries no store/title/asin/upc/url, so it cannot be swept for a
        catalogue. Returns {summary, teaser, free, quote?}; `quote` is absent
        when nothing matched. Redeem it with redeem_quote()."""
        q = dict(params)
        q["_export"] = export_format
        resp = self._http.get(
            f"{self.base_url}/cli/v1/{kind}/mcp-search",
            params=q,
            headers=self._headers(),
        )
        return self._handle(resp)

    def redeem_quote(self, quote_id: str) -> dict:
        """Buy the full result set a search quoted. Charges exactly the
        credits the quote named and returns {download_url, rows, bytes,
        credits_charged, ...}."""
        resp = self._http.get(
            f"{self.base_url}/cli/v1/exports/redeem",
            params={"quote_id": quote_id},
            headers=self._headers(),
        )
        return self._handle(resp)

    def download_export(self, token: str, filename: str) -> tuple[bytes, str, str]:
        """Fetch a cached export from Django's unauthenticated download endpoint.
        Returns (content, content_type, filename)."""
        resp = self._http.get(
            f"{self.base_url}/cli/v1/exports/{token}/{filename}",
        )
        if resp.status_code >= 400:
            try:
                err = resp.json().get("error", {})
                raise ApiError(
                    code=err.get("code", "unknown"),
                    message=err.get("message", resp.text),
                    status=resp.status_code,
                )
            except ApiError:
                raise
            except Exception:
                raise ApiError(code="unknown", message=resp.text, status=resp.status_code)
        content_type = resp.headers.get("Content-Type", "application/octet-stream")
        disposition = resp.headers.get("Content-Disposition", "")
        if 'filename="' in disposition:
            filename = disposition.split('filename="', 1)[1].split('"', 1)[0]
        return resp.content, content_type, filename

    def purchase_info(self) -> dict:
        resp = self._http.get(
            f"{self.base_url}/cli/v1/credits/purchase-info",
            headers=self._headers(),
        )
        return self._handle(resp)
