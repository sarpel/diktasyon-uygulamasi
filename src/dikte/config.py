from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from dikte import paths

log = logging.getLogger(__name__)


class SttSettings(BaseModel):
    model_config = ConfigDict(frozen=True)
    model: str = "large-v3-turbo"
    device: Literal["cuda"] = "cuda"  # CPU kasıtlı olarak desteklenmez; GPU yoksa hata verilir
    compute_type: str = "float16"
    language: str = "tr"
    beam_size: int = Field(default=5, ge=1, le=10)
    vad_filter: bool = True
    initial_prompt: str = "Türkçe konuşma. Noktalama işaretleri kullanılır."
    # Uzun kayıtlarda BatchedInferencePipeline; kısa diktede kazanç yok, VRAM'i artırır.
    batch_enabled: bool = True
    batch_threshold_s: float = Field(default=60.0, ge=0)
    batch_size: int = Field(default=8, ge=1, le=32)
    # Model yüklendikten sonra kısa bir sahte çözümleme; ilk gerçek diktenin gecikmesini alır.
    warm_up: bool = True


class LlmSettings(BaseModel):
    model_config = ConfigDict(frozen=True)
    # VRAM'i STT ile paylaşmak istemeyen makinelerde düzeltme tamamen kapatılabilir.
    enabled: bool = True
    # Whisper yüklenirken LLM'i de belleğe alır (yalnızca Ollama'da anlamlı).
    prewarm: bool = True
    provider: Literal["ollama", "anthropic"] = "ollama"
    model: str = "qwen3.5:4b"
    ollama_host: str = "http://127.0.0.1:11434"
    anthropic_model: str = "claude-sonnet-5"
    keep_alive: str = "30m"
    timeout_s: float = Field(default=120.0, gt=0)
    think: bool = False  # Qwen3.5 varsayılan olarak düşünür; kapalı tutulur
    num_ctx: int = Field(default=8192, ge=2048)  # KV cache'i küçük tut (VRAM)
    top_p: float = 0.8
    top_k: int = 20


class AudioSettings(BaseModel):
    model_config = ConfigDict(frozen=True)
    device_index: int | None = None  # None = sistem varsayılanı
    sample_rate: int = 16000
    max_seconds: int = Field(default=0, ge=0)  # 0 = sınırsız


class Settings(BaseModel):
    model_config = ConfigDict(frozen=True)
    hotkey: str = "ctrl+alt+space"
    autostart: bool = True
    close_after_copy: bool = False
    history_limit: int = Field(default=200, ge=0)
    stt: SttSettings = SttSettings()
    llm: LlmSettings = LlmSettings()
    audio: AudioSettings = AudioSettings()


def load_settings(path: Path | None = None) -> Settings:
    p = path or paths.config_path()
    if not p.exists():
        return Settings()
    try:
        return Settings.model_validate_json(p.read_text(encoding="utf-8"))
    except (ValidationError, ValueError, OSError) as exc:
        log.warning("config okunamadı (%s), varsayılanlar kullanılıyor", exc)
        backup = p.with_suffix(p.suffix + ".bak")
        try:
            backup.write_bytes(p.read_bytes())
        except OSError:
            log.exception("config yedeği yazılamadı")
        return Settings()


def save_settings(settings: Settings, path: Path | None = None) -> None:
    p = path or paths.config_path()
    tmp = p.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(settings.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    tmp.replace(p)
