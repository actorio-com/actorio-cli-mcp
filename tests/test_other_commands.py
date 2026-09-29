from unittest.mock import patch, MagicMock
from typer.testing import CliRunner
from actorio_cli.main import app
from actorio_cli.config import Config, save_config

runner = CliRunner()
EMPTY = {"results": [], "pagination": {"page": 1, "per_page": 20, "total": 0, "has_more": False}}


def _login():
    save_config(Config(base_url="https://a", token="t", token_label="l"))


@patch("actorio_cli.commands._common.Client")
def test_favorites_search(mock_client_cls, isolated_config_path):
    _login()
    m = MagicMock(); m.search.return_value = EMPTY; mock_client_cls.return_value = m
    result = runner.invoke(app, ["favorites", "search", "--country", "DE"])
    assert result.exit_code == 0, result.output
    assert m.search.call_args.args[0] == "favorites"


@patch("actorio_cli.commands._common.Client")
def test_amazon_search(mock_client_cls, isolated_config_path):
    _login()
    m = MagicMock(); m.search.return_value = EMPTY; mock_client_cls.return_value = m
    result = runner.invoke(app, ["amazon", "search", "lego"])
    assert result.exit_code == 0
    assert m.search.call_args.args[0] == "amazon"
    assert "lego" in str(m.search.call_args.args[1])


@patch("actorio_cli.commands._common.Client")
def test_reverse_search(mock_client_cls, isolated_config_path):
    _login()
    m = MagicMock(); m.search.return_value = EMPTY; mock_client_cls.return_value = m
    result = runner.invoke(app, ["reverse", "search", "B00X"])
    assert result.exit_code == 0
    assert m.search.call_args.args[0] == "reverse"
    assert "B00X" in str(m.search.call_args.args[1])
