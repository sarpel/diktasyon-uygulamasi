"""Ayar şeması (değişmez pydantic modelleri) ve `config.json` okuma/yazma.

Yeni alanlar her zaman varsayılan değerle eklenir; eski config dosyaları doğrulamadan
geçmeye devam etmelidir."""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from dikte import paths

log = logging.getLogger(__name__)


HISTORY_LIMIT_MAX = 5000
# `load_settings_with_issues` işaretleri: tüm dosya varsayılana döndü (yedek alındı) /
# dosya hiç okunamadı (yedek alınmadı, dosyaya dokunulmadı).
ALL_DEFAULTS: tuple[str, ...] = ("*",)
UNREADABLE: tuple[str, ...] = ("!",)


class SettingsError(RuntimeError):
    """Ayarlar dosyası yazılamadı; çağıran katman kullanıcıya ne yapacağını söylemeli."""


class SttSettings(BaseModel):
    """Konuşma tanıma (faster-whisper) ayarları; model/compute_type değişimi yeniden yükletir."""

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
    # Kayıt sırasında parça parça çözümleme: 0 = kapalı (tek geçiş, kayıt bitince çözümlenir).
    live_chunk_s: float = Field(default=20.0, ge=0)
    live_max_chunk_s: float = Field(default=45.0, ge=5)


class LlmSettings(BaseModel):
    """LLM düzeltmesi ayarları: sağlayıcı seçimi, sağlayıcı başına model/uç nokta ve örnekleme.

    API anahtarlarının kendisi değil, yalnızca okunacakları ortam değişkeninin adı saklanır."""

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
    openai_model: str = "gpt-5.6-terra"
    openai_base_url: str = "https://api.openai.com/v1"
    openai_api_key_env: str = "OPENAI_API_KEY"
    anthropic_model: str = "claude-sonnet-5"
    anthropic_api_key_env: str = "ANTHROPIC_API_KEY"
    gemini_model: str = "gemini-3.8-flash"
    gemini_api_key_env: str = "GEMINI_API_KEY"
    # Özel uç nokta: OpenAI-uyumlu veya Anthropic-uyumlu iki yaygın formattan biri.
    custom_format: Literal["openai", "anthropic"] = "openai"
    # Kişiye özel uç nokta bilgileri config.json'a yazılır; kod içinde varsayılan tutulmaz.
    custom_base_url: str = ""
    custom_model: str = ""
    custom_api_key_env: str = ""  # boş = anahtar gönderilmez (yerel sunucu)
    timeout_s: float = Field(default=120.0, gt=0)
    think: bool = False  # Qwen3.5 varsayılan olarak düşünür; kapalı tutulur
    num_ctx: int = Field(default=8192, ge=2048)  # KV cache'i küçük tut (VRAM)
    top_p: float = 0.8
    top_k: int = 20
    # Düzeltilmiş metnin kelime sayısı ham metinden çok saparsa (model cevap verdi/özetledi)
    # ham metne dönülür.
    sanity_check: bool = True

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
    """Mikrofon seçimi ve kayıt sınırları; değişiklikler bir sonraki kayıtta geçerli olur."""

    model_config = ConfigDict(frozen=True)
    device_index: int | None = None  # eski config'ler için; device_name önceliklidir
    # Mikrofon adı: PortAudio index'leri USB cihaz takılıp çıkınca kayar, ad kaymaz.
    device_name: str = ""  # boş = device_index'e, o da yoksa sistem varsayılanına bakılır
    # Kayıt başladıktan sonra bu kadar saniye hiç ses gelmezse uyarı; 0 = kapalı.
    dead_mic_warn_s: float = Field(default=3.0, ge=0)
    # STT (faster-whisper) ve başarısız kayıt WAV'ı 16 kHz varsayar; başka değer (ör. elle
    # yazılmış 0 → sıfıra bölme) eski config'ten gelirse yalnızca bu alan varsayılana döner.
    sample_rate: Literal[16000] = 16000
    max_seconds: int = Field(default=0, ge=0)  # 0 = sınırsız
    silence_stop_s: float = Field(
        default=0.0, ge=0
    )  # 0 = kapalı; konuşma sonrası bu kadar sessizlikte kayıt otomatik durur
    silence_threshold: float = Field(
        default=0.01, ge=0.0, le=1.0
    )  # RMS eşiği: bunun altı sessizlik sayılır


