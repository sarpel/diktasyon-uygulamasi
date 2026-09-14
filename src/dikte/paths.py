import os
import sys
from pathlib import Path

from dikte import APP_NAME


def _base(env_var: str, fallback: str) -> Path:
    if sys.platform == "win32" and (val := os.environ.get(env_var)):
        return Path(val)
    return Path.home() / fallback


def app_data_dir() -> Path:
    d = _base("APPDATA", ".config") / APP_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def models_dir() -> Path:
    d = _base("LOCALAPPDATA", ".cache") / APP_NAME / "models"
    d.mkdir(parents=True, exist_ok=True)
    return d


def config_path() -> Path:
    return app_data_dir() / "config.json"


def history_path() -> Path:
    return app_data_dir() / "history.jsonl"


def log_path() -> Path:
    return app_data_dir() / "dikte.log"
