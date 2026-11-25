from unittest.mock import patch, MagicMock
from typer.testing import CliRunner
from actorio_cli.main import app
from actorio_cli.config import Config

runner = CliRunner()


@patch("actorio_cli.commands.auth.webbrowser.open")
@patch("actorio_cli.commands.auth.time.sleep", lambda s: None)
@patch("actorio_cli.commands.auth.Client")
@patch("actorio_cli.commands.auth.save_config")
def test_login_happy_path(mock_save, mock_client_cls, mock_browser, isolated_config_path):
    client = MagicMock()
    client.device_start.return_value = {
        "device_code": "dc", "user_code": "UC",
        "verification_url": "https://actorio.example/x",
        "expires_in": 600, "interval": 0,
    }
    from actorio_cli.client import ApiError
    client.device_poll.side_effect = [
        ApiError(code="authorization_pending", message="wait", status=400),
        {"token": "act_new"},
    ]
    mock_client_cls.return_value = client

    result = runner.invoke(app, ["login", "--base-url", "https://actorio.example", "--label", "laptop"])
    assert result.exit_code == 0, result.output
    mock_save.assert_called_once()
    saved: Config = mock_save.call_args.args[0]
    assert saved.token == "act_new"
    assert saved.token_label == "laptop"


def test_whoami_not_logged_in(isolated_config_path):
    result = runner.invoke(app, ["whoami"])
    assert result.exit_code != 0
    assert "login" in result.output.lower()


def _save_login():
    from actorio_cli.config import save_config
    save_config(Config(base_url="https://a", token="act_t", token_label="laptop"))


@patch("actorio_cli.commands.auth.Client")
def test_whoami_logged_in(mock_client_cls, isolated_config_path):
    _save_login()
    mock_client_cls.return_value.me.return_value = {
        "username": "alice", "email": "alice@example.com",
        "token_label": "laptop",
        "searches": {"products": True, "favorites": True,
                     "amazon": False, "reverse": False},
    }
    result = runner.invoke(app, ["whoami"])
    assert result.exit_code == 0, result.output
    assert "User: alice <alice@example.com>" in result.output
    assert "Token label: laptop" in result.output
    assert "Searches: products, favorites" in result.output


@patch("actorio_cli.commands.auth.Client")
def test_whoami_email_username_not_repeated(mock_client_cls, isolated_config_path):
    _save_login()
    mock_client_cls.return_value.me.return_value = {
        "username": "a@example.com", "email": "a@example.com", "searches": {},
    }
    result = runner.invoke(app, ["whoami"])
    assert "User: a@example.com\n" in result.output


@patch("actorio_cli.commands.auth.Client")
def test_whoami_revoked_token(mock_client_cls, isolated_config_path):
    from actorio_cli.client import ApiError
    _save_login()
    mock_client_cls.return_value.me.side_effect = ApiError(
        code="unknown", message="Invalid or revoked token", status=401)
    result = runner.invoke(app, ["whoami"])
    assert result.exit_code == 1
    assert "actorio login" in result.output


@patch("actorio_cli.commands.auth.Client")
def test_whoami_old_server_falls_back_to_local_info(mock_client_cls, isolated_config_path):
    from actorio_cli.client import ApiError
    _save_login()
    mock_client_cls.return_value.me.side_effect = ApiError(
        code="unknown", message="Not Found", status=404)
    result = runner.invoke(app, ["whoami"])
    assert result.exit_code == 0
    assert "Token label: laptop" in result.output
    assert "User: unknown" in result.output


@patch("actorio_cli.commands.auth.Client")
def test_whoami_server_unreachable(mock_client_cls, isolated_config_path):
    import httpx
    _save_login()
    mock_client_cls.return_value.me.side_effect = httpx.ConnectError("boom")
    result = runner.invoke(app, ["whoami"])
    assert result.exit_code == 0
    assert "could not reach server" in result.output


def test_logout_removes_config(isolated_config_path):
    from actorio_cli.config import save_config
    save_config(Config(base_url="https://a", token="act_t", token_label="l"))
    assert isolated_config_path.exists()
    result = runner.invoke(app, ["logout"])
    assert result.exit_code == 0
    assert not isolated_config_path.exists()


def test_logout_when_not_logged_in(isolated_config_path):
    result = runner.invoke(app, ["logout"])
    assert result.exit_code == 0
    assert "not logged in" in result.output.lower()
