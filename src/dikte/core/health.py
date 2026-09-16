from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from dikte.config import LlmSettings, Settings

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class HealthItem:
    name: str
    ok: bool
    detail: str
    hint: str


def model_is_cached(model: str, root: Path) -> bool:
    """Varsayılan model_probe: `root` altında `*<model>*/**/model.bin` eşleşmesi arar."""
    return any(root.glob(f"*{model}*/**/model.bin"))


def check_health(
    settings: Settings,
    *,
    cuda_probe: Callable[[], int],
    model_probe: Callable[[str], bool],
    llm_probe: Callable[[LlmSettings], str | None],
) -> tuple[HealthItem, ...]:
    cuda_count = cuda_probe()
    gpu = HealthItem(
        name="GPU",
        ok=cuda_count >= 1,
        detail=f"{cuda_count} CUDA aygıtı" if cuda_count >= 1 else "CUDA aygıtı bulunamadı",
        hint="" if cuda_count >= 1 else "NVIDIA sürücüleri ve CUDA kurulumunu kontrol edin.",
    )
    cached = model_probe(settings.stt.model)
    model = HealthItem(
        name="Whisper modeli",
        ok=cached,
        detail="önbellekte" if cached else "indirilmemiş",
        hint="" if cached else 'Aşağıdaki "Modeli indir" ile indirin.',
    )
    if not settings.llm.enabled:
        llm = HealthItem(name="LLM", ok=True, detail="kapalı", hint="")
    else:
        error = llm_probe(settings.llm)
        llm = HealthItem(
            name="LLM",
            ok=error is None,
            detail="bağlantı kuruldu" if error is None else error,
            hint="" if error is None else "Ayarlar → Metin Düzeltme'den sağlayıcıyı kontrol edin.",
        )
    return (gpu, model, llm)


def default_cuda_probe() -> int:
    try:
        import ctranslate2

        return ctranslate2.get_cuda_device_count()
    except Exception as exc:  # noqa: BLE001 - bilgi amaçlı; hata uygulamayı durdurmamalı
        log.debug("CUDA sayısı alınamadı: %s", exc)
        return 0


def default_model_probe(model: str) -> bool:
    from dikte import paths

    return model_is_cached(model, paths.models_dir())


def default_llm_probe(llm: LlmSettings) -> str | None:
    from dikte.llm import LlmError, make_provider

    try:
        provider = make_provider(llm)
        provider.complete("Yanıt: OK", "OK")
        return None
    except LlmError as exc:
        return str(exc)
    except Exception as exc:  # noqa: BLE001 - ağ/sağlayıcı hatası kullanıcıya metin gösterilir
        return str(exc)
