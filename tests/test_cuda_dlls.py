import os
import sys
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


def test_non_windows_is_noop(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    assert cuda_dlls.register_nvidia_dll_dirs() == []
