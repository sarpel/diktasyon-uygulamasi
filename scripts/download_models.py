"""STT modelini ilk çalıştırmadan önce indirir (kurulum sonrası / build öncesi).

Yalnızca dosyaları indirir; modeli GPU'ya yüklemez. Bu yüzden CUDA kitaplıkları henüz
hazır olmayan (ör. yeni kurulmuş) bir makinede de çalışır. Ayarlardaki model adı kullanılır.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

from dikte import paths
from dikte.config import Settings, load_settings
from dikte.stt.download import download_model

RETRY_HINT = (
    "İnternet bağlantınızı kontrol edip `python scripts/download_models.py` komutunu yeniden "
    "çalıştırın; ya da uygulamada Ayarlar → Hakkında → Durum kontrolü… penceresinden indirin."
)


class _Progress:
    """Yüzdeyi %10'luk adımlarla yazar; tqdm çıktısıyla karışmaması için tek satır."""

    def __init__(self) -> None:
        self._last = -1

    def __call__(self, done: int, total: int) -> None:
        if total <= 0:
            return
        step = min(100, done * 100 // total) // 10 * 10
        if step > self._last:
            self._last = step
            print(f"  %{step}", flush=True)


def main(
    *,
    download: Callable[[str, Path, Callable[[int, int], None]], Path] = download_model,
    settings_loader: Callable[[], Settings] = load_settings,
    models_dir: Callable[[], Path] = paths.models_dir,
) -> int:
    model = settings_loader().stt.model
    root = models_dir()
    print(f"Model indiriliyor: {model} → {root}", flush=True)
    try:
        path = download(model, root, _Progress())
    except Exception as exc:  # noqa: BLE001 - kurulum betiği; kullanıcıya ne yapacağı söylenir
        print(f"HATA: {model} modeli indirilemedi: {exc}", file=sys.stderr)
        print(RETRY_HINT, file=sys.stderr)
        return 1
    print(f"OK: {model}")
    print("Model dizini:", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
