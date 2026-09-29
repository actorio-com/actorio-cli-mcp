import pytest
from pathlib import Path
import actorio_cli.config as cfg_module
import actorio_cli.version_check as version_check


@pytest.fixture(autouse=True)
def isolated_config_path(tmp_path, monkeypatch):
    """Each test gets its own config file location, so we never touch ~/.actorio."""
    p = tmp_path / "config.json"
    monkeypatch.setattr(cfg_module, "DEFAULT_PATH", p)
    return p


@pytest.fixture(autouse=True)
def no_version_check(monkeypatch):
    """Disable the PyPI update check by default; tests opt in per-test."""
    monkeypatch.setenv(version_check.NO_CHECK_ENV, "1")
