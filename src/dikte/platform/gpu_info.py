from __future__ import annotations

import logging
import subprocess
from collections.abc import Callable
from dataclasses import dataclass

log = logging.getLogger(__name__)

LOW_VRAM_MB = 1536


@dataclass(frozen=True)
class VramInfo:
    used_mb: int
    total_mb: int


def _run_nvidia_smi() -> str:
    return subprocess.check_output(
        ["nvidia-smi", "--query-gpu=memory.used,memory.total", "--format=csv,noheader,nounits"],
        timeout=3,
        text=True,
    )


def query_vram(runner: Callable[..., object] | None = None) -> VramInfo | None:
    """`nvidia-smi` çıktısının ilk satırını ayrıştırır; kurulu değilse/parse edilemezse None."""
    run = runner or _run_nvidia_smi
    try:
        output = run()
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        log.info("VRAM bilgisi alınamadı: %s", exc)
        return None
    first_line = str(output).splitlines()[0] if str(output).strip() else ""
    try:
        used_str, total_str = first_line.split(",")
        return VramInfo(int(used_str.strip()), int(total_str.strip()))
    except (ValueError, IndexError) as exc:
        log.info("VRAM çıktısı ayrıştırılamadı: %r (%s)", first_line, exc)
        return None


def format_vram(info: VramInfo | None) -> str:
    if info is None:
        return "bilinmiyor"
    used_gb = info.used_mb / 1024
    total_gb = info.total_mb / 1024
    return f"{used_gb:.1f} / {total_gb:.1f} GB".replace(".", ",")
