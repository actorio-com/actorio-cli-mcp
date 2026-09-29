"""Terminal rendering for search results.

The table mirrors the webapp product table (ecommercer/tables.py
ProductTable): one row per product, with per-marketplace values stacked
inside each cell in DE/ES/FR/GB/IT order, the same VAT-aware supplier
price block, and the monthly sales/profit totals.
"""
import sys

from rich.console import Console
from rich.table import Table

# When stdout is not a terminal (pipes, agents, tests) there is no real
# width limit — use a generous one so columns aren't truncated.
_console = Console() if sys.stdout.isatty() else Console(width=200)

# Marketplaces with data in the product index (webapp DB_AMZ_COUNTRIES).
# The web UI also lists BE/NL/PL/SE/IE/TR but those only fill in via a
# live Amazon-API refresh, which the bridge does not perform.
MARKETPLACES = ("DE", "ES", "FR", "GB", "IT")
_MP_CURRENCY = {"DE": "€", "ES": "€", "FR": "€", "GB": "£", "IT": "€"}

_CURRENCY_SYMBOLS = {
    "EUR": "€", "GBP": "£", "PLN": "zł", "SEK": "kr", "CZK": "Kč",
    "HUF": "Ft", "TRY": "₺", "DKK": "kr.", "RON": "lei", "USD": "$",
}


def _get(row: dict, key: str):
    value = row.get(key)
    return None if value in (None, "") else value


def _to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _money(value, symbol: str) -> str:
    number = _to_float(value)
    return "N/A" if number is None else f"{number:,.2f} {symbol}"


def _identifiers_cell(row: dict) -> str:
    lines = []
    if _get(row, "asin"):
        lines.append(f"ASIN {row['asin']}")
    if _get(row, "upc"):
        lines.append(f"EAN {row['upc']}")
    if _get(row, "reference"):
        lines.append(f"SKU {row['reference']}")
    return "\n".join(lines) or "—"


def _amazon_title(row: dict):
    for cc in MARKETPLACES:
        title = _get(row, f"amz_title_{cc.lower()}")
        if title:
            return title
    return _get(row, "title")


def _product_cell(row: dict) -> str:
    lines = []
    title = _amazon_title(row)
    if title:
        lines.append(str(title))
    supplier_title = _get(row, "title")
    if supplier_title and supplier_title != title:
        lines.append(f"[dim]{supplier_title}[/dim]")
    supplier_bits = [
        str(v) for v in (_get(row, "store"), _get(row, "country"), _get(row, "type")) if v
    ]
    if supplier_bits:
        lines.append("[cyan]" + " · ".join(supplier_bits) + "[/cyan]")
    extra_bits = [
        str(v) for v in (_get(row, "brand"), _get(row, "size_tier")) if v
    ]
    if extra_bits:
        lines.append("[dim]" + " · ".join(extra_bits) + "[/dim]")
    return "\n".join(lines) or "—"


def _supplier_price_cell(row: dict) -> str:
    """Net/gross supplier price, mirroring ProductTable.render_store_price."""
    currency = str(_get(row, "currency") or "EUR")
    symbol = _CURRENCY_SYMBOLS.get(currency, currency)
    vat_rate = _to_float(_get(row, "vat")) or 0.21
    price = _to_float(_get(row, "price"))
    vat_included = bool(row.get("vat_included"))

    net = _to_float(_get(row, "net_price"))
    if net is None and price is not None:
        net = price / (1 + vat_rate) if vat_included else price
    gross = _to_float(_get(row, "gross_price"))
    if gross is None and price is not None:
        gross = price if vat_included else price * (1 + vat_rate)

    lines = []
    if net is not None:
        line = f"{net:,.2f} {symbol} VAT excl."
        net_eur = _to_float(_get(row, "net_price_eur"))
        if net_eur is not None and symbol != "€":
            line += f" ({net_eur:,.2f} €)"
        lines.append(line)
    if gross is not None:
        line = f"{gross:,.2f} {symbol} VAT {vat_rate * 100:.0f}% incl."
        gross_eur = _to_float(_get(row, "gross_price_eur"))
        if gross_eur is not None and symbol != "€":
            line += f" ({gross_eur:,.2f} €)"
        lines.append(line)
    return "\n".join(lines) or "N/A"


def _amz_price_line(row: dict, cc: str, avg30: bool) -> str:
    """Current (or 30-day average) Amazon price for one marketplace.

    Same outlier guard as the webapp: a value more than 10x above the
    row's minimum across marketplaces is treated as bad data.
    """
    lc = cc.lower()
    value = None
    if avg30:
        value = _to_float(_get(row, f"avg_30_new_{lc}"))
        floor = _to_float(_get(row, "min_amz_price_30d"))
        if value and floor and value > floor * 10:
            value = None
    if value is None:
        value = _to_float(_get(row, f"competitive_price_{lc}"))
        floor = _to_float(_get(row, "min_competitive_price"))
        if value and floor and value > floor * 10:
            value = None
    return _money(value, _MP_CURRENCY[cc])


