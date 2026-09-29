import json
import typer
from actorio_cli.client import Client, ApiError
from actorio_cli.config import load_config
from actorio_cli.output import print_usage_table


def usage(
    as_json: bool = typer.Option(False, "--json", help="Output raw JSON"),
):
    """Show your CLI credit balance."""
    cfg = load_config()
    if cfg is None:
        typer.echo("Not logged in. Run `actorio login`.", err=True)
        raise typer.Exit(1)
    client = Client(base_url=cfg.base_url, token=cfg.token)
    try:
        data = client.usage()
    except ApiError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    if as_json:
        typer.echo(json.dumps(data, indent=2, default=str))
    else:
        print_usage_table(data)
