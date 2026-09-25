from __future__ import annotations

import logging
import os
import re
from collections.abc import Callable, Iterator
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


_MODEL_FILE = "model.bin"


def _iter_model_files(root: Path) -> Iterator[Path]:
    """`root` altındaki tüm `model.bin` dosyalarını üretir; okunamayan girdileri atlar.

    `Path.glob` her adayı `stat()` ile doğrular ve symlink'i izler. Windows'ta HF
    önbelleği `snapshots/<rev>/model.bin`i `blobs/<sha>`ya symlink'lediğinden bu
    doğrulama "WinError 448: güvenilmeyen bağlama noktası" ile patlayabiliyor ve
    uygulamayı açılışta düşürüyordu. Bu yüzden dizin listesi üzerinden, symlink
    izlemeden ilerlenir ve her OSError yutulur.
    """
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            stack.append(Path(entry.path))
                        elif entry.name == _MODEL_FILE:
                            yield Path(entry.path)
                    except OSError as exc:  # tek bir girdi okunamadı; tarama sürmeli
                        log.debug("Model önbelleği girdisi okunamadı (%s): %s", entry.path, exc)
        except OSError as exc:  # dizin listelenemedi (izin, symlink, ağ sürücüsü)
            log.debug("Model önbelleği dizini taranamadı (%s): %s", current, exc)


def model_is_cached(model: str, root: Path) -> bool:
    """Varsayılan model_probe: `root` altında `*<model>*/**/model.bin` eşleşmesi arar.

    Salt alt dize eşleşmesi yanlış pozitif üretir: model="large-v3" iken
    "faster-whisper-large-v3-turbo" dizini de eşleşirdi. Model adından hemen sonra
    (isteğe bağlı bir "-" ile) başka bir alfasayısal karakter gelmemesi şartı aranır.
    """
    guard = re.compile(re.escape(model) + r"(?!-?[0-9a-zA-Z])")
    for path in _iter_model_files(root):
        parts = path.relative_to(root).parts
        if len(parts) < 2 or model not in parts[0]:
            continue
        if guard.search(str(path)):
            return True
    return False


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
    from dikte.cuda_dlls import register_nvidia_dll_dirs

    # Motorla aynı koşullarda sorgula: Windows'ta DLL dizinleri kaydedilmeden ctranslate2
    # GPU'yu göremeyebilir ve denetim, çalışan motorla çelişen "GPU yok" derdi.
    try:
        register_nvidia_dll_dirs()
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
