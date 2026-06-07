"""
Configuration loader with dot-access support.
"""
import yaml
from pathlib import Path
from typing import Any

_CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"
_config = None


class _DotDict(dict):
    def __getattr__(self, key: str) -> Any:
        try:
            val = self[key]
        except KeyError:
            raise AttributeError(f"Config has no key '{key}'")
        return _DotDict(val) if isinstance(val, dict) else val

    def __setattr__(self, key: str, value: Any) -> None:
        self[key] = value


def load_config(path=None) -> _DotDict:
    global _config
    with open(path or _CONFIG_PATH, "r") as f:
        _config = _DotDict(yaml.safe_load(f))
    return _config


def get_config() -> _DotDict:
    global _config
    if _config is None:
        _config = load_config()
    return _config
