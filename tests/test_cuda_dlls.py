import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from dikte import cuda_dlls


@pytest.fixture
def fake_windows(monkeypatch, tmp_path):
    bin_dir = tmp_path / "cublas" / "bin"
    bin_dir.mkdir(parents=True)
    added: list[str] = []
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(os, "add_dll_directory", added.append, raising=False)
    monkeypatch.setattr(
        cuda_dlls.importlib.util,
        "find_spec",
        lambda name: (
            SimpleNamespace(submodule_search_locations=[str(bin_dir.parent)])
            if name == "nvidia.cublas"
            else None
        ),
    )
    monkeypatch.setenv("PATH", "C:\\Windows")
    monkeypatch.setattr(cuda_dlls, "_registered", None)
    return bin_dir, added


def test_register_is_idempotent(fake_windows):
    bin_dir, added = fake_windows
    first = cuda_dlls.register_nvidia_dll_dirs()
    second = cuda_dlls.register_nvidia_dll_dirs()
    assert first == second == [str(bin_dir)]
    assert added == [str(bin_dir)]  # DLL dizini yalnızca bir kez eklenir
    assert os.environ["PATH"].count(str(bin_dir)) == 1  # PATH her çağrıda büyümez


def test_linux_without_nvidia_wheels_is_noop(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(cuda_dlls, "_registered", None)
    monkeypatch.setattr(cuda_dlls.importlib.util, "find_spec", lambda name: None)
    assert cuda_dlls.register_nvidia_dll_dirs() == []


def test_linux_preloads_wheel_libraries_globally_once(monkeypatch, tmp_path):
    """Autostart/--toggle başlatıcıyı atlayınca LD_LIBRARY_PATH yoktur; pip'in
    nvidia/*/lib kütüphaneleri RTLD_GLOBAL ile önceden yüklenir."""
    roots = {}
    for pkg, libs in {
        "cublas": ("libcublas.so.12", "libcublasLt.so.12", "libnvblas.so.12"),
        "cudnn": ("libcudnn.so.9", "libcudnn_ops.so.9"),
    }.items():
        lib = tmp_path / pkg / "lib"
        lib.mkdir(parents=True)
        for name in libs:
            (lib / name).write_bytes(b"")
        (lib / "__init__.py").write_text("")
        roots[f"nvidia.{pkg}"] = tmp_path / pkg
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(cuda_dlls, "_registered", None)
    monkeypatch.setattr(
        cuda_dlls.importlib.util,
        "find_spec",
        lambda name: (
            SimpleNamespace(submodule_search_locations=[str(roots[name])])
            if name in roots
            else None
        ),
    )
    loaded = []

    def fake_load(path, mode):
        if "nvblas" in path:
            raise OSError("bağımlılık eksik")
        loaded.append((Path(path).name, mode))

    monkeypatch.setattr(cuda_dlls, "_load_library", fake_load)
    first = cuda_dlls.register_nvidia_dll_dirs()
    second = cuda_dlls.register_nvidia_dll_dirs()
    names = [n for n, _ in loaded]
    assert names.index("libcublasLt.so.12") < names.index("libcublas.so.12")
    assert names.index("libcudnn.so.9") < names.index("libcudnn_ops.so.9")
    assert all(mode == cuda_dlls.ctypes.RTLD_GLOBAL for _, mode in loaded)
    assert len(loaded) == 4  # ikinci çağrı yeniden yüklemez; başarısız olan atlanır
    assert first == second == [str(tmp_path / "cublas" / "lib"), str(tmp_path / "cudnn" / "lib")]
