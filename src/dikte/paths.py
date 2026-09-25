import contextlib
import os
import sys
from pathlib import Path

from dikte import APP_NAME

# Dikte edilen metin (config.json, history.jsonl, dikte.log) kullanıcının konuşmalarını
# içerir; çok kullanıcılı bir Linux sisteminde varsayılan umask ile bu klasör diğer
# kullanıcılarca okunabilir olurdu. POSIX'te dizin 0700 (yalnızca sahibi) ile oluşturulur.
_PRIVATE_DIR_MODE = 0o700


def _base(env_var: str, fallback: str) -> Path:
    if sys.platform == "win32" and (val := os.environ.get(env_var)):
        return Path(val)
    return Path.home() / fallback


def _ensure_private_dir(d: Path) -> Path:
    d.mkdir(parents=True, exist_ok=True)
    if sys.platform != "win32":
        with contextlib.suppress(OSError):  # en iyi çaba; salt-okunur bir aygıtta karşılaşılabilir
            d.chmod(_PRIVATE_DIR_MODE)
    return d


def app_data_dir() -> Path:
    return _ensure_private_dir(_base("APPDATA", ".config") / APP_NAME)


def models_dir() -> Path:
    return _ensure_private_dir(_base("LOCALAPPDATA", ".cache") / APP_NAME / "models")


def config_path() -> Path:
    return app_data_dir() / "config.json"


def history_path() -> Path:
    return app_data_dir() / "history.jsonl"


def log_path() -> Path:
    return app_data_dir() / "dikte.log"


def failed_audio_path() -> Path:
    """Son başarısız diktenin sesi (yeniden denemek için); her başarısızlıkta üzerine yazılır."""
    return _ensure_private_dir(app_data_dir() / "failed") / "last.wav"
