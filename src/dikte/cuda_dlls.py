"""pip ile kurulan nvidia-cublas-cu12 / nvidia-cudnn-cu12 wheel'lerinin DLL'lerini
Windows'ta ctranslate2'nin bulabilmesi için DLL arama yoluna ekler."""

import importlib.util
import logging
import os
import sys
from pathlib import Path

log = logging.getLogger(__name__)
_PACKAGES = ("nvidia.cublas", "nvidia.cudnn")
_registered: list[str] | None = None  # ilk başarılı kayıttan sonra tekrar yapılmaz


def register_nvidia_dll_dirs() -> list[str]:
    """Idempotent: motor, sağlık denetimi vb. her çağırdığında PATH büyümesin."""
    global _registered
    if sys.platform != "win32":
        return []
    if _registered is not None:
        return list(_registered)
    added: list[str] = []
    for pkg in _PACKAGES:
        spec = importlib.util.find_spec(pkg)
        if spec is None or not spec.submodule_search_locations:
            continue
        bin_dir = Path(next(iter(spec.submodule_search_locations))) / "bin"
        if bin_dir.is_dir():
            os.add_dll_directory(str(bin_dir))
            os.environ["PATH"] = f"{bin_dir};{os.environ.get('PATH', '')}"
            added.append(str(bin_dir))
    log.info("NVIDIA DLL dizinleri: %s", added)
    _registered = added
    return list(added)