def _sellers_line(row: dict, cc: str) -> str:
    lc = cc.lower()
    sellers = _get(row, f"sellers_{lc}")
    if sellers is None:
        return "N/A"
    sellers = int(sellers)
    if sellers == 0:
        return "0"
    fba = int(_to_float(_get(row, f"new_amz_sellers_{lc}")) or 0)
    return f"{sellers} ({fba} FBA)"


def _profit_line(row: dict, cc: str, avg30: bool) -> str:
    key = f"profit_30d_{cc.lower()}" if avg30 else f"profit_{cc.lower()}"
    value = _to_float(_get(row, key))
    if not value:  # webapp treats 0 as no data
        return "N/A"
    color = "green" if value > 0 else "red"
    return f"[{color}]{value:,.2f} €[/{color}]"


def _roi_line(row: dict, cc: str, avg30: bool) -> str:
    key = f"roi_30d_{cc.lower()}" if avg30 else f"roi_{cc.lower()}"
    value = _to_float(_get(row, key))
    if value is None:
        return "N/A"
    color = "green" if value > 0 else "red"
    return f"[{color}]{value:,.0f} %[/{color}]"


def _sales_month_line(row: dict, cc: str) -> str:
    value = _get(row, f"sales_30_days_{cc.lower()}")
    return "N/A" if value is None else str(int(value))


def _profit_month_line(row: dict, cc: str, avg30: bool) -> str:
    key = f"profit_month_30d_{cc.lower()}" if avg30 else f"profit_month_{cc.lower()}"
    value = _to_float(_get(row, key))
    return "N/A" if value is None else f"{value:,.2f} €"


def _with_total(lines: list[str], total: str | None) -> str:
    if total is not None:
        lines = lines + ["────", f"Σ {total}"]
    return "\n".join(lines)


def print_products_table(results: list[dict], pagination: dict, params: dict | None = None) -> None:
    avg30 = "avg30" in str((params or {}).get("price_reference") or "")

    table = Table(show_lines=True)
    table.add_column("Identifiers", no_wrap=True)
    table.add_column("Product", max_width=38)
    table.add_column("Supplier Price")
    table.add_column("MP")
    table.add_column("AMZ Price", justify="right")
    table.add_column("Sellers", justify="right")
    table.add_column("Unit Profit", justify="right")
    table.add_column("Unit ROI", justify="right")
    table.add_column("Sales/mo", justify="right")
    table.add_column("Profit/mo", justify="right")

    for row in results:
        total_sales = _get(row, "total_sales_30_days")
        total_sales = None if total_sales is None else str(int(total_sales))
        total_profit_key = "total_profit_month_30d" if avg30 else "total_profit_month"
        total_profit = _to_float(_get(row, total_profit_key))
        total_profit = None if total_profit is None else f"{total_profit:,.2f} €"

        table.add_row(
            _identifiers_cell(row),
            _product_cell(row),
            _supplier_price_cell(row),
            "\n".join(MARKETPLACES),
            "\n".join(_amz_price_line(row, cc, avg30) for cc in MARKETPLACES),
            "\n".join(_sellers_line(row, cc) for cc in MARKETPLACES),
            "\n".join(_profit_line(row, cc, avg30) for cc in MARKETPLACES),
            "\n".join(_roi_line(row, cc, avg30) for cc in MARKETPLACES),
            _with_total([_sales_month_line(row, cc) for cc in MARKETPLACES], total_sales),
            _with_total([_profit_month_line(row, cc, avg30) for cc in MARKETPLACES], total_profit),
        )

    _console.print(table)
    total = pagination.get("total", len(results))
    shown = len(results)
    if "offset" in pagination:
        start = pagination["offset"]
    else:  # older servers only report page/per_page
        page = pagination.get("page", 1)
        per_page = pagination.get("per_page", shown or 1)
        start = (page - 1) * per_page
    suffix = " — use --offset/--limit to paginate" if pagination.get("has_more") else ""
    _console.print(f"[dim]showing {start + 1}-{start + shown} of {total}{suffix}[/dim]")


def print_credits_footer(credits: dict) -> None:
    cost = credits.get("cost", "?")
    remaining = credits.get("remaining", "?")
    line = f"[dim]Cost: {cost} credit{'s' if str(cost) != '1' else ''}. Remaining: {remaining}.[/dim]"
    if credits.get("warning"):
        line += f" [yellow]({credits['warning']})[/yellow]"
    _console.print(line)


def print_usage_table(data: dict) -> None:
    table = Table(show_header=False, show_lines=False)
    table.add_column("Field")
    table.add_column("Value", justify="right")
    monthly_inc = data.get("monthly_included", 0)
    monthly_used = data.get("monthly_used", 0)
    pct = (monthly_used / monthly_inc * 100) if monthly_inc else 0
    table.add_row("Monthly included", str(monthly_inc))
    table.add_row("Monthly used", f"{monthly_used} ({pct:.0f}%)")
    table.add_row("Monthly remaining", str(data.get("monthly_remaining", 0)))
    table.add_row("Pack balance", str(data.get("pack_balance", 0)))
    table.add_row("Effective remaining", str(data.get("effective_remaining", 0)))
    table.add_row("Period start", data.get("period_start", "")[:10])
    table.add_row("Period end", data.get("period_end", "")[:10])
    _console.print(table)