class DictionaryEntry(BaseModel):
    """Kullanıcı sözlüğü girdisi: doğru terim ve STT'nin onun yerine ürettiği yanlış biçimler."""

    model_config = ConfigDict(frozen=True)
    term: str  # doğru yazım, ör. "Kubernetes"
    wrong: tuple[str, ...] = ()  # STT'nin ürettiği yanlış biçimler, ör. ("kuber netes",)


class DictionarySettings(BaseModel):
    """Kullanıcı sözlüğü ve LLM düzeltme talimatına eklenen serbest metin."""

    model_config = ConfigDict(frozen=True)
    entries: tuple[DictionaryEntry, ...] = ()
    user_instructions: str = ""  # LLM düzeltme talimatına ek serbest metin


class AppProfile(BaseModel):
    """Ön plandaki uygulamaya (exe adı) göre mod, yapıştırma biçimi ve LLM kullanımını belirler."""

    model_config = ConfigDict(frozen=True)
    name: str
    match: str  # exe adı alt dizesi, küçük harf (ör. "code", "windowsterminal")
    mode: Literal["correct", "translate", "prompt"] = "correct"
    paste: Literal["ctrl+v", "ctrl+shift+v", "type"] = "ctrl+v"
    llm_enabled: bool = True
    trailing: Literal["", " ", "\n"] = ""


class Settings(BaseModel):
    """Tüm uygulama ayarları (`config.json`'un kökü); değişmezdir, `model_copy` ile güncellenir."""

    model_config = ConfigDict(frozen=True)
    hotkey: str = "ctrl+alt+space"
    hotkey_translate: str = ""  # boş = kapalı
    hotkey_prompt: str = ""  # boş = kapalı
    autostart: bool = True
    close_after_copy: bool = False
    history_limit: int = Field(default=200, ge=0)
    history_retention_days: int = Field(default=0, ge=0)  # 0 = süre sınırı yok
    # Sonuç teslimi: pano her zaman yedektir, yapıştırma aktif pencereye Ctrl+V gönderir.
    auto_copy: bool = True
    auto_paste: bool = True
    restore_clipboard: bool = False  # yapıştırdıktan sonra panodaki eski içeriği geri yükle
    push_to_talk: bool = True  # Windows: kısayolu basılı tutunca kayıt, bırakınca çözümleme
    raise_window_on_result: bool = False  # dikte akışını bozmamak için varsayılan kapalı
    sounds_enabled: bool = True  # başlat/durdur/hata sesleri
    suggest_dictionary: bool = True  # elle düzenlemeden tek kelimelik sözlük önerisi çıkar
    voice_commands: bool = True  # "yeni satır", "yeni paragraf", "son cümleyi sil"
    hotkey_paste_last: str = ""  # boş = kapalı; son sonucu yeniden yapıştırır
    pause_media: bool = False  # kayıt sırasında çalan medyayı duraklat
    keep_failed_audio: bool = True  # başarısız diktenin sesini WAV olarak sakla
    overlay_position: Literal["bottom", "top", "custom"] = "bottom"
    overlay_xy: tuple[int, int] | None = None  # "custom" konumda sürüklenen son yer
    # Yapıştırılan metin Windows pano geçmişine/bulut senkronuna girmesin.
    clipboard_exclude_history: bool = True
    stt: SttSettings = SttSettings()
    llm: LlmSettings = LlmSettings()
    audio: AudioSettings = AudioSettings()
    dictionary: DictionarySettings = DictionarySettings()
    profiles: tuple[AppProfile, ...] = ()

    @field_validator("history_limit", mode="before")
    @classmethod
    def _clamp_history_limit(cls, value: Any) -> Any:
        # Her diktede dosya baştan yazılır; sınırsız büyüme GUI'yi yavaşlatır. Eski
        # config'lerdeki büyük değerler reddedilmez, üst sınıra çekilir.
        if isinstance(value, int) and not isinstance(value, bool) and value > HISTORY_LIMIT_MAX:
            return HISTORY_LIMIT_MAX
        return value


