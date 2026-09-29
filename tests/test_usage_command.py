import json
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from actorio_cli.config import Config, save_config
from actorio_cli.main import app

runner = CliRunner()


def _login():
    save_config(Config(base_url="https://a", token="t", token_label="l"))


USAGE_RESP = {
    "monthly_included": 1000,
    "monthly_used": 250,
    "monthly_remaining": 750,
    "pack_balance": 100,
    "effective_remaining": 850,
    "period_start": "2026-04-01T00:00:00+00:00",
    "period_end": "2026-05-01T00:00:00+00:00",
    "warned_80": False,
}


@patch("actorio_cli.commands.usage.Client")
def test_usage_table(mock_client_cls, isolated_config_path):
    _login()
    client = MagicMock()
    client.usage.return_value = USAGE_RESP
    mock_client_cls.return_value = client
    result = runner.invoke(app, ["usage"])
    assert result.exit_code == 0, result.output
    assert "1000" in result.output
    assert "250" in result.output
    assert "850" in result.output


@patch("actorio_cli.commands.usage.Client")
def test_usage_json(mock_client_cls, isolated_config_path):
    _login()
    client = MagicMock()
    client.usage.return_value = USAGE_RESP
    mock_client_cls.return_value = client
    result = runner.invoke(app, ["usage", "--json"])
    assert result.exit_code == 0
    assert json.loads(result.output) == USAGE_RESP


def test_usage_requires_login(isolated_config_path):
    result = runner.invoke(app, ["usage"])
    assert result.exit_code != 0
    assert "login" in result.output.lower()


@patch("actorio_cli.commands._common.Client")
def test_search_prints_credit_footer(mock_client_cls, isolated_config_path):
    """When client.last_credits is set, run_search prints a footer line."""
    _login()
    client = MagicMock()
    client.search.return_value = {
        "results": [],
        "pagination": {"page": 1, "per_page": 20, "total": 0, "has_more": False},
    }
    client.last_credits = {
        "cost": 1,
        "remaining": 999,
        "reset": "2026-05-01T00:00:00+00:00",
        "warning": None,
    }
    mock_client_cls.return_value = client
    result = runner.invoke(app, ["products", "search", "lego"])
    assert result.exit_code == 0
    assert "999" in result.output
