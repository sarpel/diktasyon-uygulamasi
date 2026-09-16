"""Whisper modelini ilerleme geri bildirimiyle indirir (Ayarlar → Hakkında → "Durum kontrolü…").

`huggingface_hub`/`tqdm`, `faster-whisper`in geçişli bağımlılıklarıdır; ayrı bir
paket eklenmedi.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import cast

log = logging.getLogger(__name__)


def download_model(
    model: str,
    root: Path,
    progress: Callable[[int, int], None],
    downloader: Callable[..., object] | None = None,
) -> Path:
    """`model` için HF Hub snapshot'ını `root`'a indirir; `progress(done, total)` çağrılır."""
    from faster_whisper.utils import _MODELS
    from huggingface_hub import snapshot_download
    from tqdm import tqdm

    # cast: `tqdm_class` özel alt sınıfımızı kabul eder, ancak hub tip taslakları
    # yalnızca `tqdm_asyncio` bildirir.
    run = cast(Callable[..., object], downloader or snapshot_download)
    repo_id = _MODELS.get(model, model)

    class _ProgressTqdm(tqdm):
        def update(self, n=1):
            super().update(n)
            progress(self.n, self.total or 0)

    result = run(repo_id=repo_id, cache_dir=str(root), tqdm_class=_ProgressTqdm)
    return Path(str(result))
