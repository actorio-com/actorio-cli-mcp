# Actorio CLI — Agent Setup Guide

How to give a coding agent (Claude Code, Codex, or any MCP-capable assistant)
access to Actorio's product search, reverse lookup, Amazon Flip, and export
capabilities.

> **Using claude.ai, the Claude Desktop app or Cowork?** You don't need any of
> this. Add the hosted remote connector instead: **Settings → Connectors → Add
> custom connector**, URL `https://clitest.actorio.com/mcp` (temporary test
> instance), then sign in to Actorio when prompted. See the
> [README](README.md#connect-to-claude-claudeai-claude-desktop-cowork) for details.

## Prerequisites

- **Python 3.10+** and **pipx** (install with `brew install pipx` on macOS, or
  `pip install pipx` elsewhere)
- A **web browser** with an active Actorio login (for the one-time device-code
  auth flow)
- For Claude Code specifically: version 1.0.0 or later (MCP support is built
  in)

## 1. Install the CLI

```bash
pipx install actorio-cli
```

This installs all dependencies (`typer`, `rich`, `httpx`, `mcp`, `starlette`,
`uvicorn`) and puts the `actorio` entry point on your `PATH`.

Verify it's installed:

```bash
actorio --help
```

## 2. Authenticate

Log in once per machine using the device-code flow. You'll need the base URL
of the Actorio API instance (your admin will provide this):

> **Note:** `clitest.actorio.com` is a temporary test instance — the base URL
> will move to the production API (`api.actorio.com`) in the future.

```bash
actorio login --base-url https://clitest.actorio.com
```

The CLI prints a short user code and a verification URL:

```
Open https://clitest.actorio.com/cli/v1/auth/cli/authorize and enter code XXXX-XXXX
Waiting for approval…
```

Open that URL in a browser where you're already signed in to Actorio, approve
the request, and the CLI writes a bearer token to `~/.actorio/config.json`
(mode `0600`).

To confirm everything is wired up:

```bash
actorio whoami
actorio usage
```

## 3. Enable the MCP server for your agent

The `actorio mcp` command starts a Model Context Protocol server on stdio.
Your agent launches it as a subprocess and discovers its tools automatically.
Once configured, the agent can call `search_products`, `reverse_lookup`,
`export_results`, etc. without any prompting.

### Claude Code

Register the server with the `claude mcp add` command:

```bash
# Available in all your projects
claude mcp add actorio --scope user -- actorio mcp

# Or only for the current project (writes .mcp.json in the repo root,
# which you can commit so teammates get it too)
claude mcp add actorio --scope project -- actorio mcp
```

The project-scoped `.mcp.json` looks like this if you prefer to write it by
hand:

```json
{
  "mcpServers": {
    "actorio": {
      "command": "actorio",
      "args": ["mcp"]
    }
  }
}
```

Start a new Claude Code session, then run `/mcp` to confirm that `actorio`
shows as connected.

### Claude Desktop (local server)

Most Claude Desktop users should use the remote connector described at the top
of this guide, which also works in Cowork. To run the local stdio server
instead, edit `claude_desktop_config.json` (macOS:
`~/Library/Application Support/Claude/`, Windows: `%APPDATA%\Claude\`). Use
the **absolute** path from `which actorio`, because the desktop app doesn't
inherit your shell `PATH`:

```json
{
  "mcpServers": {
    "actorio": {
      "command": "/Users/you/.local/bin/actorio",
      "args": ["mcp"]
    }
  }
}
```

Fully quit and reopen Claude Desktop after editing.

### Codex (OpenAI)

Add a `mcp` entry to `~/.codex/config.toml`:

```toml
[mcp_servers.actorio]
command = "actorio"
args = ["mcp"]
```

Or in `codex.yaml` for per-project setup:

```yaml
mcp_servers:
  actorio:
    command: actorio
    args:
      - mcp
```

### Other MCP-capable agents (Zed, Continue, Cursor, etc.)

The pattern is the same: point the agent's MCP configuration at the `actorio`
binary with the `mcp` subcommand. The server uses stdio transport (no network
port), so no firewall or TLS configuration is needed.

## 4. Available tools

Once connected, the agent sees these tools. Search parameters mirror the
webapp filter set exactly.

| Tool | What it does |
|---|---|
| `search_products` | Full product catalog search with all 40+ filters (country, store, price, ROI, profit, marketplace, FBA, hazmat, etc.) |
| `search_favorites` | Same filters, scoped to the user's saved favorites |
| `search_amazon` | Amazon Flip — cross-marketplace Amazon-to-Amazon arbitrage. `store` is the source you buy from; `marketplace` the target |
| `reverse_lookup` | Given one or more ASINs, returns Amazon-side listing data (store fields are nulled for privacy) |
| `export_results` | Download the full result set as CSV or XLSX (up to 2 500 rows), saved to a local file path. Costs 5× a search |
| `get_usage` | Current credit balance, monthly allowance, reset date |

Every search/export response includes a `_meta.credits` object:

```json
{
  "_meta": {
    "credits": {
      "cost": 1,
      "remaining": 984,
      "reset": "2026-08-04T00:00:00Z"
    }
  }
}
```

Agents can read this to avoid exhausting your monthly allowance.

### Filter reference

The most commonly used filters across all search tools:

| Parameter | Type | Notes |
|---|---|---|
| `query` | string | Keyword search |
| `country` | string | Source country: `DE`, `ES`, `FR`, `GB`, `IT` |
| `store` | string[] | Supplier store names (repeatable) |
| `marketplace` | string | Target Amazon marketplace: `DE`, `ES`, `FR`, `GB`, `IT` |
| `type` | string | Supplier type: `RTL`, `WHL`, `UPL`, `EXC` |
| `price_min` / `price_max` | number | Supplier price range, VAT incl. (gross) — matches the web UI "Supplier Price (VAT incl.)" filter; products with no computed gross price are excluded, as on the web |
| `profit_min` / `profit_max` | number | Estimated profit per unit |
| `roi_min` / `roi_max` | number | ROI percentage |
| `profit_month_min` / `profit_month_max` | number | Estimated monthly profit |
| `sales_month_min` / `sales_month_max` | number | Estimated monthly sales |
| `missing_fba` | boolean | Only listings with complete FBA data (excludes incomplete) |
| `exclude_hazmat` | boolean | Exclude hazmat products |
| `competitive_price_min` / `competitive_price_max` | number | Compete against current buy box |
| `last_update` | string | Only recently refreshed: `24` or `48` (hours) |
| `sort` | string | `profit`, `-profit`, `roi`, `-roi`, `identifiers`, `price`, `last_scan`, `last_update` |
| `page` | integer | Result page (default 1; fixed page size, matches the web UI) |

Full schemas with all enums and descriptions are embedded in each tool's
JSONSchema definition — the agent reads them at connection time, so you don't
need to paste anything extra.

## 5. Credit costs

| Action | Credits |
|---|---|
| Search (products, favorites, amazon, reverse) | **1** |
| Export (CSV or XLSX) | **5** |

Your monthly allowance depends on your Actorio subscription plan. The agent
can check remaining credits at any time with `get_usage`. When credits run
out, searches return a clear error; the agent should not retry until you top
up or your allowance resets.

To buy more credits:

```bash
actorio buy-credits
```

This opens the Actorio webapp's credit-pack purchase page in your browser
(Stripe checkout). Credit packs add to your balance immediately after payment.

## 6. Verify everything works

From the terminal (not the agent):

```bash
# Confirm the CLI can talk to the API
actorio whoami
actorio usage

# Run a quick search
actorio products search "test" --limit 20

# Start the MCP server and check it starts cleanly (Ctrl+C to exit)
actorio mcp
```

From the agent, ask it to run `get_usage` or `search_products`. If the agent
responds with real data (or a clean "no results" table), the setup is
complete.

## Troubleshooting

**`actorio: command not found`**
`pipx` installs binaries to `~/.local/bin`. Make sure it's on your PATH:
```bash
pipx ensurepath
```
Then restart your shell.

**`actorio login` fails with "Could not resolve host"**
Check the `--base-url` value with your admin. If you're on a VPN or behind a
corporate proxy, set `HTTPS_PROXY` / `HTTP_PROXY`.

**Claude Desktop says the server failed to start, but `actorio mcp` works in a terminal**
The desktop app couldn't find `actorio` on its `PATH`. Put the absolute path
from `which actorio` in `command`.

**Agent says "No tools found" or "MCP server failed to start"**
Run `actorio mcp` directly in a terminal. If it exits immediately with an
error, the issue is likely a missing or expired token — run `actorio login`
again. If it sits waiting on stdin (that's correct behavior — it's a stdio
server), the issue is the agent's MCP config path or JSON syntax.

**Searches return "Out of credits"**
Your allowance is exhausted. Run `actorio usage` to confirm, then either wait
for the monthly reset or run `actorio buy-credits`.

**Export returns "upgrade required"**
Product exports require the `full_search` permission, which comes with higher
plan tiers. Searches still work; contact Actorio to upgrade.
