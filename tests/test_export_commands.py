from unittest.mock import patch, MagicMock
from typer.testing import CliRunner
from actorio_cli.main import app
from actorio_cli.config import Config, save_config

runner = CliRunner()


def _login():
    save_config(Config(base_url="https://a", token="t", token_label="l"))


def _client_mock():
    m = MagicMock()
    m.export.return_value = (b"a,b\n1,2\n", "actorio-amazon-flips.csv")
    m.last_credits = None
    return m


@patch("actorio_cli.commands._common.Client")
def test_amazon_export_writes_file(mock_client_cls, isolated_config_path, tmp_path):
    _login()
    m = _client_mock()
    mock_client_cls.return_value = m
    out = tmp_path / "flips.csv"
    result = runner.invoke(
        app,
        ["amazon", "export", "--marketplace", "DE", "--output", str(out)],
    )
    assert result.exit_code == 0, result.output
    assert out.read_bytes() == b"a,b\n1,2\n"
    assert m.export.call_args.args[0] == "amazon"
    assert m.export.call_args.args[1]["marketplace"] == "DE"
    assert m.export.call_args.kwargs["export_format"] == "csv"


@patch("actorio_cli.commands._common.Client")
def test_products_export_xlsx(mock_client_cls, isolated_config_path, tmp_path, monkeypatch):
    _login()
    m = _client_mock()
    m.export.return_value = (b"bin", "actorio-product-search.xlsx")
    mock_client_cls.return_value = m
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(
        app, ["products", "export", "lego", "--format", "xlsx", "--roi-min", "20"]
    )
    assert result.exit_code == 0, result.output
    assert (tmp_path / "actorio-product-search.xlsx").read_bytes() == b"bin"
    params = m.export.call_args.args[1]
    assert params["keywords"] == "lego"
    assert params["roi_min"] == 20.0


@patch("actorio_cli.commands._common.Client")
def test_export_rejects_bad_format(mock_client_cls, isolated_config_path):
    _login()
    mock_client_cls.return_value = _client_mock()
    result = runner.invoke(app, ["reverse", "export", "B000000001", "--format", "pdf"])
    assert result.exit_code == 1
    assert "csv or xlsx" in result.output


@patch("actorio_cli.commands._common.Client")
def test_search_sends_advanced_filters(mock_client_cls, isolated_config_path):
    _login()
    m = MagicMock()
    m.search.return_value = {
        "results": [],
        "pagination": {"page": 1, "per_page": 20, "total": 0, "has_more": False},
    }
    m.last_credits = None
    mock_client_cls.return_value = m
    result = runner.invoke(
        app,
        [
            "products", "search", "lego",
            "--roi-min", "25",
            "--profit-month-min", "100",
            "--missing-fba",
            "--category", "toys",
            "--category", "games",
            "--marketplace", "DE",
        ],
    )
    assert result.exit_code == 0, result.output
    params = m.search.call_args.args[1]
    assert params["roi_min"] == 25.0
    assert params["profit_month_min"] == 100.0
    assert params["missing_fba"] == "true"
    assert params["category"] == ["toys", "games"]
    assert params["marketplace"] == "DE"


@patch("actorio_cli.commands._common.Client")
def test_reverse_search_sends_asin_list(mock_client_cls, isolated_config_path):
    _login()
    m = MagicMock()
    m.search.return_value = {
        "results": [],
        "pagination": {"page": 1, "per_page": 20, "total": 0, "has_more": False},
    }
    m.last_credits = None
    mock_client_cls.return_value = m
    result = runner.invoke(app, ["reverse", "search", "B000000001,B000000002"])
    assert result.exit_code == 0, result.output
    params = m.search.call_args.args[1]
    assert params["asin_list"] == "B000000001,B000000002"


@patch("actorio_cli.commands._common.Client")
def test_buy_credits_prints_url(mock_client_cls, isolated_config_path):
    _login()
    m = MagicMock()
    m.purchase_info.return_value = {"purchase_url": "https://app.actorio.com/subscriptions/cli_credits/"}
    mock_client_cls.return_value = m
    with patch("typer.launch") as mock_launch:
        result = runner.invoke(app, ["buy-credits"])
    assert result.exit_code == 0, result.output
    assert "cli_credits" in result.output
    mock_launch.assert_called_once()

    with patch("typer.launch") as mock_launch:
        result = runner.invoke(app, ["buy-credits", "--no-open"])
    assert result.exit_code == 0
    mock_launch.assert_not_called()
