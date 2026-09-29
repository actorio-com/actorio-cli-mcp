import typer
from actorio_cli.commands._common import run_export, run_search
from actorio_cli.commands._filters import LOGIC_HELP, build_params

products_app = typer.Typer(help="Product catalog search and export", no_args_is_help=True)


def _collect(
    query, country, type_, store, upc_list, asin_list, price_min, price_max,
    marketplace, price_reference, last_update, missing_fba, multipack,
    variations, hazmat, suppressed_buybox, size, category, similarity,
    competitive_price_min, competitive_price_max, competitive_price_logic,
    profit_min, profit_max, profit_logic, roi_min, roi_max, roi_logic,
    profit_month_min, profit_month_max, profit_month_logic,
    sales_month_min, sales_month_max, sales_month_logic, sort,
) -> dict:
    return build_params(
        keywords=query,
        country=country,
        type=type_,
        store=store,
        upc_list=upc_list,
        asin_list=asin_list,
        price_min=price_min,
        price_max=price_max,
        marketplace=marketplace,
        price_reference=price_reference,
        last_update=last_update,
        missing_fba=missing_fba,
        multipack=multipack,
        variations=variations,
        hazmat=hazmat,
        suppressed_buybox=suppressed_buybox,
        size=size,
        category=category,
        similarity=similarity,
        competitive_price_min=competitive_price_min,
        competitive_price_max=competitive_price_max,
        competitive_price_logic=competitive_price_logic,
        profit_min=profit_min,
        profit_max=profit_max,
        profit_logic=profit_logic,
        roi_min=roi_min,
        roi_max=roi_max,
        roi_logic=roi_logic,
        profit_month_min=profit_month_min,
        profit_month_max=profit_month_max,
        profit_month_logic=profit_month_logic,
        sales_month_min=sales_month_min,
        sales_month_max=sales_month_max,
        sales_month_logic=sales_month_logic,
        sort=sort,
    )


# Shared option declarations (webapp filterset params, see _filters.py)
QUERY = typer.Argument(None, help="Keywords")
COUNTRY = typer.Option(None, help="Source country code, e.g. DE")
TYPE = typer.Option(None, "--type", help="Supplier type: RTL, WHL, UPL or EXC")
STORE = typer.Option(None, help="Supplier store (repeatable)")
UPC_LIST = typer.Option(None, "--upc-list", help="Comma/space separated UPC/EANs")
ASIN_LIST = typer.Option(None, "--asin-list", help="Comma/space separated ASINs")
PRICE_MIN = typer.Option(None, "--price-min", help="Min supplier price, VAT incl. (gross); same as the web UI Supplier Price filter")
PRICE_MAX = typer.Option(None, "--price-max", help="Max supplier price, VAT incl. (gross); same as the web UI Supplier Price filter")
MARKETPLACE = typer.Option(None, help="Target Amazon marketplace: DE, ES, FR, GB, IT")
PRICE_REFERENCE = typer.Option(None, "--price-reference", help="'avg30' for 30-day average prices")
LAST_UPDATE = typer.Option(None, "--last-update", help="Only recently updated: 24 or 48 (hours)")
MISSING_FBA = typer.Option(False, "--missing-fba", help="Only products without FBA sellers")
MULTIPACK = typer.Option(False, "--multipack", help="Include multipack matches")
VARIATIONS = typer.Option(False, "--variations", help="Include listings with variations")
HAZMAT = typer.Option(False, "--hazmat", help="Include hazmat products")
SUPPRESSED_BUYBOX = typer.Option(False, "--suppressed-buybox", help="Include suppressed-buybox listings")
SIZE = typer.Option(None, help="Size category code, e.g. SML_PAR (repeatable)")
CATEGORY = typer.Option(None, help="Amazon category code (repeatable)")
SIMILARITY = typer.Option(None, help="Match similarity level (0-3)")
COMPETITIVE_PRICE_MIN = typer.Option(None, "--competitive-price-min", help="Min competitive price (EUR)")
COMPETITIVE_PRICE_MAX = typer.Option(None, "--competitive-price-max", help="Max competitive price (EUR)")
COMPETITIVE_PRICE_LOGIC = typer.Option(None, "--competitive-price-logic", help=LOGIC_HELP)
PROFIT_MIN = typer.Option(None, "--profit-min", help="Min unit profit (EUR)")
PROFIT_MAX = typer.Option(None, "--profit-max", help="Max unit profit (EUR)")
PROFIT_LOGIC = typer.Option(None, "--profit-logic", help=LOGIC_HELP)
ROI_MIN = typer.Option(None, "--roi-min", help="Min unit ROI (%)")
ROI_MAX = typer.Option(None, "--roi-max", help="Max unit ROI (%)")
ROI_LOGIC = typer.Option(None, "--roi-logic", help=LOGIC_HELP)
PROFIT_MONTH_MIN = typer.Option(None, "--profit-month-min", help="Min monthly profit (EUR)")
PROFIT_MONTH_MAX = typer.Option(None, "--profit-month-max", help="Max monthly profit (EUR)")
PROFIT_MONTH_LOGIC = typer.Option(None, "--profit-month-logic", help=LOGIC_HELP)
SALES_MONTH_MIN = typer.Option(None, "--sales-month-min", help="Min monthly sales")
SALES_MONTH_MAX = typer.Option(None, "--sales-month-max", help="Max monthly sales")
SALES_MONTH_LOGIC = typer.Option(None, "--sales-month-logic", help=LOGIC_HELP)
SORT = typer.Option(None, help="Sort key, e.g. profit, -profit, identifiers")


