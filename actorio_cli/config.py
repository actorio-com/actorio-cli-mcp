import json
import os
from dataclasses import dataclass, asdict
from pathlib import Path

DEFAULT_PATH = Path.home() / ".actorio" / "config.json"


@dataclass
class Config:
    base_url: str
    token: str
    token_label: str


def load_config() -> "Config | None":
    path = DEFAULT_PATH
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    return Config(**data)


def save_config(cfg: Config) -> None:
    path = DEFAULT_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(cfg), indent=2))
    os.chmod(path, 0o600)
