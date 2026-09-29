import pytest
from pathlib import Path
import actorio_cli.config as cfg_module


@pytest.fixture(autouse=True)
def isolated_config_path(tmp_path, monkeypatch):
    """Each test gets its own config file location, so we never touch ~/.actorio."""
    p = tmp_path / "config.json"
    monkeypatch.setattr(cfg_module, "DEFAULT_PATH", p)
    return p
