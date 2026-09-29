import typer
from actorio_cli.client import ApiError
from actorio_cli.commands._common import _client_or_exit


def buy_credits(
    no_open: bool = typer.Option(False, "--no-open", help="Print the URL without opening a browser"),
):
    """Open the Actorio credit-pack purchase page (billing lives in the webapp)."""
    client = _client_or_exit()
    try:
        info = client.purchase_info()
    except ApiError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    url = info["purchase_url"]
    typer.echo(f"Buy credit packs at: {url}")
    if not no_open:
        typer.launch(url)
