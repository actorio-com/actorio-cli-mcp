"""Translate an Actorio webapp search URL into the equivalent CLI command.

The CLI flags map 1:1 to the webapp filterset query params (see
``actorio_cli/commands/_filters.py``), so the translation is mechanical:
query params become ``--kebab-case`` flags, repeated params repeat the flag,
boolean params become bare flags, and the keyword becomes the positional
argument. Unknown params are skipped with a warning on stderr.

Usage:
    actorio translate "https://app.actorio.com/products/search/?store=carrefour.es&roi_min=20"
    actorio translate "store=carrefour.es&roi_min=20"   # bare query string works too
"""
import shlex
from urllib.parse import parse_qs, urlparse

import typer

# Webapp filterset param names the CLI has flags for (products search).
_PRODUCT_PARAMS = (
    "country",
    "type",
    "store",
    "upc_list",
    "asin_list",
    "price_min",
    "price_max",
    "marketplace",
    "price_reference",
    "last_update",
    "missing_fba",
    "multipack",
    "variations",
    "hazmat",
    "suppressed_buybox",
    "size",
    "category",
    "similarity",
    "competitive_price_min",
    "competitive_price_max",
    "competitive_price_logic",
    "profit_min",
    "profit_max",
    "profit_logic",
    "roi_min",
    "roi_max",
    "roi_logic",
    "profit_month_min",
    "profit_month_max",
    "profit_month_logic",
    "sales_month_min",
    "sales_month_max",
    "sales_month_logic",
    "sort",
)

_MULTI_VALUE = {"store", "size", "category"}
_BOOL = {"missing_fba", "multipack", "variations", "hazmat", "suppressed_buybox", "actorio_only"}
_TRUE_VALUES = {"true", "1", "on", "yes"}
_KEYWORD_PARAMS = ("keywords", "q")
_IGNORED_PARAMS = {"page", "csrfmiddlewaretoken", "format"}  # pagination/session noise


def translate(text: str) -> tuple[str, list[str]]:
    """Return ``(command, warnings)`` for a webapp search URL or query string."""
    text = text.strip()
    if "://" in text:
        parsed = urlparse(text)
        path, query = parsed.path, parsed.query
    elif text.startswith("/"):  # path-style URL without scheme
        path, _, query = text.partition("?")
    else:  # bare query string
        path, query = "/products/search/", text.lstrip("?")

    path_lower = path.lower()
    if "favorites" in path_lower:
        kind = "favorites"
    elif "amazon" in path_lower:
        kind = "amazon"
    elif "reverse" in path_lower:
        kind = "reverse"
    elif "search" in path_lower:
        kind = "products"
    else:
        raise ValueError(f"Unrecognized search URL path: {path!r}")

    parts = ["actorio", kind, "search"]
    keyword = None
    warnings: list[str] = []
    for name, values in parse_qs(query, keep_blank_values=False).items():
        if name in _IGNORED_PARAMS:
            continue
        if name in _KEYWORD_PARAMS:
            keyword = values[0]
            continue
        if name not in _PRODUCT_PARAMS:
            warnings.append(f"skipped unknown param {name!r} (no CLI flag)")
            continue
        flag = "--" + name.replace("_", "-")
        if name in _BOOL:
            if values[0].lower() in _TRUE_VALUES:
                parts.append(flag)
            continue
        if name in _MULTI_VALUE:
            for value in values:
                parts.append(f"{flag} {shlex.quote(value)}")
        else:
            parts.append(f"{flag} {shlex.quote(values[0])}")

    if keyword:
        parts.insert(3, shlex.quote(keyword))
    return " ".join(parts), warnings


def translate_cmd(
    url: str = typer.Argument(
        ...,
        help="Actorio webapp search URL (or bare query string) to translate",
    ),
) -> None:
    """Print the actorio CLI command equivalent to a webapp search URL."""
    try:
        command, warnings = translate(url)
    except ValueError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    for warning in warnings:
        typer.echo(f"warning: {warning}", err=True)
    typer.echo(command)
