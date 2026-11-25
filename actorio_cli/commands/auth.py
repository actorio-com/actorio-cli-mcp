import socket
import time
import webbrowser
import httpx
import typer
from actorio_cli.client import Client, ApiError
from actorio_cli.config import Config, load_config, save_config
import actorio_cli.config as cfg_module


def login(
    base_url: str = typer.Option(
        ..., "--base-url",
        help="Actorio API base URL, e.g. https://clitest.actorio.com "
             "(temporary test instance — will move to api.actorio.com)",
    ),
    label: str = typer.Option(None, "--label", help="Token label; defaults to hostname"),
):
    """Authenticate via device-code flow."""
    label = label or socket.gethostname()
    client = Client(base_url=base_url, token=None)
    start = client.device_start(label=label)
    typer.echo(f"Open this URL in your browser: {start['verification_url']}")
    typer.echo(f"Then enter this code to approve: {start['user_code']}")
    try:
        webbrowser.open(start["verification_url"])
    except Exception:
        pass
    deadline = time.time() + start.get("expires_in", 600)
    interval = start.get("interval", 2)
    while time.time() < deadline:
        try:
            result = client.device_poll(start["device_code"])
        except ApiError as e:
            if e.code == "authorization_pending":
                time.sleep(interval)
                continue
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(1)
        save_config(Config(base_url=base_url, token=result["token"], token_label=label))
        typer.echo(f"Logged in as {label}.")
        return
    typer.echo("Timed out waiting for approval.", err=True)
    raise typer.Exit(1)


def logout():
    """Delete local credentials."""
    if cfg_module.DEFAULT_PATH.exists():
        cfg_module.DEFAULT_PATH.unlink()
        typer.echo("Logged out.")
    else:
        typer.echo("Not logged in.")


def whoami():
    """Show the current login."""
    cfg = load_config()
    if cfg is None:
        typer.echo("Not logged in. Run `actorio login`.", err=True)
        raise typer.Exit(1)
    typer.echo(f"Base URL: {cfg.base_url}")
    try:
        me = Client(base_url=cfg.base_url, token=cfg.token).me()
    except ApiError as e:
        if e.status == 401:
            typer.echo(f"Token label: {cfg.token_label}")
            typer.echo("Token is invalid or revoked. Run `actorio login`.", err=True)
            raise typer.Exit(1)
        # e.g. 404 from a server that predates /cli/v1/me
        typer.echo(f"Token label: {cfg.token_label}")
        typer.echo(f"User: unknown (server error: {e})", err=True)
        return
    except httpx.HTTPError as e:
        typer.echo(f"Token label: {cfg.token_label}")
        typer.echo(f"User: unknown (could not reach server: {e})", err=True)
        return
    user = me["username"]
    if me.get("email") and me["email"].lower() != user.lower():
        user += f" <{me['email']}>"
    typer.echo(f"User: {user}")
    typer.echo(f"Token label: {me.get('token_label') or cfg.token_label}")
    searches = me.get("searches") or {}
    if searches:
        allowed = [k for k, ok in searches.items() if ok]
        typer.echo(f"Searches: {', '.join(allowed) if allowed else 'none'}")
