"""pip ile kurulan nvidia-cublas-cu12 / nvidia-cudnn-cu12 wheel'lerinin kütüphanelerini
ctranslate2'nin bulabilmesini sağlar: Windows'ta DLL arama yoluna ekler, Linux'ta
`RTLD_GLOBAL` ile önceden yükler (autostart veya doğrudan `python -m dikte` başlatıcıyı
atlayınca LD_LIBRARY_PATH ayarlı olmaz)."""

import ctypes
import importlib.util
import logging
import os
import sys
from pathlib import Path

log = logging.getLogger(__name__)
_PACKAGES = ("nvidia.cublas", "nvidia.cudnn")
_registered: list[str] | None = None  # ilk tamamlanan kayıttan sonra (boş olsa da) tekrarlanmaz
_load_library = ctypes.CDLL  # testlerde değiştirilir


def _package_dir(pkg: str, sub: str) -> Path | None:
    spec = importlib.util.find_spec(pkg)
    if spec is None or not spec.submodule_search_locations:
        return None
    path = Path(next(iter(spec.submodule_search_locations))) / sub
    return path if path.is_dir() else None


def _preload_order(lib: Path) -> list[Path]:
    """Bağımlılık sırası: cublasLt cublas'tan, ana libcudnn alt kütüphanelerinden önce."""
    files = sorted(p for p in lib.iterdir() if ".so" in p.name)

    def rank(p: Path) -> tuple[int, str]:
        name = p.name
        if name.startswith("libcublasLt"):
            return (0, name)
        if name.startswith("libcublas."):
            return (1, name)
        if name.startswith("libcudnn."):
            return (2, name)
        return (3, name)

    return sorted(files, key=rank)


def _register_linux() -> list[str]:
    added: list[str] = []
    for pkg in _PACKAGES:
        lib = _package_dir(pkg, "lib")
        if lib is None:
            continue
        for path in _preload_order(lib):
            try:
                _load_library(str(path), mode=ctypes.RTLD_GLOBAL)
            except OSError as exc:
                # Bazı yardımcı kütüphaneler (ör. nvblas) kullanılmaz ve yüklenemeyebilir.
                log.debug("CUDA kütüphanesi önceden yüklenemedi (%s): %s", path.name, exc)
        added.append(str(lib))
    return added


def _register_windows() -> list[str]:
    added: list[str] = []
    for pkg in _PACKAGES:
        bin_dir = _package_dir(pkg, "bin")
        if bin_dir is not None:
            os.add_dll_directory(str(bin_dir))
            os.environ["PATH"] = f"{bin_dir};{os.environ.get('PATH', '')}"
            added.append(str(bin_dir))
    return added


def register_nvidia_dll_dirs() -> list[str]:
    """NVIDIA wheel kütüphanelerini kaydeder; eklenen dizinleri döndürür (yoksa boş liste).

    İdempotent: ilk çağrının sonucu saklanır, böylece motor, sağlık denetimi vb. her
    çağırdığında PATH büyümez. macOS gibi diğer platformlarda hiçbir şey yapmaz."""
    global _registered
    if _registered is not None:
        return list(_registered)
    if sys.platform == "win32":
        added = _register_windows()
    elif sys.platform.startswith("linux"):
        added = _register_linux()
    else:
        added = []
    log.info("NVIDIA kütüphane dizinleri: %s", added)
    _registered = added
    return list(added)
