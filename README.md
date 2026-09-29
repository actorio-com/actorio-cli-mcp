# actorio-cli

A command-line client and MCP server for Actorio's product search. It wraps the
same search endpoints the web UI uses (products, favorites, Amazon, reverse
lookup) and exposes them both as interactive CLI commands and as tools for AI
assistants via the Model Context Protocol.

## Install

Install from PyPI — pipx is recommended so the `actorio` entry point gets an
isolated environment:

```bash
pipx install actorio-cli
# or, if you prefer a plain pip install into your environment:
pip install actorio-cli
```

For development against a local checkout:

```bash
pip install -e ".[test]"
```

Both methods install the `actorio` entry point on your `PATH`.

## Authentication

Log in once per machine using the device-code flow:

```bash
actorio login --base-url https://api.actorio.com
```
```

The CLI prints a short user code and a verification URL. Open the URL in a
browser where you are already signed in to Actorio and approve the request.
The CLI polls until the approval lands, then writes a token to
`~/.actorio/config.json` with file mode `0600`.

To revoke a token, use the Actorio account settings page (coming soon — for
now, contact Actorio support or run `actorio logout` locally to forget the
token on this machine).

## Commands

Every search command accepts `--limit` (server default 20, or 16 for reverse search; max 100), `--offset` (default 0) and `--json`.
Without `--json`, results render as a Rich table mirroring the webapp
product table: identifiers (ASIN/EAN/SKU), Amazon + supplier titles,
VAT-aware supplier price (net/gross with EUR equivalents), and
per-marketplace rows (DE/ES/FR/GB/IT) for Amazon price, sellers (with FBA
count), unit profit, unit ROI, monthly sales and monthly profit, plus the
monthly totals. With `--price-reference avg30` the table switches to the
30-day-average price/profit columns, like the webapp toggle. `--json`
returns every field the backend has for each row.

- `actorio login --base-url URL [--label LABEL]` — start the device-code
  login flow and store the issued token.
  ```bash
  actorio login --base-url https://api.actorio.com --label laptop
  ```
- `actorio logout` — delete the local config file.
  ```bash
  actorio logout
  ```
- `actorio whoami` — print the stored base URL, token label, and username.
  ```bash
  actorio whoami
  ```
- `actorio products search [QUERY] [filters...] [--limit 20] [--offset 0] [--json]`
  — search the product catalog with the full webapp filter set.
  ```bash
  actorio products search "lego star wars" --country DE --price-max 50
  actorio products search --roi-min 30 --profit-month-min 200 --marketplace DE --missing-fba
  ```
- `actorio favorites search [QUERY] [filters...] [--limit] [--offset] [--json]`
  — search your saved favorites (same filters as products).
  ```bash
  actorio favorites search headphones --json
  ```
- `actorio amazon search [QUERY] [filters...] [--limit] [--offset] [--json]`
  — Amazon Flip: cross-marketplace Amazon-to-Amazon arbitrage. `--store` is
  the source marketplace you buy from; `--marketplace` the target you compare
  against.
  ```bash
  actorio amazon search --store amazon.es --marketplace DE --roi-min 20
  ```
- `actorio reverse search ASINS [--actorio-only] [--limit] [--offset] [--json]`
  — reverse lookup for one or more ASINs (comma or space separated).
  ```bash
  actorio reverse search "B09XYZ1234,B08ABC5678"
  ```
- `actorio products|favorites|amazon|reverse export [filters...] [--format csv|xlsx] [--output FILE]`
  — download the full filtered result set (up to 2500 rows), matching the
  web UI's export buttons. Exports cost more credits than searches.
  ```bash
  actorio amazon export --marketplace DE --roi-min 20 --format xlsx -o flips.xlsx
  ```
- `actorio usage` — show your credit balance, allowance and reset date.
- `actorio buy-credits [--no-open]` — open the credit-pack purchase page
  (billing happens in the Actorio web app).
- `actorio mcp` — start the MCP server on stdio. Intended to be launched by
  an MCP-capable client, not run interactively.

### Advanced filters

Every filter the web UI offers is available as a flag on
`products`/`favorites` (and most on `amazon`) search/export commands:

`--country`, `--type` (RTL/WHL/UPL/EXC), `--store` (repeatable),
`--upc-list`, `--asin-list`, `--price-min/max` (supplier price VAT
incl., i.e. the web UI's "Supplier Price" filter), `--marketplace`
(DE/ES/FR/GB/IT), `--price-reference avg30`, `--last-update 24|48`,
`--missing-fba`, `--multipack`, `--variations`, `--hazmat`,
`--suppressed-buybox`, `--size` (repeatable), `--category` (repeatable),
`--similarity 0-3`, `--competitive-price-min/max`, `--profit-min/max`,
`--roi-min/max`, `--profit-month-min/max`, `--sales-month-min/max`
(each range has a `--*-logic all` variant: blank = ANY marketplace,
`all` = ALL marketplaces), and `--sort` (e.g. `profit`, `-profit`,
`identifiers`).

Plan limits apply exactly as on the web: e.g. filters your plan doesn't
include are ignored/forced server-side, and product exports require the
full-search permission.

## Output formats

By default, results print as a human-friendly Rich table. Pass `--json` for
machine-readable output — this is the format MCP tools and any scripting use.
JSON output includes both `results` and `pagination` (with `total`, `page`,
`per_page`, and `has_more`).

## MCP setup for Claude Desktop

Add an entry to your Claude Desktop `mcp.json`:

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

The MCP server exposes these tools, each mirroring the parameters of the
matching CLI command (including all advanced filters):

- `search_products`
- `search_favorites`
- `search_amazon` — Amazon Flip arbitrage search
- `reverse_lookup` — takes `asins` (comma/space separated)
- `export_results` — saves a CSV/XLSX export to a local path
- `get_usage` — credit balance and reset date

Search responses include `_meta.credits` (cost, remaining, reset) so agents
can track spend. You must `actorio login` on the same machine first. The MCP
server reads the same `~/.actorio/config.json` the CLI writes.

## Config file

Location: `~/.actorio/config.json`, mode `0600`.

Fields:

- `base_url` — the Actorio instance this token was issued for.
- `token` — the bearer token (`act_...`).
- `token_label` — the label supplied at `login` time.

Delete it with `actorio logout`.

## Pagination

Search commands take `--limit` (results per request; server default 20 for
products/favorites/amazon, 16 for reverse, max 100) and `--offset` (skip
this many results, default 0). When using `--json`, check
`pagination.has_more` to decide whether to fetch more by increasing
`--offset` by `--limit`.
