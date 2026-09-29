import json
import typer
from actorio_cli.client import Client, ApiError
from actorio_cli.config import load_config
from actorio_cli.output import print_credits_footer, print_products_table


def _client_or_exit() -> Client:
    cfg = load_config()
    if cfg is None:
        typer.echo("Not logged in. Run `actorio login`.", err=True)
        raise typer.Exit(1)
    return Client(base_url=cfg.base_url, token=cfg.token)


def _echo_api_error(e: ApiError) -> None:
    if e.code == "out_of_credits":
        typer.echo(f"Out of credits: {e.message}", err=True)
        typer.echo("Top up with `actorio buy-credits`.", err=True)
    elif e.code == "unauthorized":
        typer.echo("Token invalid. Run `actorio login`.", err=True)
    elif e.code == "upgrade_required":
        typer.echo(f"Upgrade required: {e.message}", err=True)
    else:
        typer.echo(f"Error: {e}", err=True)


def run_search(kind: str, params: dict, *, limit: int | None, offset: int,
               as_json: bool) -> None:
    client = _client_or_exit()
    try:
        data = client.search(kind, params, limit=limit, offset=offset)
    except ApiError as e:
        _echo_api_error(e)
        raise typer.Exit(1)
    if as_json:
        typer.echo(json.dumps(data, indent=2, default=str))
    else:
        print_products_table(data["results"], data["pagination"], params)
        if client.last_credits:
            print_credits_footer(client.last_credits)


def run_export(kind: str, params: dict, export_format: str, output: str | None) -> None:
    export_format = export_format.lower()
    if export_format not in ("csv", "xlsx"):
        typer.echo("Format must be csv or xlsx.", err=True)
        raise typer.Exit(1)
    client = _client_or_exit()
    try:
        content, filename = client.export(kind, params, export_format=export_format)
    except ApiError as e:
        _echo_api_error(e)
        raise typer.Exit(1)
    path = output or filename
    with open(path, "wb") as fh:
        fh.write(content)
    typer.echo(f"Saved {len(content)} bytes to {path}")
    if client.last_credits:
        print_credits_footer(client.last_credits)
