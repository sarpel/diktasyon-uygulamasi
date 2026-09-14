"""STT modelini ilk çalıştırmadan önce indirir (kurulum sonrası / build öncesi).

Ayarlardaki model ve compute_type kullanılır; GPU desteklemiyorsa motor
desteklenen en iyi hassasiyete kendisi düşer.
"""

import sys

from dikte import paths
from dikte.config import load_settings
from dikte.stt.engine import FasterWhisperEngine, SttError


def main() -> int:
    settings = load_settings()
    engine = FasterWhisperEngine(settings.stt)
    try:
        engine.load()
    except SttError as exc:
        print("HATA:", exc, file=sys.stderr)
        return 1
    print(f"OK: {settings.stt.model} ({engine.compute_type})")
    print("Model dizini:", paths.models_dir())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
