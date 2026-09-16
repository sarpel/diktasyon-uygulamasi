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
    # Silero VAD eşikleri (faster-whisper içinde gömülü). Gürültülü ortamda 0.6, yumuşak seste 0.35.
    vad_threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    vad_min_silence_ms: int = Field(default=1000, ge=0)
    vad_speech_pad_ms: int = Field(default=300, ge=0)
    # Halüsinasyon önlemleri: sessizlikte "Altyazı M.K." gibi uydurma metinleri engeller.
    no_speech_threshold: float = Field(default=0.6, ge=0.0, le=1.0)
    log_prob_threshold: float = -1.0
    hallucination_silence_threshold_s: float = Field(default=2.0, ge=0)
    hallucination_filter: bool = True
    initial_prompt: str = "Türkçe konuşmalar. Noktalama işaretleri kullanılır."
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
    provider: Literal["ollama", "lmstudio", "openai", "anthropic", "gemini", "custom"] = "ollama"
    model: str = "gemma4:e4b-it-qat"  # Ollama modeli (benchmark: docs/llm_benchmark.md)
    ollama_host: str = "http://127.0.0.1:11434"  # Ollama'nın varsayılan portu
    keep_alive: str = "30m"
    # LM Studio yerel sunucusu: OpenAI-uyumlu, varsayılan port 1234, anahtar istemez.
    lmstudio_base_url: str = "http://127.0.0.1:1234/v1"
    lmstudio_model: str = ""  # LM Studio'daki model kimliği (ör. qwen3.5-4b)
    lmstudio_api_key_env: str = ""  # boş = anahtar gönderilmez
    openai_model: str = "gpt-5.5"
    openai_base_url: str = "https://api.openai.com/v1"
    openai_api_key_env: str = "OPENAI_API_KEY"
    anthropic_model: str = "claude-sonnet-5"
    anthropic_api_key_env: str = "ANTHROPIC_API_KEY"
    gemini_model: str = "gemini-3.5-flash"
    gemini_api_key_env: str = "GEMINI_API_KEY"
    # Özel uç nokta: OpenAI-uyumlu veya Anthropic-uyumlu iki yaygın formattan biri.
    custom_format: Literal["openai", "anthropic"] = "openai"
    custom_base_url: str = ""
    custom_model: str = ""
    custom_api_key_env: str = ""  # boş = anahtar gönderilmez (yerel sunucu)
    timeout_s: float = Field(default=120.0, gt=0)
    think: bool = False  # Qwen3.5 varsayılan olarak düşünür; kapalı tutulur
    num_ctx: int = Field(default=8192, ge=2048)  # KV cache'i küçük tut (VRAM)
    top_p: float = 0.8
    top_k: int = 20

    @property
    def active_model(self) -> str:
        """Seçili sağlayıcının model adı; durum çubuğu ve günlükler bunu gösterir."""
        return {
            "ollama": self.model,
            "lmstudio": self.lmstudio_model,
            "openai": self.openai_model,
            "anthropic": self.anthropic_model,
            "gemini": self.gemini_model,
            "custom": self.custom_model,
        }[self.provider]


class AudioSettings(BaseModel):
    model_config = ConfigDict(frozen=True)
    device_index: int | None = None  # None = sistem varsayılanı
    sample_rate: int = 16000
    max_seconds: int = Field(default=0, ge=0)  # 0 = sınırsız
    silence_stop_s: float = Field(
        default=0.0, ge=0
    )  # 0 = kapalı; konuşma sonrası bu kadar sessizlikte kayıt otomatik durur
    silence_threshold: float = Field(
        default=0.01, ge=0.0, le=1.0
    )  # RMS eşiği: bunun altı sessizlik sayılır


class DictionaryEntry(BaseModel):
    model_config = ConfigDict(frozen=True)
    term: str  # doğru yazım, ör. "Kubernetes"
    wrong: tuple[str, ...] = ()  # STT'nin ürettiği yanlış biçimler, ör. ("kuber netes",)


class DictionarySettings(BaseModel):
    model_config = ConfigDict(frozen=True)
    entries: tuple[DictionaryEntry, ...] = ()
    user_instructions: str = ""  # LLM düzeltme talimatına ek serbest metin


class Settings(BaseModel):
    model_config = ConfigDict(frozen=True)
    hotkey: str = "ctrl+alt+space"
    hotkey_translate: str = ""  # boş = kapalı
    hotkey_prompt: str = ""  # boş = kapalı
    autostart: bool = True
    close_after_copy: bool = False
    history_limit: int = Field(default=200, ge=0)
    # Sonuç teslimi: pano her zaman yedektir, yapıştırma aktif pencereye Ctrl+V gönderir.
    auto_copy: bool = True
    auto_paste: bool = True
    restore_clipboard: bool = False  # yapıştırdıktan sonra panodaki eski içeriği geri yükle
    push_to_talk: bool = True  # Windows: kısayolu basılı tutunca kayıt, bırakınca çözümleme
    raise_window_on_result: bool = False  # dikte akışını bozmamak için varsayılan kapalı
    sounds_enabled: bool = True  # başlat/durdur/hata sesleri
    suggest_dictionary: bool = True  # elle düzenlemeden tek kelimelik sözlük önerisi çıkar
    voice_commands: bool = True  # "yeni satır", "yeni paragraf", "son cümleyi sil"
    stt: SttSettings = SttSettings()
    llm: LlmSettings = LlmSettings()
    audio: AudioSettings = AudioSettings()
    dictionary: DictionarySettings = DictionarySettings()


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
