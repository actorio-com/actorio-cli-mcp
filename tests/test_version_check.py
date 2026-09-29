import pytest
from unittest.mock import patch
from typer.testing import CliRunner

import actorio_cli.version_check as vc
from actorio_cli.main import app
from actorio_cli.config import Config, save_config

runner = CliRunner()


def _enable_check(monkeypatch, latest="99.0.0", installed="0.1.0"):
    """Undo the conftest opt-out and pin both versions for this test."""
    monkeypatch.delenv(vc.NO_CHECK_ENV, raising=False)
    monkeypatch.setattr(vc, "latest_version", lambda: latest)
    monkeypatch.setattr(vc, "installed_version", lambda: installed)


def test_notice_when_newer_available(monkeypatch, isolated_config_path):
    _enable_check(monkeypatch)
    result = runner.invoke(app, ["translate", "store=carrefour.es"])
    assert result.exit_code == 0, result.output
    assert "actorio products search" in result.output
    assert "99.0.0" in result.output
    assert "pip install -U actorio-cli" in result.output


def test_notice_goes_to_stderr(monkeypatch, isolated_config_path):
    """The upgrade notice uses stderr, keeping stdout parseable for --json pipelines."""

    class Done:
        def join(self, timeout):  # noqa: ANN001
            pass

    printed = []
    monkeypatch.setattr(vc.typer, "echo", lambda msg, err=False: printed.append((msg, err)))
    vc._active = (Done(), "0.1.0", {"latest": "99.0.0"})
    vc.finish_version_check(None)
    assert len(printed) == 1
    assert printed[0][1] is True  # err=True → stderr
    assert "99.0.0" in printed[0][0]
    assert vc._active is None  # consumed


def test_silent_when_up_to_date(monkeypatch, isolated_config_path):
    _enable_check(monkeypatch, latest="0.1.0")
    result = runner.invoke(app, ["translate", "store=x"])
    assert result.exit_code == 0, result.output
    assert "new version" not in result.output


def test_silent_when_pypi_unreachable(monkeypatch, isolated_config_path):
    _enable_check(monkeypatch, latest=None)
    result = runner.invoke(app, ["translate", "store=x"])
    assert result.exit_code == 0, result.output
    assert "new version" not in result.output


def test_throttled_by_cache_file(monkeypatch, isolated_config_path):
    monkeypatch.delenv(vc.NO_CHECK_ENV, raising=False)
    vc.cache_path().touch()  # fresh timestamp → skip the network
    monkeypatch.setattr(vc, "installed_version", lambda: "0.1.0")

    def boom():
        raise AssertionError("latest_version must not be called with a fresh cache")

    monkeypatch.setattr(vc, "latest_version", boom)
    result = runner.invoke(app, ["translate", "store=x"])
    assert result.exit_code == 0, result.output


def test_env_var_disables_check(monkeypatch, isolated_config_path):
    # conftest leaves NO_CHECK set — verify it short-circuits entirely
    def boom():
        raise AssertionError("latest_version must not be called when disabled")

    monkeypatch.setattr(vc, "latest_version", boom)
    result = runner.invoke(app, ["translate", "store=x"])
    assert result.exit_code == 0, result.output
    assert not vc.cache_path().exists()


def test_mcp_subcommand_skipped(monkeypatch, isolated_config_path):
    monkeypatch.delenv(vc.NO_CHECK_ENV, raising=False)
    monkeypatch.setattr(vc, "installed_version", lambda: "0.1.0")

    def boom():
        raise AssertionError("no version check in mcp mode")

    monkeypatch.setattr(vc, "latest_version", boom)
    assert vc.start_version_check("mcp") is None


@patch("actorio_cli.commands._common.Client")
def test_nested_subcommand_triggers_check(mock_client_cls, monkeypatch, isolated_config_path):
    """The root callback runs for sub-app commands (products search) too."""
    _enable_check(monkeypatch)
    save_config(Config(base_url="https://a", token="t", token_label="l"))
    mock_client_cls.return_value.search.return_value = {
        "results": [],
        "pagination": {"page": 1, "per_page": 20, "total": 0, "has_more": False},
    }
    result = runner.invoke(app, ["products", "search", "lego"])
    assert result.exit_code == 0, result.output
    assert "99.0.0" in result.output


def test_version_flag(monkeypatch, isolated_config_path):
    monkeypatch.setattr(vc, "installed_version", lambda: "1.2.3")
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert result.output.strip() == "1.2.3"


def test_bare_invocation_shows_help(monkeypatch, isolated_config_path):
    result = runner.invoke(app, [])
    assert result.exit_code == 0
    assert result.output.strip().startswith("Usage:")


@pytest.mark.parametrize(
    "latest,current,expected",
    [
        ("0.2.0", "0.1.0", True),
        ("0.10.0", "0.9.0", True),
        ("0.1.0", "0.1.0", False),
        ("0.1.0", "0.2.0", False),
        ("0.1.0", "0.1.0rc1", True),
        ("not-a-version", "0.1.0", False),
    ],
)
def test_is_newer(latest, current, expected):
    assert vc.is_newer(latest, current) is expected


def test_upgrade_hint_detects_pipx():
    assert vc.upgrade_hint("/home/u/.local/pipx/venvs/actorio-cli") == "pipx upgrade actorio-cli"
    assert vc.upgrade_hint("/home/u/env") == "pip install -U actorio-cli"
