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


def test_whoami_logged_in(isolated_config_path):
    from actorio_cli.config import save_config
    save_config(Config(base_url="https://a", token="act_t", token_label="laptop"))
    result = runner.invoke(app, ["whoami"])
    assert result.exit_code == 0
    assert "laptop" in result.output


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
