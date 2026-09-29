import typer
from actorio_cli.commands import products as p
from actorio_cli.commands._common import run_export, run_search

favorites_app = typer.Typer(help="Favorites search and export", no_args_is_help=True)


@favorites_app.command("search")
def search(
    query: str = p.QUERY,
    country: str = p.COUNTRY,
    type_: str = p.TYPE,
    store: list[str] = p.STORE,
    upc_list: str = p.UPC_LIST,
    asin_list: str = p.ASIN_LIST,
    price_min: float = p.PRICE_MIN,
    price_max: float = p.PRICE_MAX,
    marketplace: str = p.MARKETPLACE,
    price_reference: str = p.PRICE_REFERENCE,
    last_update: str = p.LAST_UPDATE,
    missing_fba: bool = p.MISSING_FBA,
    multipack: bool = p.MULTIPACK,
    variations: bool = p.VARIATIONS,
    hazmat: bool = p.HAZMAT,
    suppressed_buybox: bool = p.SUPPRESSED_BUYBOX,
    size: list[str] = p.SIZE,
    category: list[str] = p.CATEGORY,
    similarity: int = p.SIMILARITY,
    competitive_price_min: float = p.COMPETITIVE_PRICE_MIN,
    competitive_price_max: float = p.COMPETITIVE_PRICE_MAX,
    competitive_price_logic: str = p.COMPETITIVE_PRICE_LOGIC,
    profit_min: float = p.PROFIT_MIN,
    profit_max: float = p.PROFIT_MAX,
    profit_logic: str = p.PROFIT_LOGIC,
    roi_min: float = p.ROI_MIN,
    roi_max: float = p.ROI_MAX,
    roi_logic: str = p.ROI_LOGIC,
    profit_month_min: float = p.PROFIT_MONTH_MIN,
    profit_month_max: float = p.PROFIT_MONTH_MAX,
    profit_month_logic: str = p.PROFIT_MONTH_LOGIC,
    sales_month_min: float = p.SALES_MONTH_MIN,
    sales_month_max: float = p.SALES_MONTH_MAX,
    sales_month_logic: str = p.SALES_MONTH_LOGIC,
    sort: str = p.SORT,
    limit: int = typer.Option(None, help="Results per request (server default: 20, max 100)"),
    offset: int = typer.Option(0, help="Skip this many results"),
    as_json: bool = typer.Option(
        False,
        "--json",
        help="Output raw JSON ({results, pagination}) instead of a table; "
             "page with --offset/--limit while pagination.has_more is true",
    ),
):
    """Search your saved favorites.

    For CSV/XLSX files use `actorio favorites export` — costs more credits
    than a search.
    """
    params = p._collect(
        query, country, type_, store, upc_list, asin_list, price_min, price_max,
        marketplace, price_reference, last_update, missing_fba, multipack,
        variations, hazmat, suppressed_buybox, size, category, similarity,
        competitive_price_min, competitive_price_max, competitive_price_logic,
        profit_min, profit_max, profit_logic, roi_min, roi_max, roi_logic,
        profit_month_min, profit_month_max, profit_month_logic,
        sales_month_min, sales_month_max, sales_month_logic, sort,
    )
    run_search("favorites", params, limit=limit, offset=offset, as_json=as_json)


@favorites_app.command("export")
def export(
    query: str = p.QUERY,
    country: str = p.COUNTRY,
    store: list[str] = p.STORE,
    upc_list: str = p.UPC_LIST,
    asin_list: str = p.ASIN_LIST,
    export_format: str = typer.Option("csv", "--format", help="csv or xlsx"),
    output: str = typer.Option(None, "--output", "-o", help="Output file path (default: server-suggested filename)"),
):
    """Export your favorites (up to 2500 rows). Costs more credits than a search."""
    params: dict = {}
    if query:
        params["keywords"] = query
    if country:
        params["country"] = country
    if store:
        params["store"] = list(store)
    if upc_list:
        params["upc_list"] = upc_list
    if asin_list:
        params["asin_list"] = asin_list
    run_export("favorites", params, export_format, output)
