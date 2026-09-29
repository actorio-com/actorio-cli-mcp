import typer
from actorio_cli.commands._common import run_export, run_search

reverse_app = typer.Typer(help="Reverse lookup by ASIN list", no_args_is_help=True)

ASINS = typer.Argument(..., help="One or more ASINs, comma or space separated")
ACTORIO_ONLY = typer.Option(
    False, "--actorio-only", help="Only rows with an Actorio match (hide unknown ASINs)"
)


@reverse_app.command("search")
def search(
    asins: str = ASINS,
    actorio_only: bool = ACTORIO_ONLY,
    limit: int = typer.Option(None, help="Results per request (server default: 16, max 100)"),
    offset: int = typer.Option(0, help="Skip this many results"),
    as_json: bool = typer.Option(False, "--json"),
):
    # The webapp filterset reads `asin_list` (10-char tokens, comma/space separated)
    params: dict = {"asin_list": asins.strip()}
    if actorio_only:
        params["actorio_only"] = "true"
    run_search("reverse", params, limit=limit, offset=offset, as_json=as_json)


@reverse_app.command("export")
def export(
    asins: str = ASINS,
    export_format: str = typer.Option("csv", "--format", help="csv or xlsx"),
    output: str = typer.Option(None, "--output", "-o", help="Output file path"),
):
    """Export the ASIN list (same as the web 'actorio-asin-list' export)."""
    params = {"asin_list": asins.strip()}
    run_export("reverse", params, export_format, output)
