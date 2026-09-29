import json
from unittest.mock import patch, MagicMock
from typer.testing import CliRunner
from actorio_cli.main import app
from actorio_cli.config import Config, save_config

runner = CliRunner()

RESP = {
    "results": [{"id": 1, "title": "Lego Set", "price": 12.34, "currency": "EUR",
                 "brand": "Lego", "store": "shop.de", "asin": "B00", "upc": "123"}],
    "pagination": {"page": 1, "per_page": 20, "total": 1, "has_more": False},
}


def _login(isolated_config_path):
    save_config(Config(base_url="https://a", token="t", token_label="l"))


@patch("actorio_cli.commands._common.Client")
def test_products_search_table(mock_client_cls, isolated_config_path):
    _login(isolated_config_path)
    client = MagicMock()
    client.search.return_value = RESP
    mock_client_cls.return_value = client
    result = runner.invoke(app, ["products", "search", "lego", "--country", "DE"])
    assert result.exit_code == 0, result.output
    assert "Lego Set" in result.output
    call = client.search.call_args
    assert call.args[0] == "products"
    assert "lego" in str(call.args[1])
    assert "DE" in str(call.args[1])


FULL_ROW = {
    "id": 2,
    "title": "Philips Multigroom Series 5000",
    "brand": "Philips",
    "store": "argos.co.uk",
    "country": "UK",
    "type": "RTL",
    "asin": "B075QGBMH7",
    "upc": "8710103794813",
    "reference": "879/2557",
    "price": 90.00,
    "currency": "GBP",
    "vat_included": True,
    "vat": 0.20,
    "net_price": 75.00,
    "net_price_eur": 88.50,
    "gross_price": 90.00,
    "gross_price_eur": 106.20,
    "size_tier": "SML_PAR",
    "amz_title_gb": "Philips Multigroom Series 5000 11-in-1",
    "competitive_price_gb": 82.50,
    "sellers_gb": 3,
    "new_amz_sellers_gb": 0,
    "profit_gb": -25.01,
    "roi_gb": -28,
    "sales_30_days_gb": 65,
    "profit_month_gb": 0.00,
    "total_sales_30_days": 65,
    "total_profit_month": 0.00,
}

FULL_RESP = {
    "results": [FULL_ROW],
    "pagination": {"page": 1, "per_page": 20, "total": 1, "has_more": False},
}


@patch("actorio_cli.commands._common.Client")
def test_products_search_marketplace_columns(mock_client_cls, isolated_config_path):
    """The table shows per-marketplace data like the webapp product table."""
    _login(isolated_config_path)
    client = MagicMock()
    client.search.return_value = FULL_RESP
    mock_client_cls.return_value = client
    result = runner.invoke(app, ["products", "search", "philips"])
    assert result.exit_code == 0, result.output
    out = result.output
    # every marketplace row is rendered
    for cc in ("DE", "ES", "FR", "GB", "IT"):
        assert cc in out
    assert "82.50 £" in out          # GB competitive price in local currency
    assert "3 (0 FBA)" in out        # sellers with FBA count
    assert "-25.01 €" in out         # unit profit
    assert "-28 %" in out            # unit ROI
    assert "65" in out               # monthly sales
    assert "75.00 £ VAT excl. (88.50 €)" in out
    assert "90.00 £ VAT 20% incl. (106.20 €)" in out
    assert "ASIN B075QGBMH7" in out
    assert "EAN 8710103794813" in out
    assert "N/A" in out              # marketplaces without data


@patch("actorio_cli.commands._common.Client")
def test_products_search_json(mock_client_cls, isolated_config_path):
    _login(isolated_config_path)
    client = MagicMock()
    client.search.return_value = RESP
    mock_client_cls.return_value = client
    result = runner.invoke(app, ["products", "search", "lego", "--json"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed == RESP


def test_requires_login(isolated_config_path):
    result = runner.invoke(app, ["products", "search", "lego"])
    assert result.exit_code != 0
    assert "login" in result.output.lower()


@patch("actorio_cli.commands._common.Client")
def test_products_search_limit_offset(mock_client_cls, isolated_config_path):
    _login(isolated_config_path)
    client = MagicMock()
    client.search.return_value = {
        "results": [],
        "pagination": {"total": 0, "limit": 50, "offset": 100,
                       "has_more": False, "page": 3, "per_page": 50},
    }
    mock_client_cls.return_value = client
    result = runner.invoke(
        app, ["products", "search", "lego", "--limit", "50", "--offset", "100"]
    )
    assert result.exit_code == 0, result.output
    call = client.search.call_args
    assert call.kwargs["limit"] == 50
    assert call.kwargs["offset"] == 100