def _salvage(model_cls: type[BaseModel], data: dict, prefix: str) -> tuple[dict, list[str]]:
    """`data` içinden geçerli alanları ayıklar; geçersiz olanların yolunu döndürür.

    İç içe bölümler (stt, llm, …) alan alan kurtarılır; liste gibi diğer alanlar bütün
    olarak ya kabul ya da reddedilir. Bilinmeyen anahtarlar pydantic tarafından zaten
    yok sayılır (daha yeni sürümden kalan alanlar sorun çıkarmaz)."""
    kept: dict = {}
    issues: list[str] = []
    for name, field in model_cls.model_fields.items():
        if name not in data:
            continue
        value, path = data[name], f"{prefix}{name}"
        ann = field.annotation
        if isinstance(ann, type) and issubclass(ann, BaseModel) and isinstance(value, dict):
            sub, sub_issues = _salvage(ann, value, f"{path}.")
            kept[name] = sub
            issues.extend(sub_issues)
            continue
        try:
            model_cls.model_validate({name: value})
        except ValidationError:
            issues.append(path)
        else:
            kept[name] = value
    return kept, issues


def _backup(p: Path) -> None:
    backup = p.with_suffix(p.suffix + ".bak")
    try:
        backup.write_bytes(p.read_bytes())
    except OSError:
        log.exception("config yedeği yazılamadı")


def load_settings_with_issues(path: Path | None = None) -> tuple[Settings, tuple[str, ...]]:
    """Ayarları yükler; ikinci değer atlanan (geçersiz) alanların yollarıdır.

    Tek bir hatalı değer (ör. elle düzenlenmiş `beam_size=11`) tüm ayarları sıfırlamaz:
    yalnızca o alan varsayılana döner. Doğrulama başarısızsa orijinal dosya önce
    `config.json.bak`'a kopyalanır. Dosya yoksa `()` ile varsayılanlar döner; `ALL_DEFAULTS`
    = geçerli JSON nesnesi değil ya da kurtarılan alanlar da doğrulanamadı (tümü varsayılan,
    yedek alındı); `UNREADABLE` = dosya okunamadı (`OSError`, yedek alınmadı). Hiçbir
    durumda istisna fırlatmaz."""
    p = path or paths.config_path()
    if not p.exists():
        return Settings(), ()
    try:
        raw = p.read_text(encoding="utf-8")
    except OSError as exc:
        log.warning("config okunamadı (%s), varsayılanlar kullanılıyor", exc)
        return Settings(), UNREADABLE
    try:
        return Settings.model_validate_json(raw), ()
    except (ValidationError, ValueError) as exc:
        log.warning("config doğrulanamadı (%s); geçerli alanlar kurtarılıyor", exc)
    _backup(p)
    try:
        data = json.loads(raw)
    except ValueError:
        return Settings(), ALL_DEFAULTS
    if not isinstance(data, dict):
        return Settings(), ALL_DEFAULTS
    kept, issues = _salvage(Settings, data, "")
    try:
        return Settings.model_validate(kept), tuple(issues)
    except ValidationError:
        log.exception("kurtarılan config de doğrulanamadı; varsayılanlar kullanılıyor")
        return Settings(), ALL_DEFAULTS


def load_settings(path: Path | None = None) -> Settings:
    """`load_settings_with_issues` ile aynı; atlanan alan listesi gerekmeyenler için."""
    return load_settings_with_issues(path)[0]


def save_settings(settings: Settings, path: Path | None = None) -> None:
    """Ayarları atomik olarak yazar (geçici dosya + yeniden adlandırma; POSIX'te 0600).

    Yazılamazsa `SettingsError` fırlatır; mesaj kullanıcıya gösterilmeye uygundur."""
    p = path or paths.config_path()
    tmp = p.with_suffix(".tmp")
    try:
        tmp.write_text(
            json.dumps(settings.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        if sys.platform != "win32":
            # API anahtarı *adları* (değerleri değil) gibi bilgiler burada; yine de çok
            # kullanıcılı bir sistemde başkaları okumasın.
            tmp.chmod(0o600)
        tmp.replace(p)
    except OSError as exc:
        log.exception("config yazılamadı: %s", p)
        raise SettingsError(
            f"Ayarlar kaydedilemedi ({p}): {exc}. Diskte yer olduğunu ve klasöre "
            "yazma izniniz olduğunu kontrol edin."
        ) from exc
