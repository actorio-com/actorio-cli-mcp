import json
import os
from actorio_cli.config import Config, load_config, save_config
import actorio_cli.config as cfg_module


def test_save_load_roundtrip(isolated_config_path):
    cfg = Config(base_url="https://actorio.example", token="act_abc", token_label="laptop")
    save_config(cfg)
    loaded = load_config()
    assert loaded == cfg


def test_file_mode_is_0600(isolated_config_path):
    save_config(Config(base_url="x", token="y", token_label="z"))
    mode = os.stat(cfg_module.DEFAULT_PATH).st_mode & 0o777
    assert mode == 0o600


def test_load_missing_returns_none(isolated_config_path):
    assert load_config() is None
