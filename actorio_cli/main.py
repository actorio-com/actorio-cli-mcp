import typer
from actorio_cli.commands import auth, credits as credits_cmd, translate, usage as usage_cmd
from actorio_cli.commands.products import products_app
from actorio_cli.commands.favorites import favorites_app
from actorio_cli.commands.amazon import amazon_app
from actorio_cli.commands.reverse import reverse_app

app = typer.Typer(help="Actorio CLI", no_args_is_help=True)
app.command("login")(auth.login)
app.command("logout")(auth.logout)
app.command("whoami")(auth.whoami)
app.command("usage")(usage_cmd.usage)
app.command("buy-credits")(credits_cmd.buy_credits)
app.command("translate")(translate.translate_cmd)
app.add_typer(products_app, name="products")
app.add_typer(favorites_app, name="favorites")
app.add_typer(amazon_app, name="amazon")
app.add_typer(reverse_app, name="reverse")

@app.command("mcp")
def mcp_cmd(
    http: bool = typer.Option(
        False, "--http", help="Serve over Streamable HTTP instead of stdio (for remote clients like ChatGPT connectors)."
    ),
    host: str = typer.Option("127.0.0.1", "--host", help="Bind host for --http mode."),
    port: int = typer.Option(8765, "--port", help="Bind port for --http mode."),
    public_url: str = typer.Option(
        None, "--public-url",
        help="Public https URL this server is reachable at (e.g. your ngrok URL) — used as the "
             "OAuth issuer and to build export download links. Auto-detected from a local ngrok "
             "if not given.",
    ),
    api_base_url: str = typer.Option(
        "http://127.0.0.1:9000", "--api-base-url",
        help="Where the Actorio Django API lives (e.g. https://app.actorio.com). --http mode has "
             "no per-user config file — every caller's OAuth-verified token is used against this "
             "URL instead.",
    ),
):
    """Start the Actorio MCP server (stdio by default).

    --http mode reads MCP_OAUTH_INTERNAL_SECRET from the environment (never
    a flag, to keep it out of `ps`/shell history) — it's the shared secret
    this service uses to call Django's internal OAuth endpoints.
    """
    if http:
        from actorio_cli.mcp_server import run_http
        run_http(host=host, port=port, public_url=public_url, api_base_url=api_base_url)
    else:
        from actorio_cli.mcp_server import run
        run()


if __name__ == "__main__":
    app()