@products_app.command("search")
def search(
    query: str = QUERY,
    country: str = COUNTRY,
    type_: str = TYPE,
    store: list[str] = STORE,
    upc_list: str = UPC_LIST,
    asin_list: str = ASIN_LIST,
    price_min: float = PRICE_MIN,
    price_max: float = PRICE_MAX,
    marketplace: str = MARKETPLACE,
    price_reference: str = PRICE_REFERENCE,
    last_update: str = LAST_UPDATE,
    missing_fba: bool = MISSING_FBA,
    multipack: bool = MULTIPACK,
    variations: bool = VARIATIONS,
    hazmat: bool = HAZMAT,
    suppressed_buybox: bool = SUPPRESSED_BUYBOX,
    size: list[str] = SIZE,
    category: list[str] = CATEGORY,
    similarity: int = SIMILARITY,
    competitive_price_min: float = COMPETITIVE_PRICE_MIN,
    competitive_price_max: float = COMPETITIVE_PRICE_MAX,
    competitive_price_logic: str = COMPETITIVE_PRICE_LOGIC,
    profit_min: float = PROFIT_MIN,
    profit_max: float = PROFIT_MAX,
    profit_logic: str = PROFIT_LOGIC,
    roi_min: float = ROI_MIN,
    roi_max: float = ROI_MAX,
    roi_logic: str = ROI_LOGIC,
    profit_month_min: float = PROFIT_MONTH_MIN,
    profit_month_max: float = PROFIT_MONTH_MAX,
    profit_month_logic: str = PROFIT_MONTH_LOGIC,
    sales_month_min: float = SALES_MONTH_MIN,
    sales_month_max: float = SALES_MONTH_MAX,
    sales_month_logic: str = SALES_MONTH_LOGIC,
    sort: str = SORT,
    limit: int = typer.Option(None, help="Results per request (server default: 20, max 100)"),
    offset: int = typer.Option(0, help="Skip this many results"),
    as_json: bool = typer.Option(
        False,
        "--json",
        help="Output raw JSON ({results, pagination}) instead of a table; "
             "page with --offset/--limit while pagination.has_more is true",
    ),
):
    """Search the product catalog.

    For CSV/XLSX files use `actorio products export` — same filters, costs
    more credits than a search.
    """
    params = _collect(
        query, country, type_, store, upc_list, asin_list, price_min, price_max,
        marketplace, price_reference, last_update, missing_fba, multipack,
        variations, hazmat, suppressed_buybox, size, category, similarity,
        competitive_price_min, competitive_price_max, competitive_price_logic,
        profit_min, profit_max, profit_logic, roi_min, roi_max, roi_logic,
        profit_month_min, profit_month_max, profit_month_logic,
        sales_month_min, sales_month_max, sales_month_logic, sort,
    )
    run_search("products", params, limit=limit, offset=offset, as_json=as_json)


@products_app.command("export")
def export(
    query: str = QUERY,
    country: str = COUNTRY,
    type_: str = TYPE,
    store: list[str] = STORE,
    upc_list: str = UPC_LIST,
    asin_list: str = ASIN_LIST,
    price_min: float = PRICE_MIN,
    price_max: float = PRICE_MAX,
    marketplace: str = MARKETPLACE,
    price_reference: str = PRICE_REFERENCE,
    last_update: str = LAST_UPDATE,
    missing_fba: bool = MISSING_FBA,
    multipack: bool = MULTIPACK,
    variations: bool = VARIATIONS,
    hazmat: bool = HAZMAT,
    suppressed_buybox: bool = SUPPRESSED_BUYBOX,
    size: list[str] = SIZE,
    category: list[str] = CATEGORY,
    similarity: int = SIMILARITY,
    competitive_price_min: float = COMPETITIVE_PRICE_MIN,
    competitive_price_max: float = COMPETITIVE_PRICE_MAX,
    competitive_price_logic: str = COMPETITIVE_PRICE_LOGIC,
    profit_min: float = PROFIT_MIN,
    profit_max: float = PROFIT_MAX,
    profit_logic: str = PROFIT_LOGIC,
    roi_min: float = ROI_MIN,
    roi_max: float = ROI_MAX,
    roi_logic: str = ROI_LOGIC,
    profit_month_min: float = PROFIT_MONTH_MIN,
    profit_month_max: float = PROFIT_MONTH_MAX,
    profit_month_logic: str = PROFIT_MONTH_LOGIC,
    sales_month_min: float = SALES_MONTH_MIN,
    sales_month_max: float = SALES_MONTH_MAX,
    sales_month_logic: str = SALES_MONTH_LOGIC,
    sort: str = SORT,
    export_format: str = typer.Option("csv", "--format", help="csv or xlsx"),
    output: str = typer.Option(None, "--output", "-o", help="Output file path (default: server-suggested filename)"),
):
    """Export the full result set (up to 2500 rows) like the web export button. Costs more credits than a search."""
    params = _collect(
        query, country, type_, store, upc_list, asin_list, price_min, price_max,
        marketplace, price_reference, last_update, missing_fba, multipack,
        variations, hazmat, suppressed_buybox, size, category, similarity,
        competitive_price_min, competitive_price_max, competitive_price_logic,
        profit_min, profit_max, profit_logic, roi_min, roi_max, roi_logic,
        profit_month_min, profit_month_max, profit_month_logic,
        sales_month_min, sales_month_max, sales_month_logic, sort,
    )
    run_export("products", params, export_format, output)
