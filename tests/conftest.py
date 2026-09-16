import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _has_cuda() -> bool:
    try:
        import ctranslate2  # type: ignore[import-not-found]

        return ctranslate2.get_cuda_device_count() > 0
    except Exception:
        return False


def pytest_runtest_setup(item):
    if "gpu" in item.keywords and not _has_cuda():
        pytest.skip("CUDA yok")
    if "win" in item.keywords and sys.platform != "win32":
        pytest.skip("yalnızca Windows")
