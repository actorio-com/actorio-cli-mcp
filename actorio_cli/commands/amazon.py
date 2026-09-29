import typer
from actorio_cli.commands import products as p
from actorio_cli.commands._common import run_export, run_search
from actorio_cli.commands._filters import build_params

amazon_app = typer.Typer(
    help="Amazon Flip: cross-marketplace Amazon-to-Amazon arbitrage",
    no_args_is_help=True,
)

# Amazon Flip searches EU Amazon listings; 'store' is the SOURCE marketplace
SOURCE_STORE = typer.Option(
    None,
    "--store",
    help="Source Amazon marketplace: amazon.de, amazon.es, amazon.fr, amazon.co.uk, amazon.it",
)


def _collect_amazon(
    query, store, upc_list, asin_list, price_min, price_max, marketplace,
    price_reference, last_update, missing_fba, multipack, size, category,
    competitive_price_min, competitive_price_max, competitive_price_logic,
    profit_min, profit_max, profit_logic, roi_min, roi_max, roi_logic,
    profit_month_min, profit_month_max, profit_month_logic,
    sales_month_min, sales_month_max, sales_month_logic, sort,
) -> dict:
    return build_params(
        keywords=query,
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
        size=size,
        category=category,
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


@amazon_app.command("search")
def search(
    query: str = p.QUERY,
    store: str = SOURCE_STORE,
    upc_list: str = p.UPC_LIST,
    asin_list: str = p.ASIN_LIST,
    price_min: float = p.PRICE_MIN,
    price_max: float = p.PRICE_MAX,
    marketplace: str = p.MARKETPLACE,
    price_reference: str = p.PRICE_REFERENCE,
    last_update: str = p.LAST_UPDATE,
    missing_fba: bool = p.MISSING_FBA,
    multipack: bool = p.MULTIPACK,
    size: list[str] = p.SIZE,
    category: list[str] = p.CATEGORY,
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
    as_json: bool = typer.Option(False, "--json"),
):
    params = _collect_amazon(
        query, store, upc_list, asin_list, price_min, price_max, marketplace,
        price_reference, last_update, missing_fba, multipack, size, category,
        competitive_price_min, competitive_price_max, competitive_price_logic,
        profit_min, profit_max, profit_logic, roi_min, roi_max, roi_logic,
        profit_month_min, profit_month_max, profit_month_logic,
        sales_month_min, sales_month_max, sales_month_logic, sort,
    )
    run_search("amazon", params, limit=limit, offset=offset, as_json=as_json)


@amazon_app.command("export")
def export(
    query: str = p.QUERY,
    store: str = SOURCE_STORE,
    upc_list: str = p.UPC_LIST,
    asin_list: str = p.ASIN_LIST,
    price_min: float = p.PRICE_MIN,
    price_max: float = p.PRICE_MAX,
    marketplace: str = p.MARKETPLACE,
    price_reference: str = p.PRICE_REFERENCE,
    last_update: str = p.LAST_UPDATE,
    missing_fba: bool = p.MISSING_FBA,
    multipack: bool = p.MULTIPACK,
    size: list[str] = p.SIZE,
    category: list[str] = p.CATEGORY,
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
    export_format: str = typer.Option("csv", "--format", help="csv or xlsx"),
    output: str = typer.Option(None, "--output", "-o", help="Output file path"),
):
    """Export Amazon flips (up to 2500 rows), like the web export button."""
    params = _collect_amazon(
        query, store, upc_list, asin_list, price_min, price_max, marketplace,
        price_reference, last_update, missing_fba, multipack, size, category,
        competitive_price_min, competitive_price_max, competitive_price_logic,
        profit_min, profit_max, profit_logic, roi_min, roi_max, roi_logic,
        profit_month_min, profit_month_max, profit_month_logic,
        sales_month_min, sales_month_max, sales_month_logic, sort,
    )
    run_export("amazon", params, export_format, output)
