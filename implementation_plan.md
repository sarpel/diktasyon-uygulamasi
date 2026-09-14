# Dikte — Türkçe Diktasyon Uygulaması (Windows 11) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Windows 11'de tray'de sürekli çalışan, tek bir global kısayolla kayıt başlatıp durduran, sesi yerel GPU'da (RTX 3060 Ti, 8 GB) faster-whisper `large-v3-turbo` ile Türkçe metne çeviren, yerel LLM ile hatalı kelimeleri düzelten, ham + düzeltilmiş metni yan yana düzenlenebilir gösteren, tek tıkla kopyalatan ve isteğe bağlı olarak metni İngilizce'ye çeviren veya İngilizce "AI agent prompt"una dönüştüren masaüstü uygulaması.

**Architecture:** Tek bir Python süreci; PySide6 (Qt) ile tray ikonu, kayıt overlay'i ve sonuç penceresi. Win32 `RegisterHotKey` ile global toggle kısayolu. `sounddevice` ile 16 kHz mono ses yakalama, `faster-whisper` (CTranslate2, CUDA) ile STT, `ollama` ile yerel LLM (varsayılan `qwen3.5:4b`, alternatif `gemma4:e4b-it-qat`, isteğe bağlı Anthropic API). Tüm ağır işler `QThreadPool` worker'larında; UI thread'e yalnızca Qt sinyalleriyle dönülür. Durum makinesi tek bir `DictationController` sınıfında toplanır.

**Tech Stack:** Python 3.11 (64-bit), PySide6 ≥ 6.7, sounddevice, numpy, faster-whisper ≥ 1.1, ctranslate2 ≥ 4.5, nvidia-cublas-cu12, nvidia-cudnn-cu12, ollama (python client), anthropic (opsiyonel), pydantic ≥ 2, pytest, pytest-qt, PyInstaller, Inno Setup 6.

**Spec:** Bu dosyanın "Bölüm 0 — Ürün Spesifikasyonu" kısmı. Ayrı bir spec dosyası yoktur; plan spec'i içerir.

## Global Constraints

- Hedef platform: **Windows 11 x64**. Linux/WSL yalnızca geliştirme ve platform-bağımsız birim testleri içindir. Windows'a özel kod (`winreg`, `RegisterHotKey`, `os.add_dll_directory`) `sys.platform == "win32"` koşuluyla korunur; diğer platformlarda import hatası vermez.
- Python **3.11.x**. Paket yöneticisi: `uv` (yoksa `pip` + `venv`).
- Ses formatı: **16000 Hz, mono, float32** (Whisper'ın beklediği format; yeniden örnekleme yapılmaz).
- STT modeli: `large-v3-turbo` (faster-whisper ≥ 1.1 model adı; CTranslate2 dönüşümü HF'den `deepdml/faster-whisper-large-v3-turbo-ct2` olarak iner). `device="cuda"`, `compute_type="float16"`. VRAM bütçesi: Whisper ≈ 1.6 GB + LLM 4B Q4 ≈ 3.4–4.5 GB + KV cache < 8 GB.
- LLM varsayılanı: Ollama, model `qwen3.5:4b` (Q4_K_M ≈ 3.4 GB, 201 dil, Apache-2.0), **thinking kapalı** (`think=False`). İkinci aday: `gemma4:e4b-it-qat` (≈ 4.5 GB VRAM + PLE tabloları RAM'de). Seçim Task 13'teki Türkçe A/B betiğiyle doğrulanır. `keep_alive="30m"`. Bkz. Bölüm 0.6.
- Varsayılan global kısayol: **Ctrl+Alt+Space** (toggle). Ayarlardan değiştirilebilir.
- Uygulama adı: **Dikte**. Python paketi: `dikte`. Kullanıcı verileri: `%APPDATA%\Dikte\` (config, history), `%LOCALAPPDATA%\Dikte\models\` (model önbelleği).
- "Servis" gereksinimi: Windows Service (Session 0) UI gösteremez; bu yüzden uygulama **oturum açılışında otomatik başlayan, tek örnek (single-instance) tray uygulaması** olarak yapılır (HKCU Run kaydı). Pencere kapatma = tray'e küçültme; çıkış yalnızca tray menüsünden.
- Gizli bilgi kaynak koda yazılmaz. `ANTHROPIC_API_KEY` yalnızca ortam değişkeninden okunur.
- Immutable veri: `@dataclass(frozen=True)` / pydantic modelleri; state güncellemeleri yeni nesne döndürür.
- Test: `pytest`; GPU gerektiren testler `@pytest.mark.gpu` ile işaretlenir, CUDA yoksa atlanır. Qt testleri `QT_QPA_PLATFORM=offscreen` ile çalışır. Hedef kapsam: Windows'a özel ve GPU'ya bağlı modüller dışında ≥ 80 %.
- Her task sonunda commit. Conventional Commits (`feat:`, `fix:`, `test:`, `chore:`).

---

## Bölüm 0 — Ürün Spesifikasyonu

### 0.1 Kullanıcı akışı

1. Uygulama Windows oturumu ile başlar, tray'de ikon görünür. Whisper modeli arka planda GPU'ya yüklenir (warm-up); tray tooltip'i "Hazır" olunca hazırdır.
2. Kullanıcı **Ctrl+Alt+Space** basar → kayıt başlar. Ekranın alt-ortasında küçük, çerçevesiz, her zaman üstte bir **overlay** açılır: sesle uyumlu dalga formu animasyonu + **kırmızı yanıp sönen kayıt noktası** + geçen süre.
3. Kullanıcı tekrar **Ctrl+Alt+Space** basar → kayıt durur, overlay "Yazıya dökülüyor…" gösterir, STT çalışır (Türkçe), ardından LLM düzeltmesi çalışır ("Düzeltiliyor…").
4. **Sonuç penceresi** açılır: sol pane **Ham** metin, sağ pane **Düzeltilmiş** metin; ikisi de düzenlenebilir. Her pane'in sağ üstünde **kopyala** ikonu. Düzeltilmiş metnin altında LLM'in yaptığı değişiklik listesi (from → to).
5. Alt araç çubuğu: **"İngilizce'ye Çevir"** (düzeltilmiş pane içeriğini İngilizce'ye çevirir, üçüncü pane'de gösterir) ve **"Agent Prompt'a Dönüştür"** (düzeltilmiş pane içeriğini İngilizce, AI agent'lar için optimize edilmiş yapılandırılmış prompt'a dönüştürür, üçüncü pane'de gösterir; kopyala ikonu vardır).
6. Kopyalanınca kısa "Kopyalandı" toast'ı görünür. Pencere kapatılınca tray'e döner; geçmiş JSONL'e yazılır.

### 0.2 Kısayol toggle durum makinesi

```
IDLE --hotkey--> RECORDING --hotkey--> TRANSCRIBING --auto--> CORRECTING --auto--> RESULT --hotkey--> RECORDING
TRANSCRIBING/CORRECTING sırasında hotkey yok sayılır. Herhangi bir hata -> RESULT (ham metin varsa) veya IDLE (+ tray bildirimi).
```

### 0.3 LLM görevleri

| Görev | Girdi | Çıktı | Format |
|---|---|---|---|
| `correct` | Ham Türkçe transkript | Düzeltilmiş Türkçe metin + değişiklik listesi | JSON şeması |
| `translate` | Türkçe metin | İngilizce çeviri | Düz metin |
| `enhance_prompt` | Türkçe (veya İngilizce) istek | İngilizce, agent'a yönelik yapılandırılmış prompt (Goal / Context / Requirements / Constraints / Output format) | Markdown düz metin |

### 0.4 Ayarlar

Kısayol, mikrofon cihazı, STT modeli adı ve compute_type, dil (`tr` varsayılan), LLM sağlayıcı (`ollama` / `anthropic`), LLM model adı, Ollama host, otomatik başlatma (açık/kapalı), "kopyalama sonrası pencereyi kapat" (kapalı varsayılan), geçmiş uzunluğu.

### 0.5 LLM model seçimi (Eylül 2026 araştırması)

VRAM bütçesi: 8 GB − Whisper large-v3-turbo fp16 (≈ 1.6 GB) − masaüstü (≈ 0.5 GB) ⇒ LLM için ≈ 5.5–6 GB.

| Model (Ollama etiketi) | Dosya | VRAM tahmini | Sığar mı? | Çok dillilik | Not |
|---|---|---|---|---|---|
| `qwen3.5:4b` (varsayılan) | 3.4 GB | ≈ 3.8 GB + KV | Evet | 201 dil; MMMLU 76.1; WMT24++ 66.6 | Thinking varsayılan açık → `think=False` zorunlu |
| `gemma4:e4b-it-qat` (alternatif) | 6.1 GB | ≈ 4.5 GB VRAM, PLE tabloları RAM | Evet | 140+ dil; MMMLU 76.6 | QAT, kalite kaybı az; thinking varsayılan kapalı |
| `qwen3.5:9b` | 6.6 GB | ≈ 7 GB | Hayır (CPU offload, yavaş) | MMMLU 81.2; WMT24++ 72.6 | Whisper `int8_float16` ile bile sınırda |
| `gemma4:12b-it-qat` | 7.2 GB | ≈ 7.5 GB | Hayır | MMMLU 83.4 | 12 GB+ kartta tercih |
| Qwen3.6 / Qwen3.8 | 17 GB+ | — | Hayır | — | Küçük (≤ 9B) varyantı yok; yalnızca bulut |

Kurallar:
- Qwen3.5 için Ollama `chat(..., think=False)` ve non-thinking örnekleme (`temperature=0.7, top_p=0.8, top_k=20, presence_penalty=1.5`) resmi öneri; düzeltme görevinde `temperature` 0.3'e çekilir.
- Gemma 4 için thinking yalnızca sistem promptunun başına `<|think|>` konursa açılır; biz koymayız. Resmi örnekleme `temperature=1.0, top_p=0.95, top_k=64`; düzeltme görevinde 0.3.
- Nihai seçim Task 13'teki `scripts/eval_llm.py` Türkçe A/B testiyle yapılır (10 STT-hatalı cümle, iki modelin JSON düzeltme çıktısı yan yana, süre ölçümü).

### 0.6 Kapsam dışı (YAGNI)

Gerçek zamanlı akış transkripsiyon, çoklu dil otomatik algılama UI'si, bulut senkronizasyonu, otomatik güncelleme, Windows Service kurulumu.

---

## Bölüm 1 — Dosya Yapısı

```
dictation-app/
├── pyproject.toml
├── README.md
├── implementation_plan.md
├── src/dikte/
│   ├── __init__.py               # __version__
│   ├── __main__.py               # python -m dikte
│   ├── app.py                    # QApplication kurulumu, composition root
│   ├── paths.py                  # APPDATA/LOCALAPPDATA yolları
│   ├── config.py                 # pydantic Settings + load/save
│   ├── logging_setup.py          # dosya + konsol logger
│   ├── cuda_dlls.py              # Windows'ta nvidia wheel DLL dizinlerini ekle
│   ├── audio/
│   │   ├── __init__.py
│   │   ├── recorder.py           # AudioRecorder (sounddevice) + level sinyali
│   │   └── levels.py             # RMS / peak hesaplama (saf numpy, test edilebilir)
│   ├── stt/
│   │   ├── __init__.py
│   │   ├── engine.py             # SttEngine protokolü + FasterWhisperEngine
│   │   └── result.py             # TranscriptResult dataclass
│   ├── llm/
│   │   ├── __init__.py
│   │   ├── provider.py           # LlmProvider protokolü, LlmError
│   │   ├── ollama_provider.py
│   │   ├── anthropic_provider.py
│   │   ├── prompts.py            # sistem/kullanıcı prompt şablonları
│   │   └── tasks.py              # correct / translate / enhance_prompt fonksiyonları
│   ├── core/
│   │   ├── __init__.py
│   │   ├── state.py              # DictationState enum + Session dataclass
│   │   ├── controller.py         # DictationController (durum makinesi, worker orkestrasyonu)
│   │   ├── workers.py            # QRunnable sarmalayıcıları
│   │   └── history.py            # JSONL geçmiş
│   ├── platform/
│   │   ├── __init__.py
│   │   ├── hotkey.py             # Win32 RegisterHotKey + QAbstractNativeEventFilter
│   │   ├── hotkey_parse.py       # "ctrl+alt+space" -> (modifiers, vk) (saf, test edilebilir)
│   │   ├── autostart.py          # HKCU Run kaydı
│   │   └── single_instance.py    # QLocalServer kilidi
│   └── ui/
│       ├── __init__.py
│       ├── tray.py               # QSystemTrayIcon + menü
│       ├── overlay.py            # Kayıt overlay'i (dalga formu + kırmızı nokta)
│       ├── waveform.py           # WaveformWidget (QPainter)
│       ├── result_window.py      # Ham / Düzeltilmiş / Prompt pane'leri
│       ├── text_pane.py          # Başlık + kopyala butonu + QPlainTextEdit
│       ├── settings_dialog.py
│       ├── toast.py
│       └── icons.py              # QIcon üretimi (QPainter ile çizilen basit ikonlar)
├── tests/
│   ├── conftest.py
│   ├── test_config.py
│   ├── test_levels.py
│   ├── test_recorder.py
│   ├── test_stt_engine.py
│   ├── test_llm_tasks.py
│   ├── test_ollama_provider.py
│   ├── test_controller.py
│   ├── test_history.py
│   ├── test_hotkey_parse.py
│   ├── test_autostart.py
│   ├── test_ui_text_pane.py
│   ├── test_ui_result_window.py
│   ├── test_ui_waveform.py
│   └── test_settings_dialog.py
├── packaging/
│   ├── dikte.spec                # PyInstaller
│   ├── installer.iss             # Inno Setup
│   └── build.ps1
└── docs/
    └── manual_test_checklist.md
```

---

## Bölüm 2 — Görevler

### Task 1: Proje iskeleti, yollar, config, logging

**Files:**
- Create: `pyproject.toml`, `src/dikte/__init__.py`, `src/dikte/__main__.py`, `src/dikte/paths.py`, `src/dikte/config.py`, `src/dikte/logging_setup.py`, `tests/conftest.py`, `tests/test_config.py`, `.gitignore`, `README.md`

**Interfaces:**
- Produces: `paths.app_data_dir() -> Path`, `paths.models_dir() -> Path`, `config.Settings` (pydantic BaseModel, frozen), `config.load_settings(path: Path | None = None) -> Settings`, `config.save_settings(settings: Settings, path: Path | None = None) -> None`, `logging_setup.setup_logging(level: str = "INFO") -> None`.

- [x] **Step 1: pyproject.toml yaz**

```toml
[project]
name = "dikte"
version = "0.1.0"
description = "Türkçe odaklı, GPU destekli yerel diktasyon uygulaması (Windows 11)"
requires-python = ">=3.11,<3.13"
dependencies = [
  "PySide6>=6.7",
  "sounddevice>=0.5",
  "numpy>=1.26",
  "faster-whisper>=1.1.0",
  "ctranslate2>=4.5",
  "ollama>=0.4",
  "pydantic>=2.7",
  "anthropic>=0.40; extra == 'anthropic'",
]

[project.optional-dependencies]
cuda = ["nvidia-cublas-cu12", "nvidia-cudnn-cu12>=9"]
anthropic = ["anthropic>=0.40"]
dev = ["pytest>=8", "pytest-qt>=4.4", "pytest-cov>=5", "ruff>=0.5", "pyinstaller>=6.6"]

[project.scripts]
dikte = "dikte.app:main"

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
markers = ["gpu: CUDA gerektirir", "win: yalnızca Windows"]
addopts = "-q"

[tool.ruff]
line-length = 100
target-version = "py311"
```

- [x] **Step 2: Ortamı kur**

```bash
uv venv --python 3.11 .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
uv pip install -e ".[dev]"
```
Windows'ta ek olarak: `uv pip install -e ".[dev,cuda]"`.

- [x] **Step 3: `.gitignore` ve git init**

```
.venv/
__pycache__/
*.pyc
dist/
build/
*.spec.bak
.pytest_cache/
.coverage
htmlcov/
.remember/
```
```bash
git init && git add -A && git commit -m "chore: project skeleton"
```

- [x] **Step 4: Başarısız config testini yaz** — `tests/test_config.py`

```python
from pathlib import Path
from dikte.config import Settings, load_settings, save_settings


def test_default_settings_values():
    s = Settings()
    assert s.hotkey == "ctrl+alt+space"
    assert s.stt.model == "large-v3-turbo"
    assert s.stt.language == "tr"
    assert s.llm.provider == "ollama"
    assert s.llm.model == "qwen3.5:4b"
    assert s.llm.think is False


def test_settings_are_immutable():
    s = Settings()
    import pytest
    with pytest.raises(Exception):
        s.hotkey = "ctrl+shift+d"  # type: ignore[misc]


def test_save_and_load_roundtrip(tmp_path: Path):
    p = tmp_path / "config.json"
    s = Settings().model_copy(update={"hotkey": "ctrl+shift+d"})
    save_settings(s, p)
    assert load_settings(p) == s


def test_load_missing_file_returns_defaults(tmp_path: Path):
    assert load_settings(tmp_path / "nope.json") == Settings()


def test_load_corrupt_file_returns_defaults_and_backs_up(tmp_path: Path):
    p = tmp_path / "config.json"
    p.write_text("{not json", encoding="utf-8")
    assert load_settings(p) == Settings()
    assert (tmp_path / "config.json.bak").exists()
```

- [x] **Step 5: Testi çalıştır, başarısız olduğunu gör**

Run: `pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: dikte.config`

- [x] **Step 6: `src/dikte/__init__.py`, `paths.py`, `config.py`, `logging_setup.py` yaz**

`src/dikte/__init__.py`:
```python
__version__ = "0.1.0"
APP_NAME = "Dikte"
```

`src/dikte/paths.py`:
```python
import os
import sys
from pathlib import Path

from dikte import APP_NAME


def _base(env_var: str, fallback: str) -> Path:
    if sys.platform == "win32" and (val := os.environ.get(env_var)):
        return Path(val)
    return Path.home() / fallback


def app_data_dir() -> Path:
    d = _base("APPDATA", ".config") / APP_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def models_dir() -> Path:
    d = _base("LOCALAPPDATA", ".cache") / APP_NAME / "models"
    d.mkdir(parents=True, exist_ok=True)
    return d


def config_path() -> Path:
    return app_data_dir() / "config.json"


def history_path() -> Path:
    return app_data_dir() / "history.jsonl"


def log_path() -> Path:
    return app_data_dir() / "dikte.log"
```

`src/dikte/config.py`:
```python
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
    device: Literal["cuda", "cpu"] = "cuda"
    compute_type: str = "float16"
    language: str = "tr"
    beam_size: int = Field(default=5, ge=1, le=10)
    vad_filter: bool = True
    initial_prompt: str = "Türkçe konuşma. Noktalama işaretleri kullanılır."


class LlmSettings(BaseModel):
    model_config = ConfigDict(frozen=True)
    provider: Literal["ollama", "anthropic"] = "ollama"
    model: str = "qwen3.5:4b"
    ollama_host: str = "http://127.0.0.1:11434"
    anthropic_model: str = "claude-sonnet-5"
    keep_alive: str = "30m"
    timeout_s: float = Field(default=120.0, gt=0)
    think: bool = False          # Qwen3.5 varsayılan olarak düşünür; kapalı tutulur
    num_ctx: int = Field(default=8192, ge=2048)  # KV cache'i küçük tut (VRAM)
    top_p: float = 0.8
    top_k: int = 20


class AudioSettings(BaseModel):
    model_config = ConfigDict(frozen=True)
    device_index: int | None = None  # None = sistem varsayılanı
    sample_rate: int = 16000
    max_seconds: int = Field(default=600, ge=5)


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
    tmp.write_text(json.dumps(settings.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(p)
```

`src/dikte/logging_setup.py`:
```python
import logging
import logging.handlers
import sys

from dikte import paths


def setup_logging(level: str = "INFO") -> None:
    fmt = "%(asctime)s %(levelname)s %(name)s: %(message)s"
    root = logging.getLogger()
    root.setLevel(level)
    if root.handlers:
        return
    fh = logging.handlers.RotatingFileHandler(
        paths.log_path(), maxBytes=2_000_000, backupCount=3, encoding="utf-8"
    )
    fh.setFormatter(logging.Formatter(fmt))
    root.addHandler(fh)
    if sys.stderr:
        sh = logging.StreamHandler(sys.stderr)
        sh.setFormatter(logging.Formatter(fmt))
        root.addHandler(sh)
```

`src/dikte/__main__.py`:
```python
from dikte.app import main

if __name__ == "__main__":
    raise SystemExit(main())
```

`tests/conftest.py`:
```python
import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _has_cuda() -> bool:
    try:
        import ctranslate2
        return ctranslate2.get_cuda_device_count() > 0
    except Exception:
        return False


def pytest_runtest_setup(item):
    if "gpu" in item.keywords and not _has_cuda():
        pytest.skip("CUDA yok")
    if "win" in item.keywords and sys.platform != "win32":
        pytest.skip("yalnızca Windows")
```

- [x] **Step 7: Testleri çalıştır, geçtiğini gör**

Run: `pytest tests/test_config.py -v`
Expected: 5 PASS

- [x] **Step 8: Commit**

```bash
git add -A && git commit -m "feat: settings model, paths and logging"
```

---

### Task 2: Ses seviyesi hesaplama ve AudioRecorder

**Files:**
- Create: `src/dikte/audio/__init__.py`, `src/dikte/audio/levels.py`, `src/dikte/audio/recorder.py`
- Test: `tests/test_levels.py`, `tests/test_recorder.py`

**Interfaces:**
- Consumes: `Settings.audio` (Task 1).
- Produces: `levels.rms(frame: np.ndarray) -> float` (0..1), `levels.bucketize(frame: np.ndarray, buckets: int) -> tuple[float, ...]`, `AudioRecorder(QObject)` — sinyaller `level_changed(float)`, `buckets_changed(object)` (tuple[float,...]), `error(str)`; metotlar `start() -> None`, `stop() -> np.ndarray` (float32, mono, 16 kHz), `is_recording -> bool`. Yapıcı `AudioRecorder(settings: AudioSettings, stream_factory=None)`; `stream_factory` test için enjekte edilir.

- [x] **Step 1: Başarısız `levels` testini yaz** — `tests/test_levels.py`

```python
import numpy as np
from dikte.audio.levels import rms, bucketize


def test_rms_of_silence_is_zero():
    assert rms(np.zeros(1600, dtype=np.float32)) == 0.0


def test_rms_of_full_scale_sine_is_about_0_7():
    t = np.linspace(0, 1, 16000, dtype=np.float32)
    assert abs(rms(np.sin(2 * np.pi * 440 * t)) - 0.707) < 0.01


def test_rms_is_clamped_to_one():
    assert rms(np.full(100, 5.0, dtype=np.float32)) == 1.0


def test_bucketize_returns_requested_count():
    frame = np.random.default_rng(0).standard_normal(1600).astype(np.float32) * 0.1
    b = bucketize(frame, 32)
    assert len(b) == 32 and all(0.0 <= v <= 1.0 for v in b)


def test_bucketize_empty_frame_returns_zeros():
    assert bucketize(np.zeros(0, dtype=np.float32), 8) == (0.0,) * 8
```

- [x] **Step 2: Çalıştır, FAIL gör** — `pytest tests/test_levels.py -v` → `ModuleNotFoundError`

- [x] **Step 3: `levels.py` yaz**

```python
import numpy as np


def rms(frame: np.ndarray) -> float:
    if frame.size == 0:
        return 0.0
    val = float(np.sqrt(np.mean(np.square(frame, dtype=np.float64))))
    return min(1.0, val)


def bucketize(frame: np.ndarray, buckets: int) -> tuple[float, ...]:
    if frame.size == 0 or buckets <= 0:
        return (0.0,) * max(buckets, 0)
    chunks = np.array_split(frame, buckets)
    return tuple(min(1.0, float(np.max(np.abs(c)))) if c.size else 0.0 for c in chunks)
```

- [x] **Step 4: Çalıştır, PASS gör** — `pytest tests/test_levels.py -v`

- [x] **Step 5: Başarısız recorder testini yaz** — `tests/test_recorder.py`

```python
import numpy as np
import pytest
from dikte.audio.recorder import AudioRecorder
from dikte.config import AudioSettings


class FakeStream:
    """sounddevice.InputStream taklidi: start() sonrası callback'i elle tetikleriz."""
    instances: list["FakeStream"] = []

    def __init__(self, *, callback, samplerate, channels, dtype, device, blocksize):
        self.callback = callback
        self.samplerate, self.channels, self.dtype, self.device = samplerate, channels, dtype, device
        self.started = self.stopped = self.closed = False
        FakeStream.instances.append(self)

    def start(self): self.started = True
    def stop(self): self.stopped = True
    def close(self): self.closed = True

    def push(self, frame: np.ndarray):
        self.callback(frame.reshape(-1, 1), len(frame), None, None)


@pytest.fixture
def rec(qtbot):
    FakeStream.instances.clear()
    r = AudioRecorder(AudioSettings(), stream_factory=FakeStream)
    return r


def test_start_opens_16k_mono_float32_stream(rec):
    rec.start()
    s = FakeStream.instances[-1]
    assert (s.samplerate, s.channels, s.dtype, s.started) == (16000, 1, "float32", True)
    assert rec.is_recording


def test_stop_returns_concatenated_audio(rec):
    rec.start()
    s = FakeStream.instances[-1]
    s.push(np.ones(1600, dtype=np.float32) * 0.5)
    s.push(np.ones(800, dtype=np.float32) * -0.5)
    audio = rec.stop()
    assert audio.dtype == np.float32 and audio.shape == (2400,)
    assert s.stopped and s.closed and not rec.is_recording


def test_level_signal_emitted_per_frame(rec, qtbot):
    rec.start()
    with qtbot.waitSignal(rec.level_changed, timeout=1000) as blocker:
        FakeStream.instances[-1].push(np.ones(1600, dtype=np.float32) * 0.5)
    assert abs(blocker.args[0] - 0.5) < 1e-6


def test_stop_without_start_returns_empty(rec):
    assert rec.stop().shape == (0,)


def test_max_seconds_truncates(rec):
    rec = AudioRecorder(AudioSettings(max_seconds=5), stream_factory=FakeStream)
    rec.start()
    s = FakeStream.instances[-1]
    for _ in range(70):  # 70 * 1600 = 112000 örnek = 7 s
        s.push(np.zeros(1600, dtype=np.float32))
    assert rec.stop().shape[0] == 5 * 16000
```

- [x] **Step 6: Çalıştır, FAIL gör** — `pytest tests/test_recorder.py -v`

- [x] **Step 7: `recorder.py` yaz**

```python
from __future__ import annotations

import logging
import threading
from typing import Callable

import numpy as np
from PySide6.QtCore import QObject, Signal

from dikte.audio.levels import bucketize, rms
from dikte.config import AudioSettings

log = logging.getLogger(__name__)
BLOCK_SIZE = 1600  # 100 ms @ 16 kHz
BUCKETS = 32


def _default_stream_factory(**kwargs):
    import sounddevice as sd
    return sd.InputStream(**kwargs)


class AudioRecorder(QObject):
    level_changed = Signal(float)
    buckets_changed = Signal(object)
    error = Signal(str)

    def __init__(self, settings: AudioSettings, stream_factory: Callable | None = None, parent=None):
        super().__init__(parent)
        self._settings = settings
        self._factory = stream_factory or _default_stream_factory
        self._stream = None
        self._chunks: list[np.ndarray] = []
        self._total = 0
        self._lock = threading.Lock()

    @property
    def is_recording(self) -> bool:
        return self._stream is not None

    def start(self) -> None:
        if self._stream is not None:
            return
        self._chunks, self._total = [], 0
        try:
            self._stream = self._factory(
                callback=self._on_audio,
                samplerate=self._settings.sample_rate,
                channels=1,
                dtype="float32",
                device=self._settings.device_index,
                blocksize=BLOCK_SIZE,
            )
            self._stream.start()
        except Exception as exc:  # sounddevice.PortAudioError vb.
            self._stream = None
            log.exception("mikrofon açılamadı")
            self.error.emit(f"Mikrofon açılamadı: {exc}")

    def stop(self) -> np.ndarray:
        stream, self._stream = self._stream, None
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception:
                log.exception("stream kapatılırken hata")
        with self._lock:
            chunks, self._chunks = self._chunks, []
        if not chunks:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(chunks).astype(np.float32, copy=False)

    def _on_audio(self, indata, frames, time_info, status) -> None:
        if status:
            log.warning("audio status: %s", status)
        frame = np.asarray(indata, dtype=np.float32).reshape(-1)
        limit = self._settings.max_seconds * self._settings.sample_rate
        with self._lock:
            room = limit - self._total
            if room <= 0:
                return
            frame = frame[:room].copy()
            self._chunks.append(frame)
            self._total += frame.shape[0]
        self.level_changed.emit(rms(frame))
        self.buckets_changed.emit(bucketize(frame, BUCKETS))
```

- [x] **Step 8: Çalıştır, PASS gör** — `pytest tests/test_recorder.py tests/test_levels.py -v`

- [x] **Step 9: Commit** — `git add -A && git commit -m "feat: audio recorder with level signals"`

---

### Task 3: STT motoru (faster-whisper sarmalayıcı)

**Files:**
- Create: `src/dikte/stt/__init__.py`, `src/dikte/stt/result.py`, `src/dikte/stt/engine.py`, `src/dikte/cuda_dlls.py`
- Test: `tests/test_stt_engine.py`

**Interfaces:**
- Consumes: `SttSettings` (Task 1).
- Produces: `TranscriptResult(text: str, language: str, duration_s: float, segments: tuple[Segment, ...])`, `Segment(start: float, end: float, text: str)`, `SttEngine` Protocol: `load() -> None`, `is_loaded -> bool`, `transcribe(audio: np.ndarray, language: str | None = None) -> TranscriptResult`. `FasterWhisperEngine(settings: SttSettings, model_factory=None)`. `SttError(Exception)`. `cuda_dlls.register_nvidia_dll_dirs() -> list[str]`.

- [x] **Step 1: Başarısız testi yaz** — `tests/test_stt_engine.py`

```python
from types import SimpleNamespace

import numpy as np
import pytest
from dikte.config import SttSettings
from dikte.stt.engine import FasterWhisperEngine, SttError
from dikte.stt.result import TranscriptResult


class FakeModel:
    def __init__(self, *args, **kwargs):
        self.init_args, self.init_kwargs = args, kwargs
        self.calls = []

    def transcribe(self, audio, **kwargs):
        self.calls.append(kwargs)
        segs = [SimpleNamespace(start=0.0, end=1.2, text=" merhaba"),
                SimpleNamespace(start=1.2, end=2.0, text=" dünya")]
        info = SimpleNamespace(language="tr", duration=2.0)
        return iter(segs), info


def make_engine():
    created = {}
    def factory(*a, **kw):
        m = FakeModel(*a, **kw)
        created["model"] = m
        return m
    return FasterWhisperEngine(SttSettings(), model_factory=factory), created


def test_load_creates_model_with_settings():
    eng, created = make_engine()
    assert not eng.is_loaded
    eng.load()
    m = created["model"]
    assert m.init_args[0] == "large-v3-turbo"
    assert m.init_kwargs["device"] == "cuda" and m.init_kwargs["compute_type"] == "float16"
    assert eng.is_loaded


def test_transcribe_joins_segments_and_strips():
    eng, created = make_engine()
    eng.load()
    res = eng.transcribe(np.zeros(16000, dtype=np.float32))
    assert isinstance(res, TranscriptResult)
    assert res.text == "merhaba dünya" and res.language == "tr"
    assert len(res.segments) == 2 and res.segments[0].text == "merhaba"
    kw = created["model"].calls[0]
    assert kw["language"] == "tr" and kw["vad_filter"] is True and kw["beam_size"] == 5


def test_transcribe_autoloads():
    eng, _ = make_engine()
    assert eng.transcribe(np.zeros(16000, dtype=np.float32)).text == "merhaba dünya"


def test_transcribe_empty_audio_raises():
    eng, _ = make_engine()
    with pytest.raises(SttError):
        eng.transcribe(np.zeros(0, dtype=np.float32))


def test_load_failure_wraps_error():
    def bad_factory(*a, **kw):
        raise RuntimeError("CUDA yok")
    eng = FasterWhisperEngine(SttSettings(), model_factory=bad_factory)
    with pytest.raises(SttError, match="CUDA yok"):
        eng.load()


@pytest.mark.gpu
def test_real_model_transcribes_silence_without_crash():
    eng = FasterWhisperEngine(SttSettings())
    eng.load()
    res = eng.transcribe(np.zeros(16000, dtype=np.float32))
    assert isinstance(res.text, str)
```

- [x] **Step 2: Çalıştır, FAIL gör** — `pytest tests/test_stt_engine.py -v`

- [x] **Step 3: `result.py`, `engine.py`, `cuda_dlls.py` yaz**

`src/dikte/stt/result.py`:
```python
from dataclasses import dataclass


@dataclass(frozen=True)
class Segment:
    start: float
    end: float
    text: str


@dataclass(frozen=True)
class TranscriptResult:
    text: str
    language: str
    duration_s: float
    segments: tuple[Segment, ...]
```

`src/dikte/cuda_dlls.py`:
```python
"""pip ile kurulan nvidia-cublas-cu12 / nvidia-cudnn-cu12 wheel'lerinin DLL'lerini
Windows'ta ctranslate2'nin bulabilmesi için DLL arama yoluna ekler."""
import importlib.util
import logging
import os
import sys
from pathlib import Path

log = logging.getLogger(__name__)
_PACKAGES = ("nvidia.cublas", "nvidia.cudnn")


def register_nvidia_dll_dirs() -> list[str]:
    if sys.platform != "win32":
        return []
    added: list[str] = []
    for pkg in _PACKAGES:
        spec = importlib.util.find_spec(pkg)
        if spec is None or not spec.submodule_search_locations:
            continue
        bin_dir = Path(next(iter(spec.submodule_search_locations))) / "bin"
        if bin_dir.is_dir():
            os.add_dll_directory(str(bin_dir))
            os.environ["PATH"] = f"{bin_dir};{os.environ.get('PATH', '')}"
            added.append(str(bin_dir))
    log.info("NVIDIA DLL dizinleri: %s", added)
    return added
```

`src/dikte/stt/engine.py`:
```python
from __future__ import annotations

import logging
import threading
from typing import Callable, Protocol

import numpy as np

from dikte import paths
from dikte.config import SttSettings
from dikte.stt.result import Segment, TranscriptResult

log = logging.getLogger(__name__)


class SttError(Exception):
    pass


class SttEngine(Protocol):
    @property
    def is_loaded(self) -> bool: ...
    def load(self) -> None: ...
    def transcribe(self, audio: np.ndarray, language: str | None = None) -> TranscriptResult: ...


def _default_model_factory(*args, **kwargs):
    from dikte.cuda_dlls import register_nvidia_dll_dirs
    register_nvidia_dll_dirs()
    from faster_whisper import WhisperModel
    return WhisperModel(*args, **kwargs)


class FasterWhisperEngine:
    def __init__(self, settings: SttSettings, model_factory: Callable | None = None):
        self._settings = settings
        self._factory = model_factory or _default_model_factory
        self._model = None
        self._lock = threading.Lock()

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    def load(self) -> None:
        with self._lock:
            if self._model is not None:
                return
            try:
                self._model = self._factory(
                    self._settings.model,
                    device=self._settings.device,
                    compute_type=self._settings.compute_type,
                    download_root=str(paths.models_dir()),
                )
            except Exception as exc:
                raise SttError(f"STT modeli yüklenemedi: {exc}") from exc
        log.info("STT modeli yüklendi: %s (%s/%s)", self._settings.model,
                 self._settings.device, self._settings.compute_type)

    def transcribe(self, audio: np.ndarray, language: str | None = None) -> TranscriptResult:
        if audio.size == 0:
            raise SttError("Ses kaydı boş")
        if not self.is_loaded:
            self.load()
        lang = language or self._settings.language
        try:
            with self._lock:
                seg_iter, info = self._model.transcribe(
                    audio.astype(np.float32, copy=False),
                    language=lang,
                    task="transcribe",
                    beam_size=self._settings.beam_size,
                    vad_filter=self._settings.vad_filter,
                    initial_prompt=self._settings.initial_prompt or None,
                    condition_on_previous_text=True,
                )
                segments = tuple(Segment(s.start, s.end, s.text.strip()) for s in seg_iter)
        except Exception as exc:
            raise SttError(f"Transkripsiyon hatası: {exc}") from exc
        text = " ".join(s.text for s in segments if s.text).strip()
        return TranscriptResult(text=text, language=info.language,
                                duration_s=float(info.duration), segments=segments)
```

- [x] **Step 4: Çalıştır, PASS gör** — `pytest tests/test_stt_engine.py -v` (gpu testi Linux'ta skip)

- [x] **Step 5: Commit** — `git add -A && git commit -m "feat: faster-whisper STT engine wrapper"`

---

### Task 4: LLM sağlayıcıları ve görevler (correct / translate / enhance_prompt)

**Files:**
- Create: `src/dikte/llm/__init__.py`, `src/dikte/llm/provider.py`, `src/dikte/llm/ollama_provider.py`, `src/dikte/llm/anthropic_provider.py`, `src/dikte/llm/prompts.py`, `src/dikte/llm/tasks.py`
- Test: `tests/test_llm_tasks.py`, `tests/test_ollama_provider.py`

**Interfaces:**
- Consumes: `LlmSettings` (Task 1).
- Produces: `LlmProvider` Protocol: `complete(system: str, user: str, *, json_schema: dict | None = None, temperature: float = 0.2) -> str`, `name -> str`. `LlmError(Exception)`. `OllamaProvider(settings, client_factory=None)`, `AnthropicProvider(settings, client_factory=None)`, `make_provider(settings: LlmSettings) -> LlmProvider`. `tasks.CorrectionResult(corrected_text: str, changes: tuple[Change, ...])`, `Change(original: str, replacement: str, reason: str)`, `tasks.correct(provider, raw: str) -> CorrectionResult`, `tasks.translate(provider, text: str) -> str`, `tasks.enhance_prompt(provider, text: str) -> str`.

- [x] **Step 1: Başarısız `tasks` testini yaz** — `tests/test_llm_tasks.py`

```python
import json
import pytest
from dikte.llm.provider import LlmError
from dikte.llm.tasks import CorrectionResult, correct, translate, enhance_prompt


class FakeProvider:
    name = "fake"
    def __init__(self, reply): self.reply, self.calls = reply, []
    def complete(self, system, user, *, json_schema=None, temperature=0.2):
        self.calls.append({"system": system, "user": user, "json_schema": json_schema})
        return self.reply


def test_correct_parses_json_reply():
    p = FakeProvider(json.dumps({
        "corrected_text": "Bugün hava çok güzel.",
        "changes": [{"original": "hava çuk", "replacement": "hava çok", "reason": "yazım"}],
    }))
    res = correct(p, "bugün hava çuk güzel")
    assert isinstance(res, CorrectionResult)
    assert res.corrected_text == "Bugün hava çok güzel."
    assert res.changes[0].replacement == "hava çok"
    assert p.calls[0]["json_schema"] is not None
    assert "bugün hava çuk güzel" in p.calls[0]["user"]


def test_correct_empty_input_returns_empty_without_calling_llm():
    p = FakeProvider("ignored")
    res = correct(p, "   ")
    assert res.corrected_text == "" and res.changes == () and p.calls == []


def test_correct_invalid_json_raises_llm_error():
    with pytest.raises(LlmError):
        correct(FakeProvider("not json"), "merhaba")


def test_correct_tolerates_missing_changes():
    res = correct(FakeProvider(json.dumps({"corrected_text": "Merhaba."})), "merhaba")
    assert res.changes == ()


def test_translate_returns_stripped_text():
    p = FakeProvider("  Hello world.  ")
    assert translate(p, "Merhaba dünya.") == "Hello world."
    assert "English" in p.calls[0]["system"]


def test_enhance_prompt_returns_text_and_uses_english_system_prompt():
    p = FakeProvider("# Goal\nBuild X")
    out = enhance_prompt(p, "bana bir todo uygulaması yaz")
    assert out.startswith("# Goal")
    assert "AI agent" in p.calls[0]["system"]
```

- [x] **Step 2: Çalıştır, FAIL gör** — `pytest tests/test_llm_tasks.py -v`

- [x] **Step 3: `provider.py`, `prompts.py`, `tasks.py` yaz**

`src/dikte/llm/provider.py`:
```python
from __future__ import annotations

from typing import Protocol


class LlmError(Exception):
    pass


class LlmProvider(Protocol):
    @property
    def name(self) -> str: ...
    def complete(self, system: str, user: str, *, json_schema: dict | None = None,
                 temperature: float = 0.2) -> str: ...
```

`src/dikte/llm/prompts.py`:
```python
CORRECT_SYSTEM = """Sen bir Türkçe transkript düzeltme asistanısın. Sana bir konuşma tanıma (STT)
sisteminden çıkan ham Türkçe metin verilecek. Görevin:
1. Yanlış tanınmış, bağlama uymayan veya anlamsız kelimeleri, konuşmacının büyük olasılıkla
   söylediği doğru kelimelerle değiştirmek ("o değil de şu denmek istenmiş olabilir").
2. Yazım, noktalama ve büyük/küçük harf hatalarını düzeltmek.
3. Anlamı, üslubu ve cümle yapısını KORUMAK. Özetleme, ekleme, yorum yapma.
4. Teknik terimleri ve İngilizce kelimeleri (ör. "prompt", "agent", "repo") olduğu gibi bırakmak.
Yalnızca verilen JSON şemasına uyan bir nesne döndür. corrected_text tam düzeltilmiş metindir;
changes listesi yaptığın her anlamlı değişikliği kısa gerekçesiyle içerir."""

CORRECT_SCHEMA = {
    "type": "object",
    "properties": {
        "corrected_text": {"type": "string"},
        "changes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "original": {"type": "string"},
                    "replacement": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["original", "replacement", "reason"],
            },
        },
    },
    "required": ["corrected_text", "changes"],
}

TRANSLATE_SYSTEM = """You are a professional Turkish-to-English translator. Translate the user's
Turkish text into natural, fluent English. Preserve meaning, tone, formatting and technical terms.
Output only the translation, nothing else."""

ENHANCE_SYSTEM = """You are an expert prompt engineer. The user will give you a request, usually in
Turkish, that they intend to send to an AI coding/agentic assistant (an AI agent). Rewrite it as a
high-quality English prompt that an AI agent will understand precisely and act on.

Rules:
- Output in English only, as Markdown.
- Use these sections, omitting any that are genuinely empty: `# Goal`, `## Context`,
  `## Requirements` (numbered, testable), `## Constraints`, `## Expected Output`.
- Be specific and unambiguous; turn vague wishes into concrete, verifiable requirements.
- Keep every fact, file name, technology and constraint the user mentioned. Do not invent
  requirements the user did not imply; if something is unclear, add it under
  `## Open Questions` instead of guessing.
- No preamble, no explanation of what you did. Output only the prompt."""


def correct_user(raw: str) -> str:
    return f"Ham transkript:\n\"\"\"\n{raw}\n\"\"\""


def translate_user(text: str) -> str:
    return text


def enhance_user(text: str) -> str:
    return f"User request:\n\"\"\"\n{text}\n\"\"\""
```

`src/dikte/llm/tasks.py`:
```python
from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from dikte.llm import prompts
from dikte.llm.provider import LlmError, LlmProvider

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Change:
    original: str
    replacement: str
    reason: str


@dataclass(frozen=True)
class CorrectionResult:
    corrected_text: str
    changes: tuple[Change, ...]


def _parse_correction(reply: str) -> CorrectionResult:
    try:
        data = json.loads(reply)
    except json.JSONDecodeError as exc:
        raise LlmError(f"LLM geçerli JSON döndürmedi: {reply[:120]!r}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("corrected_text"), str):
        raise LlmError("LLM yanıtında corrected_text yok")
    changes = tuple(
        Change(str(c.get("original", "")), str(c.get("replacement", "")), str(c.get("reason", "")))
        for c in data.get("changes", []) if isinstance(c, dict)
    )
    return CorrectionResult(corrected_text=data["corrected_text"].strip(), changes=changes)


def correct(provider: LlmProvider, raw: str) -> CorrectionResult:
    if not raw.strip():
        return CorrectionResult("", ())
    reply = provider.complete(prompts.CORRECT_SYSTEM, prompts.correct_user(raw),
                              json_schema=prompts.CORRECT_SCHEMA, temperature=0.1)
    return _parse_correction(reply)


def translate(provider: LlmProvider, text: str) -> str:
    if not text.strip():
        return ""
    return provider.complete(prompts.TRANSLATE_SYSTEM, prompts.translate_user(text),
                             temperature=0.2).strip()


def enhance_prompt(provider: LlmProvider, text: str) -> str:
    if not text.strip():
        return ""
    return provider.complete(prompts.ENHANCE_SYSTEM, prompts.enhance_user(text),
                             temperature=0.3).strip()
```

- [x] **Step 4: Çalıştır, PASS gör** — `pytest tests/test_llm_tasks.py -v`

- [x] **Step 5: Başarısız Ollama provider testini yaz** — `tests/test_ollama_provider.py`

```python
from types import SimpleNamespace
import pytest
from dikte.config import LlmSettings
from dikte.llm.provider import LlmError
from dikte.llm.ollama_provider import OllamaProvider
from dikte.llm import make_provider


class FakeClient:
    def __init__(self, reply="ok", fail=None):
        self.reply, self.fail, self.calls = reply, fail, []
    def chat(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail:
            raise self.fail
        return SimpleNamespace(message=SimpleNamespace(content=self.reply))


def test_complete_sends_system_and_user_messages():
    c = FakeClient("cevap")
    p = OllamaProvider(LlmSettings(), client_factory=lambda host, timeout: c)
    assert p.complete("SYS", "USER") == "cevap"
    call = c.calls[0]
    assert call["model"] == "qwen3.5:4b"
    assert call["messages"] == [{"role": "system", "content": "SYS"}, {"role": "user", "content": "USER"}]
    assert call["keep_alive"] == "30m" and call["options"]["temperature"] == 0.2
    assert call["think"] is False and call["options"]["num_ctx"] == 8192
    assert "format" not in call or call["format"] is None


def test_complete_passes_json_schema_as_format():
    c = FakeClient("{}")
    p = OllamaProvider(LlmSettings(), client_factory=lambda host, timeout: c)
    p.complete("s", "u", json_schema={"type": "object"})
    assert c.calls[0]["format"] == {"type": "object"}


def test_connection_error_becomes_llm_error():
    c = FakeClient(fail=ConnectionError("refused"))
    p = OllamaProvider(LlmSettings(), client_factory=lambda host, timeout: c)
    with pytest.raises(LlmError, match="Ollama"):
        p.complete("s", "u")


def test_make_provider_selects_ollama_by_default():
    assert make_provider(LlmSettings()).name == "ollama"


def test_make_provider_anthropic_requires_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(LlmError, match="ANTHROPIC_API_KEY"):
        make_provider(LlmSettings(provider="anthropic"))
```

- [x] **Step 6: Çalıştır, FAIL gör** — `pytest tests/test_ollama_provider.py -v`

- [x] **Step 7: `ollama_provider.py`, `anthropic_provider.py`, `llm/__init__.py` yaz**

`src/dikte/llm/ollama_provider.py`:
```python
from __future__ import annotations

import logging
from typing import Callable

from dikte.config import LlmSettings
from dikte.llm.provider import LlmError

log = logging.getLogger(__name__)


def _default_client_factory(host: str, timeout: float):
    from ollama import Client
    return Client(host=host, timeout=timeout)


class OllamaProvider:
    name = "ollama"

    def __init__(self, settings: LlmSettings, client_factory: Callable | None = None):
        self._settings = settings
        self._client = (client_factory or _default_client_factory)(settings.ollama_host, settings.timeout_s)

    def complete(self, system: str, user: str, *, json_schema: dict | None = None,
                 temperature: float = 0.2) -> str:
        try:
            resp = self._client.chat(
                model=self._settings.model,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                format=json_schema,
                think=self._settings.think,
                options={"temperature": temperature, "top_p": self._settings.top_p,
                         "top_k": self._settings.top_k, "num_ctx": self._settings.num_ctx},
                keep_alive=self._settings.keep_alive,
            )
        except Exception as exc:
            log.exception("Ollama isteği başarısız")
            raise LlmError(f"Ollama'ya ulaşılamadı veya yanıt vermedi ({self._settings.ollama_host}): {exc}") from exc
        content = getattr(getattr(resp, "message", None), "content", None)
        if not isinstance(content, str):
            raise LlmError("Ollama boş yanıt döndürdü")
        return content
```

`src/dikte/llm/anthropic_provider.py`:
```python
from __future__ import annotations

import json
import logging
import os
from typing import Callable

from dikte.config import LlmSettings
from dikte.llm.provider import LlmError

log = logging.getLogger(__name__)


def _default_client_factory(api_key: str, timeout: float):
    from anthropic import Anthropic
    return Anthropic(api_key=api_key, timeout=timeout)


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, settings: LlmSettings, client_factory: Callable | None = None):
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise LlmError("ANTHROPIC_API_KEY ortam değişkeni tanımlı değil")
        self._settings = settings
        self._client = (client_factory or _default_client_factory)(api_key, settings.timeout_s)

    def complete(self, system: str, user: str, *, json_schema: dict | None = None,
                 temperature: float = 0.2) -> str:
        sys_prompt = system
        if json_schema is not None:
            sys_prompt += "\n\nRespond ONLY with a JSON object matching this schema:\n" + json.dumps(json_schema)
        try:
            msg = self._client.messages.create(
                model=self._settings.anthropic_model,
                max_tokens=4096,
                temperature=temperature,
                system=sys_prompt,
                messages=[{"role": "user", "content": user}],
            )
        except Exception as exc:
            log.exception("Anthropic isteği başarısız")
            raise LlmError(f"Anthropic API hatası: {exc}") from exc
        text = "".join(getattr(b, "text", "") for b in msg.content)
        if json_schema is not None:
            start, end = text.find("{"), text.rfind("}")
            if start >= 0 and end > start:
                text = text[start:end + 1]
        return text
```

`src/dikte/llm/__init__.py`:
```python
from dikte.config import LlmSettings
from dikte.llm.provider import LlmError, LlmProvider


def make_provider(settings: LlmSettings) -> LlmProvider:
    if settings.provider == "ollama":
        from dikte.llm.ollama_provider import OllamaProvider
        return OllamaProvider(settings)
    if settings.provider == "anthropic":
        from dikte.llm.anthropic_provider import AnthropicProvider
        return AnthropicProvider(settings)
    raise LlmError(f"Bilinmeyen LLM sağlayıcı: {settings.provider}")


__all__ = ["LlmError", "LlmProvider", "make_provider"]
```

- [x] **Step 8: Çalıştır, PASS gör** — `pytest tests/test_llm_tasks.py tests/test_ollama_provider.py -v`

- [x] **Step 9: Commit** — `git add -A && git commit -m "feat: LLM providers and correction/translation/prompt tasks"`

---

### Task 5: Durum makinesi ve DictationController

**Files:**
- Create: `src/dikte/core/__init__.py`, `src/dikte/core/state.py`, `src/dikte/core/workers.py`, `src/dikte/core/controller.py`
- Test: `tests/test_controller.py`

**Interfaces:**
- Consumes: `AudioRecorder` (Task 2), `SttEngine` (Task 3), `LlmProvider` + `tasks` (Task 4), `Settings` (Task 1).
- Produces: `DictationState` enum (`IDLE, RECORDING, TRANSCRIBING, CORRECTING, RESULT`); `Session(frozen dataclass: id: str, created_at: datetime, raw_text: str = "", corrected_text: str = "", changes: tuple[Change,...] = (), translation: str = "", enhanced_prompt: str = "", duration_s: float = 0.0)`; `DictationController(QObject)` — sinyaller `state_changed(object)` (DictationState), `session_updated(object)` (Session), `error(str)`, `level_changed(float)`, `buckets_changed(object)`; slotlar `toggle()`, `request_translation(text: str)`, `request_enhanced_prompt(text: str)`, `warm_up()`; özellikler `state`, `session`. `workers.run_in_pool(fn, on_result, on_error, pool=None)`.

- [x] **Step 1: Başarısız controller testini yaz** — `tests/test_controller.py`

```python
import json
import numpy as np
import pytest
from PySide6.QtCore import QObject, QThreadPool, Signal
from dikte.config import Settings
from dikte.core.controller import DictationController
from dikte.core.state import DictationState
from dikte.stt.result import TranscriptResult


class FakeRecorder(QObject):
    level_changed = Signal(float)
    buckets_changed = Signal(object)
    error = Signal(str)

    def __init__(self):
        super().__init__()
        self.started = self.stopped = False
        self.audio = np.ones(16000, dtype=np.float32) * 0.1

    def start(self): self.started = True

    def stop(self):
        self.stopped = True
        return self.audio


class FakeStt:
    def __init__(self, text="merhaba dünya"): self.text, self.loaded = text, False
    @property
    def is_loaded(self): return self.loaded
    def load(self): self.loaded = True
    def transcribe(self, audio, language=None):
        return TranscriptResult(self.text, "tr", 1.0, ())


class FakeLlm:
    name = "fake"
    def __init__(self): self.calls = []
    def complete(self, system, user, *, json_schema=None, temperature=0.2):
        self.calls.append(user)
        if json_schema:
            return json.dumps({"corrected_text": "Merhaba dünya.", "changes": []})
        if "User request" in user:
            return "# Goal\nSay hello"
        return "Hello world."


@pytest.fixture
def ctl(qtbot):
    rec, stt, llm = FakeRecorder(), FakeStt(), FakeLlm()
    c = DictationController(Settings(), recorder=rec, stt=stt, llm=llm, pool=QThreadPool())
    return c, rec, stt, llm


def test_initial_state_idle(ctl):
    c, *_ = ctl
    assert c.state is DictationState.IDLE


def test_toggle_starts_recording(ctl, qtbot):
    c, rec, *_ = ctl
    with qtbot.waitSignal(c.state_changed):
        c.toggle()
    assert c.state is DictationState.RECORDING and rec.started


def test_full_cycle_reaches_result_with_texts(ctl, qtbot):
    c, rec, stt, llm = ctl
    c.toggle()
    with qtbot.waitSignal(c.state_changed, timeout=5000, check_params_cb=lambda s: s is DictationState.RESULT):
        c.toggle()
    assert rec.stopped
    assert c.session.raw_text == "merhaba dünya"
    assert c.session.corrected_text == "Merhaba dünya."


def test_toggle_ignored_while_transcribing(ctl, qtbot):
    c, *_ = ctl
    c.toggle()
    c.toggle()  # -> TRANSCRIBING (async)
    assert c.state is DictationState.TRANSCRIBING
    c.toggle()  # yok sayılmalı
    assert c.state is DictationState.TRANSCRIBING
    qtbot.waitUntil(lambda: c.state is DictationState.RESULT, timeout=5000)


def test_toggle_from_result_starts_new_recording(ctl, qtbot):
    c, rec, *_ = ctl
    c.toggle(); c.toggle()
    qtbot.waitUntil(lambda: c.state is DictationState.RESULT, timeout=5000)
    c.toggle()
    assert c.state is DictationState.RECORDING and c.session.raw_text == ""


def test_llm_failure_still_shows_raw_text(qtbot):
    class BadLlm(FakeLlm):
        def complete(self, *a, **k): raise RuntimeError("down")
    rec, stt = FakeRecorder(), FakeStt()
    c = DictationController(Settings(), recorder=rec, stt=stt, llm=BadLlm(), pool=QThreadPool())
    errors = []
    c.error.connect(errors.append)
    c.toggle(); c.toggle()
    qtbot.waitUntil(lambda: c.state is DictationState.RESULT, timeout=5000)
    assert c.session.raw_text == "merhaba dünya"
    assert c.session.corrected_text == "merhaba dünya"  # düzeltme başarısızsa ham metin kopyalanır
    assert errors and "down" in errors[0]


def test_empty_transcript_goes_back_to_idle_with_error(qtbot):
    rec, stt = FakeRecorder(), FakeStt(text="")
    c = DictationController(Settings(), recorder=rec, stt=stt, llm=FakeLlm(), pool=QThreadPool())
    errors = []
    c.error.connect(errors.append)
    c.toggle(); c.toggle()
    qtbot.waitUntil(lambda: c.state is DictationState.IDLE, timeout=5000)
    assert errors


def test_request_translation_updates_session(ctl, qtbot):
    c, *_ = ctl
    with qtbot.waitSignal(c.session_updated, timeout=5000, check_params_cb=lambda s: s.translation != ""):
        c.request_translation("Merhaba dünya.")
    assert c.session.translation == "Hello world."


def test_request_enhanced_prompt_updates_session(ctl, qtbot):
    c, *_ = ctl
    with qtbot.waitSignal(c.session_updated, timeout=5000, check_params_cb=lambda s: s.enhanced_prompt != ""):
        c.request_enhanced_prompt("merhaba de")
    assert c.session.enhanced_prompt.startswith("# Goal")
```

- [x] **Step 2: Çalıştır, FAIL gör** — `pytest tests/test_controller.py -v`

- [x] **Step 3: `state.py`, `workers.py`, `controller.py` yaz**

`src/dikte/core/state.py`:
```python
from __future__ import annotations

import uuid
from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import Enum, auto

from dikte.llm.tasks import Change


class DictationState(Enum):
    IDLE = auto()
    RECORDING = auto()
    TRANSCRIBING = auto()
    CORRECTING = auto()
    RESULT = auto()


@dataclass(frozen=True)
class Session:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    created_at: datetime = field(default_factory=datetime.now)
    raw_text: str = ""
    corrected_text: str = ""
    changes: tuple[Change, ...] = ()
    translation: str = ""
    enhanced_prompt: str = ""
    duration_s: float = 0.0

    def with_(self, **kwargs) -> "Session":
        return replace(self, **kwargs)
```

`src/dikte/core/workers.py`:
```python
from __future__ import annotations

import logging
from typing import Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot

log = logging.getLogger(__name__)


class _Signals(QObject):
    result = Signal(object)
    error = Signal(str)


class _Job(QRunnable):
    def __init__(self, fn: Callable[[], object], signals: _Signals):
        super().__init__()
        self._fn, self._signals = fn, signals
        self.setAutoDelete(True)

    @Slot()
    def run(self) -> None:
        try:
            self._signals.result.emit(self._fn())
        except Exception as exc:
            log.exception("worker hatası")
            self._signals.error.emit(str(exc))


def run_in_pool(fn: Callable[[], object], on_result: Callable[[object], None],
                on_error: Callable[[str], None], pool: QThreadPool | None = None) -> _Signals:
    """fn'i thread havuzunda çalıştırır; sonuç/hata Qt sinyaliyle çağıran thread'e döner.
    Dönen _Signals nesnesi, job bitene kadar referansı canlı tutmak için saklanmalıdır."""
    signals = _Signals()
    signals.result.connect(on_result)
    signals.error.connect(on_error)
    (pool or QThreadPool.globalInstance()).start(_Job(fn, signals))
    return signals
```

`src/dikte/core/controller.py`:
```python
from __future__ import annotations

import logging

import numpy as np
from PySide6.QtCore import QObject, QThreadPool, Signal, Slot

from dikte.config import Settings
from dikte.core.state import DictationState, Session
from dikte.core.workers import run_in_pool
from dikte.llm import tasks
from dikte.llm.provider import LlmProvider
from dikte.stt.engine import SttEngine
from dikte.stt.result import TranscriptResult

log = logging.getLogger(__name__)


class DictationController(QObject):
    state_changed = Signal(object)
    session_updated = Signal(object)
    error = Signal(str)
    level_changed = Signal(float)
    buckets_changed = Signal(object)
    ready_changed = Signal(bool)

    def __init__(self, settings: Settings, *, recorder, stt: SttEngine, llm: LlmProvider,
                 pool: QThreadPool | None = None, parent=None):
        super().__init__(parent)
        self._settings = settings
        self._recorder, self._stt, self._llm = recorder, stt, llm
        self._pool = pool or QThreadPool.globalInstance()
        self._state = DictationState.IDLE
        self._session = Session()
        self._jobs: list = []  # canlı sinyal nesneleri
        recorder.level_changed.connect(self.level_changed)
        recorder.buckets_changed.connect(self.buckets_changed)
        recorder.error.connect(self._on_recorder_error)

    # ---- özellikler
    @property
    def state(self) -> DictationState:
        return self._state

    @property
    def session(self) -> Session:
        return self._session

    def update_settings(self, settings: Settings) -> None:
        self._settings = settings

    # ---- kamu slotları
    @Slot()
    def warm_up(self) -> None:
        self._spawn(self._stt.load, lambda _: self.ready_changed.emit(True),
                    lambda e: self.error.emit(f"STT modeli yüklenemedi: {e}"))

    @Slot()
    def toggle(self) -> None:
        if self._state in (DictationState.IDLE, DictationState.RESULT):
            self._start_recording()
        elif self._state is DictationState.RECORDING:
            self._stop_and_transcribe()
        else:
            log.debug("toggle yok sayıldı (durum: %s)", self._state)

    @Slot(str)
    def request_translation(self, text: str) -> None:
        self._spawn(lambda: tasks.translate(self._llm, text),
                    lambda out: self._update_session(translation=out),
                    lambda e: self.error.emit(f"Çeviri başarısız: {e}"))

    @Slot(str)
    def request_enhanced_prompt(self, text: str) -> None:
        self._spawn(lambda: tasks.enhance_prompt(self._llm, text),
                    lambda out: self._update_session(enhanced_prompt=out),
                    lambda e: self.error.emit(f"Prompt oluşturma başarısız: {e}"))

    # ---- iç akış
    def _start_recording(self) -> None:
        self._session = Session()
        self.session_updated.emit(self._session)
        self._recorder.start()
        self._set_state(DictationState.RECORDING)

    def _stop_and_transcribe(self) -> None:
        audio: np.ndarray = self._recorder.stop()
        self._set_state(DictationState.TRANSCRIBING)
        self._spawn(lambda: self._stt.transcribe(audio, self._settings.stt.language),
                    self._on_transcribed, self._on_stt_error)

    def _on_transcribed(self, result: TranscriptResult) -> None:
        if not result.text.strip():
            self.error.emit("Konuşma algılanamadı, ses boş görünüyor.")
            self._set_state(DictationState.IDLE)
            return
        self._update_session(raw_text=result.text, duration_s=result.duration_s)
        self._set_state(DictationState.CORRECTING)
        raw = result.text
        self._spawn(lambda: tasks.correct(self._llm, raw), self._on_corrected, self._on_llm_error)

    def _on_corrected(self, res: tasks.CorrectionResult) -> None:
        self._update_session(corrected_text=res.corrected_text or self._session.raw_text,
                             changes=res.changes)
        self._set_state(DictationState.RESULT)

    def _on_llm_error(self, msg: str) -> None:
        self.error.emit(f"LLM düzeltmesi başarısız, ham metin gösteriliyor: {msg}")
        self._update_session(corrected_text=self._session.raw_text)
        self._set_state(DictationState.RESULT)

    def _on_stt_error(self, msg: str) -> None:
        self.error.emit(f"Transkripsiyon başarısız: {msg}")
        self._set_state(DictationState.IDLE)

    def _on_recorder_error(self, msg: str) -> None:
        self.error.emit(msg)
        if self._state is DictationState.RECORDING:
            self._set_state(DictationState.IDLE)

    def _set_state(self, new: DictationState) -> None:
        if new is self._state:
            return
        self._state = new
        self.state_changed.emit(new)

    def _update_session(self, **kwargs) -> None:
        self._session = self._session.with_(**kwargs)
        self.session_updated.emit(self._session)

    def _spawn(self, fn, on_result, on_error) -> None:
        sig = run_in_pool(fn, on_result, on_error, self._pool)
        self._jobs.append(sig)
        self._jobs = self._jobs[-16:]
```

- [x] **Step 4: Çalıştır, PASS gör** — `pytest tests/test_controller.py -v`

- [x] **Step 5: Commit** — `git add -A && git commit -m "feat: dictation controller state machine"`

---

### Task 6: Global kısayol (Win32 RegisterHotKey)

**Files:**
- Create: `src/dikte/platform/__init__.py`, `src/dikte/platform/hotkey_parse.py`, `src/dikte/platform/hotkey.py`
- Test: `tests/test_hotkey_parse.py`

**Interfaces:**
- Produces: `hotkey_parse.parse_hotkey(spec: str) -> HotkeySpec(modifiers: int, vk: int, label: str)`; `HotkeyParseError(ValueError)`; `GlobalHotkey(QObject)` — `activated` sinyali, `register(spec: str) -> bool`, `unregister() -> None`. Windows dışında `register` `False` döner ve log yazar.

- [x] **Step 1: Başarısız parse testini yaz** — `tests/test_hotkey_parse.py`

```python
import pytest
from dikte.platform.hotkey_parse import (
    MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, MOD_NOREPEAT, HotkeyParseError, parse_hotkey)


def test_ctrl_alt_space():
    hk = parse_hotkey("ctrl+alt+space")
    assert hk.modifiers == MOD_CONTROL | MOD_ALT | MOD_NOREPEAT
    assert hk.vk == 0x20 and hk.label == "Ctrl+Alt+Space"


def test_letters_and_function_keys():
    assert parse_hotkey("ctrl+shift+d").vk == ord("D")
    assert parse_hotkey("win+f9").vk == 0x78
    assert parse_hotkey("win+f9").modifiers & MOD_WIN


def test_case_and_whitespace_insensitive():
    assert parse_hotkey(" CTRL + Alt + Space ") == parse_hotkey("ctrl+alt+space")


def test_requires_at_least_one_modifier():
    with pytest.raises(HotkeyParseError):
        parse_hotkey("space")


def test_unknown_key_raises():
    with pytest.raises(HotkeyParseError):
        parse_hotkey("ctrl+bogus")
```

- [x] **Step 2: Çalıştır, FAIL gör** — `pytest tests/test_hotkey_parse.py -v`

- [x] **Step 3: `hotkey_parse.py` ve `hotkey.py` yaz**

`src/dikte/platform/hotkey_parse.py`:
```python
from __future__ import annotations

from dataclasses import dataclass

MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, MOD_NOREPEAT = 0x0001, 0x0002, 0x0004, 0x0008, 0x4000

_MODS = {"ctrl": MOD_CONTROL, "control": MOD_CONTROL, "alt": MOD_ALT,
         "shift": MOD_SHIFT, "win": MOD_WIN, "meta": MOD_WIN}
_MOD_LABEL = {MOD_CONTROL: "Ctrl", MOD_ALT: "Alt", MOD_SHIFT: "Shift", MOD_WIN: "Win"}
_KEYS = {"space": 0x20, "enter": 0x0D, "return": 0x0D, "tab": 0x09, "esc": 0x1B, "escape": 0x1B,
         "backspace": 0x08, "insert": 0x2D, "delete": 0x2E, "home": 0x24, "end": 0x23,
         "pageup": 0x21, "pagedown": 0x22, "pause": 0x13, "scrolllock": 0x91,
         "capslock": 0x14, "numlock": 0x90, "printscreen": 0x2C,
         **{f"f{i}": 0x70 + i - 1 for i in range(1, 25)}}


class HotkeyParseError(ValueError):
    pass


@dataclass(frozen=True)
class HotkeySpec:
    modifiers: int
    vk: int
    label: str


def parse_hotkey(spec: str) -> HotkeySpec:
    parts = [p.strip().lower() for p in spec.split("+") if p.strip()]
    if len(parts) < 2:
        raise HotkeyParseError("Kısayol en az bir değiştirici (Ctrl/Alt/Shift/Win) ve bir tuş içermeli")
    *mods, key = parts
    modifiers = 0
    for m in mods:
        if m not in _MODS:
            raise HotkeyParseError(f"Bilinmeyen değiştirici: {m}")
        modifiers |= _MODS[m]
    if key in _KEYS:
        vk = _KEYS[key]
    elif len(key) == 1 and key.isalnum() and key.isascii():
        vk = ord(key.upper())
    else:
        raise HotkeyParseError(f"Bilinmeyen tuş: {key}")
    labels = [_MOD_LABEL[b] for b in (MOD_CONTROL, MOD_ALT, MOD_SHIFT, MOD_WIN) if modifiers & b]
    label = "+".join(labels + [key.capitalize() if len(key) > 1 else key.upper()])
    return HotkeySpec(modifiers | MOD_NOREPEAT, vk, label)
```

`src/dikte/platform/hotkey.py`:
```python
from __future__ import annotations

import ctypes
import logging
import sys

from PySide6.QtCore import QAbstractNativeEventFilter, QCoreApplication, QObject, Signal

from dikte.platform.hotkey_parse import HotkeySpec, parse_hotkey

log = logging.getLogger(__name__)
WM_HOTKEY = 0x0312
HOTKEY_ID = 0xD1C7


class _Filter(QAbstractNativeEventFilter):
    def __init__(self, on_hotkey):
        super().__init__()
        self._on_hotkey = on_hotkey

    def nativeEventFilter(self, event_type, message):
        if event_type == b"windows_generic_MSG":
            msg = ctypes.wintypes.MSG.from_address(int(message))
            if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
                self._on_hotkey()
                return True, 0
        return False, 0


class GlobalHotkey(QObject):
    activated = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._filter: _Filter | None = None
        self._spec: HotkeySpec | None = None

    def register(self, spec: str) -> bool:
        self.unregister()
        parsed = parse_hotkey(spec)
        if sys.platform != "win32":
            log.warning("Global kısayol yalnızca Windows'ta desteklenir (%s)", parsed.label)
            return False
        import ctypes.wintypes  # noqa: F401  (MSG yapısı için)
        ok = ctypes.windll.user32.RegisterHotKey(None, HOTKEY_ID, parsed.modifiers, parsed.vk)
        if not ok:
            err = ctypes.GetLastError()
            log.error("RegisterHotKey başarısız (%s), hata=%s", parsed.label, err)
            return False
        self._filter = _Filter(self.activated.emit)
        QCoreApplication.instance().installNativeEventFilter(self._filter)
        self._spec = parsed
        log.info("Global kısayol kaydedildi: %s", parsed.label)
        return True

    def unregister(self) -> None:
        if sys.platform == "win32" and self._spec is not None:
            ctypes.windll.user32.UnregisterHotKey(None, HOTKEY_ID)
        if self._filter is not None:
            app = QCoreApplication.instance()
            if app is not None:
                app.removeNativeEventFilter(self._filter)
        self._filter, self._spec = None, None

    @property
    def label(self) -> str:
        return self._spec.label if self._spec else ""
```

Not: `RegisterHotKey(None, ...)` ile kayıt, mesajın çağıran thread'in mesaj kuyruğuna düşmesini sağlar; Qt ana thread'i bu kuyruğu işlediği için `nativeEventFilter` tetiklenir. Kayıt ana (GUI) thread'inde yapılmalıdır.

- [x] **Step 4: Çalıştır, PASS gör** — `pytest tests/test_hotkey_parse.py -v`

- [x] **Step 5: Commit** — `git add -A && git commit -m "feat: global hotkey via Win32 RegisterHotKey"`

---

### Task 7: Dalga formu widget'ı ve kayıt overlay'i

**Files:**
- Create: `src/dikte/ui/__init__.py`, `src/dikte/ui/icons.py`, `src/dikte/ui/waveform.py`, `src/dikte/ui/overlay.py`
- Test: `tests/test_ui_waveform.py`

**Interfaces:**
- Consumes: `DictationState`, controller sinyalleri `buckets_changed(object)`, `state_changed(object)` (Task 5).
- Produces: `WaveformWidget(QWidget)`: `push_buckets(buckets: tuple[float, ...])`, `clear()`, `bars -> tuple[float, ...]`; `RecordingOverlay(QWidget)`: `show_recording()`, `show_status(text: str)`, `hide_overlay()`, `on_buckets(buckets)`, `on_state(state)`. `icons.make_tray_icon(state: str) -> QIcon` (`"idle" | "recording" | "busy"`), `icons.copy_icon() -> QIcon`.

- [x] **Step 1: Başarısız waveform testini yaz** — `tests/test_ui_waveform.py`

```python
from dikte.ui.waveform import WaveformWidget, BAR_COUNT


def test_initial_bars_are_zero(qtbot):
    w = WaveformWidget(); qtbot.addWidget(w)
    assert w.bars == (0.0,) * BAR_COUNT


def test_push_buckets_resamples_to_bar_count(qtbot):
    w = WaveformWidget(); qtbot.addWidget(w)
    w.push_buckets((1.0,) * 8)
    assert len(w.bars) == BAR_COUNT and max(w.bars) > 0.5


def test_bars_decay_toward_zero_on_tick(qtbot):
    w = WaveformWidget(); qtbot.addWidget(w)
    w.push_buckets((1.0,) * BAR_COUNT)
    before = w.bars[0]
    w._tick()
    assert w.bars[0] < before


def test_clear_resets(qtbot):
    w = WaveformWidget(); qtbot.addWidget(w)
    w.push_buckets((1.0,) * BAR_COUNT); w.clear()
    assert w.bars == (0.0,) * BAR_COUNT


def test_paint_does_not_crash(qtbot):
    w = WaveformWidget(); qtbot.addWidget(w)
    w.resize(300, 60); w.push_buckets((0.5,) * BAR_COUNT); w.show()
    w.grab()  # paintEvent tetikler
```

- [x] **Step 2: Çalıştır, FAIL gör** — `pytest tests/test_ui_waveform.py -v`

- [x] **Step 3: `icons.py`, `waveform.py`, `overlay.py` yaz**

`src/dikte/ui/icons.py`:
```python
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap

_COLORS = {"idle": QColor("#4A90E2"), "recording": QColor("#E53935"), "busy": QColor("#F5A623")}


def make_tray_icon(state: str = "idle", size: int = 64) -> QIcon:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(_COLORS.get(state, _COLORS["idle"]))
    p.setPen(Qt.NoPen)
    p.drawEllipse(QRectF(size * 0.1, size * 0.1, size * 0.8, size * 0.8))
    p.setPen(QPen(QColor("white"), size * 0.12, Qt.SolidLine, Qt.RoundCap))
    for i, h in enumerate((0.25, 0.5, 0.35)):
        x = size * (0.35 + i * 0.15)
        p.drawLine(int(x), int(size * (0.5 - h / 2)), int(x), int(size * (0.5 + h / 2)))
    p.end()
    return QIcon(pm)


def copy_icon(size: int = 32) -> QIcon:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(QColor("#666"), 2))
    p.drawRoundedRect(QRectF(size * 0.35, size * 0.35, size * 0.45, size * 0.5), 3, 3)
    p.drawRoundedRect(QRectF(size * 0.2, size * 0.15, size * 0.45, size * 0.5), 3, 3)
    p.end()
    return QIcon(pm)
```

`src/dikte/ui/waveform.py`:
```python
from __future__ import annotations

import numpy as np
from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget

BAR_COUNT = 32
DECAY = 0.85
TICK_MS = 33


class WaveformWidget(QWidget):
    def __init__(self, parent=None, color: str = "#E53935"):
        super().__init__(parent)
        self._bars: tuple[float, ...] = (0.0,) * BAR_COUNT
        self._color = QColor(color)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(TICK_MS)
        self.setMinimumHeight(40)

    @property
    def bars(self) -> tuple[float, ...]:
        return self._bars

    def push_buckets(self, buckets: tuple[float, ...]) -> None:
        src = np.asarray(buckets, dtype=np.float32)
        if src.size == 0:
            return
        idx = np.linspace(0, src.size - 1, BAR_COUNT)
        resampled = np.interp(idx, np.arange(src.size), src)
        # yeni değer mevcut değerden büyükse hemen yükselt, değilse tick decay'e bırak
        self._bars = tuple(max(float(n), o) for n, o in zip(resampled, self._bars))
        self.update()

    def clear(self) -> None:
        self._bars = (0.0,) * BAR_COUNT
        self.update()

    def _tick(self) -> None:
        if any(self._bars):
            self._bars = tuple(v * DECAY if v > 0.01 else 0.0 for v in self._bars)
            self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        gap = 2.0
        bw = max(1.0, (w - gap * (BAR_COUNT - 1)) / BAR_COUNT)
        p.setPen(Qt.NoPen)
        p.setBrush(self._color)
        for i, v in enumerate(self._bars):
            bh = max(2.0, v * h)
            x = i * (bw + gap)
            p.drawRoundedRect(QRectF(x, (h - bh) / 2, bw, bh), bw / 2, bw / 2)
        p.end()
```

`src/dikte/ui/overlay.py`:
```python
from __future__ import annotations

from PySide6.QtCore import QElapsedTimer, Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from dikte.core.state import DictationState
from dikte.ui.waveform import WaveformWidget

_STATUS = {DictationState.TRANSCRIBING: "Yazıya dökülüyor…",
           DictationState.CORRECTING: "Düzeltiliyor…"}


class RecordingOverlay(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setStyleSheet("QWidget#panel{background:rgba(20,20,20,225);border-radius:14px;}"
                           "QLabel{color:white;font-size:14px;}")
        panel = QWidget(self); panel.setObjectName("panel")
        lay = QHBoxLayout(panel); lay.setContentsMargins(16, 10, 16, 10); lay.setSpacing(12)
        self._dot = QLabel("●"); self._dot.setStyleSheet("color:#E53935;font-size:22px;")
        self._wave = WaveformWidget(); self._wave.setFixedSize(220, 44)
        self._time = QLabel("00:00"); self._time.setMinimumWidth(48)
        self._status = QLabel(""); self._status.hide()
        for w in (self._dot, self._wave, self._time, self._status):
            lay.addWidget(w)
        outer = QHBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0); outer.addWidget(panel)
        self._blink = QTimer(self); self._blink.setInterval(500); self._blink.timeout.connect(self._toggle_dot)
        self._clock = QTimer(self); self._clock.setInterval(250); self._clock.timeout.connect(self._update_time)
        self._elapsed = QElapsedTimer()
        self._dot_on = True

    # ---- kamu
    def show_recording(self) -> None:
        self._wave.clear(); self._wave.show(); self._time.show(); self._status.hide()
        self._dot.show(); self._dot_on = True; self._dot.setVisible(True)
        self._elapsed.start(); self._update_time()
        self._blink.start(); self._clock.start()
        self._place(); self.show()

    def show_status(self, text: str) -> None:
        self._blink.stop(); self._clock.stop()
        self._dot.setStyleSheet("color:#F5A623;font-size:22px;"); self._dot.setVisible(True)
        self._wave.hide(); self._time.hide()
        self._status.setText(text); self._status.show()
        self.adjustSize(); self._place(); self.show()

    def hide_overlay(self) -> None:
        self._blink.stop(); self._clock.stop()
        self._dot.setStyleSheet("color:#E53935;font-size:22px;")
        self.hide()

    def on_buckets(self, buckets) -> None:
        self._wave.push_buckets(tuple(buckets))

    def on_state(self, state: DictationState) -> None:
        if state is DictationState.RECORDING:
            self.show_recording()
        elif state in _STATUS:
            self.show_status(_STATUS[state])
        else:
            self.hide_overlay()

    # ---- iç
    def _toggle_dot(self) -> None:
        self._dot_on = not self._dot_on
        self._dot.setVisible(self._dot_on)

    def _update_time(self) -> None:
        s = self._elapsed.elapsed() // 1000
        self._time.setText(f"{s // 60:02d}:{s % 60:02d}")

    def _place(self) -> None:
        self.adjustSize()
        screen = QGuiApplication.primaryScreen().availableGeometry()
        self.move(screen.center().x() - self.width() // 2, screen.bottom() - self.height() - 80)
```

- [x] **Step 4: Overlay için smoke test ekle** — `tests/test_ui_waveform.py` sonuna:

```python
from dikte.core.state import DictationState
from dikte.ui.overlay import RecordingOverlay


def test_overlay_state_transitions(qtbot):
    o = RecordingOverlay(); qtbot.addWidget(o)
    o.on_state(DictationState.RECORDING)
    assert o.isVisible() and o._blink.isActive()
    o.on_buckets((0.5,) * 32)
    o.on_state(DictationState.TRANSCRIBING)
    assert o.isVisible() and not o._blink.isActive() and o._status.text() == "Yazıya dökülüyor…"
    o.on_state(DictationState.RESULT)
    assert not o.isVisible()
```

- [x] **Step 5: Çalıştır, PASS gör** — `pytest tests/test_ui_waveform.py -v`

- [x] **Step 6: Commit** — `git add -A && git commit -m "feat: waveform widget and recording overlay"`

---

### Task 8: Sonuç penceresi (Ham / Düzeltilmiş / Prompt) ve kopyalama

**Files:**
- Create: `src/dikte/ui/text_pane.py`, `src/dikte/ui/toast.py`, `src/dikte/ui/result_window.py`
- Test: `tests/test_ui_text_pane.py`, `tests/test_ui_result_window.py`

**Interfaces:**
- Consumes: `DictationController` sinyalleri/slotları (Task 5), `Session`, `Change`, `copy_icon` (Task 7).
- Produces: `TextPane(QWidget)`: `set_text(str)`, `text() -> str`, `copied` sinyali (str), `set_busy(bool)`; `ResultWindow(QMainWindow)`: `bind(controller)`, `on_session(session)`, `on_state(state)`; butonlar `translate_btn`, `enhance_btn`; pane'ler `raw_pane`, `corrected_pane`, `output_pane`. `Toast.show_message(parent, text)`.

- [x] **Step 1: Başarısız TextPane testini yaz** — `tests/test_ui_text_pane.py`

```python
from PySide6.QtWidgets import QApplication
from dikte.ui.text_pane import TextPane


def test_set_and_get_text(qtbot):
    p = TextPane("Ham"); qtbot.addWidget(p)
    p.set_text("merhaba")
    assert p.text() == "merhaba" and p.title_label.text() == "Ham"


def test_copy_button_puts_text_on_clipboard_and_emits(qtbot):
    p = TextPane("Ham"); qtbot.addWidget(p)
    p.set_text("kopyala beni")
    with qtbot.waitSignal(p.copied) as blocker:
        p.copy_btn.click()
    assert blocker.args[0] == "kopyala beni"
    assert QApplication.clipboard().text() == "kopyala beni"


def test_editor_is_editable(qtbot):
    p = TextPane("Düzeltilmiş"); qtbot.addWidget(p)
    assert not p.editor.isReadOnly()
    qtbot.keyClicks(p.editor, "abc")
    assert p.text() == "abc"


def test_busy_disables_copy(qtbot):
    p = TextPane("X"); qtbot.addWidget(p)
    p.set_busy(True)
    assert not p.copy_btn.isEnabled()
```

- [x] **Step 2: Çalıştır, FAIL gör** — `pytest tests/test_ui_text_pane.py -v`

- [x] **Step 3: `text_pane.py` ve `toast.py` yaz**

`src/dikte/ui/text_pane.py`:
```python
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QApplication, QHBoxLayout, QLabel, QPlainTextEdit, QToolButton,
                               QVBoxLayout, QWidget)

from dikte.ui.icons import copy_icon


class TextPane(QWidget):
    copied = Signal(str)

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.title_label = QLabel(title)
        self.title_label.setStyleSheet("font-weight:600;")
        self.copy_btn = QToolButton()
        self.copy_btn.setIcon(copy_icon())
        self.copy_btn.setToolTip("Kopyala (Ctrl+Shift+C)")
        self.copy_btn.setAutoRaise(True)
        self.copy_btn.clicked.connect(self._copy)
        self.editor = QPlainTextEdit()
        self.editor.setPlaceholderText("…")
        header = QHBoxLayout(); header.addWidget(self.title_label); header.addStretch(1)
        header.addWidget(self.copy_btn, alignment=Qt.AlignRight)
        lay = QVBoxLayout(self); lay.setContentsMargins(0, 0, 0, 0)
        lay.addLayout(header); lay.addWidget(self.editor, 1)

    def set_text(self, text: str) -> None:
        if self.editor.toPlainText() != text:
            self.editor.setPlainText(text)

    def text(self) -> str:
        return self.editor.toPlainText()

    def set_busy(self, busy: bool) -> None:
        self.copy_btn.setEnabled(not busy)
        self.editor.setPlaceholderText("Bekleniyor…" if busy else "…")

    def _copy(self) -> None:
        text = self.text()
        if not text:
            return
        QApplication.clipboard().setText(text)
        self.copied.emit(text)
```

`src/dikte/ui/toast.py`:
```python
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QLabel, QWidget


class Toast(QLabel):
    def __init__(self, parent: QWidget, text: str, ms: int = 1500):
        super().__init__(text, parent)
        self.setStyleSheet("background:rgba(30,30,30,220);color:white;padding:8px 14px;border-radius:8px;")
        self.setAttribute(Qt.WA_TransientWindow)
        self.adjustSize()
        self.move((parent.width() - self.width()) // 2, parent.height() - self.height() - 24)
        self.show(); self.raise_()
        QTimer.singleShot(ms, self.deleteLater)

    @staticmethod
    def show_message(parent: QWidget, text: str) -> "Toast":
        return Toast(parent, text)
```

- [x] **Step 4: Çalıştır, PASS gör** — `pytest tests/test_ui_text_pane.py -v`

- [x] **Step 5: Başarısız ResultWindow testini yaz** — `tests/test_ui_result_window.py`

```python
from PySide6.QtCore import QObject, Signal
from dikte.core.state import DictationState, Session
from dikte.llm.tasks import Change
from dikte.ui.result_window import ResultWindow


class FakeController(QObject):
    state_changed = Signal(object); session_updated = Signal(object); error = Signal(str)
    def __init__(self):
        super().__init__(); self.translations, self.prompts = [], []
        self.session = Session()
    def request_translation(self, t): self.translations.append(t)
    def request_enhanced_prompt(self, t): self.prompts.append(t)


def make(qtbot):
    c = FakeController(); w = ResultWindow(); qtbot.addWidget(w); w.bind(c)
    return w, c


def test_session_fills_panes_and_changes(qtbot):
    w, c = make(qtbot)
    s = Session(raw_text="hava çuk güzel", corrected_text="Hava çok güzel.",
                changes=(Change("çuk", "çok", "yazım"),))
    c.session_updated.emit(s)
    assert w.raw_pane.text() == "hava çuk güzel"
    assert w.corrected_pane.text() == "Hava çok güzel."
    assert w.changes_list.count() == 1 and "çuk" in w.changes_list.item(0).text()


def test_translate_button_sends_current_corrected_text(qtbot):
    w, c = make(qtbot)
    w.corrected_pane.set_text("Merhaba dünya.")
    w.corrected_pane.editor.appendPlainText("Elle eklendi.")  # kullanıcı düzenlemesi
    w.translate_btn.click()
    assert c.translations == ["Merhaba dünya.\nElle eklendi."]
    assert w.output_pane.title_label.text() == "İngilizce Çeviri"
    assert not w.translate_btn.isEnabled()  # bekleme sırasında kilit


def test_enhance_button_sends_text_and_result_fills_output(qtbot):
    w, c = make(qtbot)
    w.corrected_pane.set_text("bana todo uygulaması yaz")
    w.enhance_btn.click()
    assert c.prompts == ["bana todo uygulaması yaz"]
    c.session_updated.emit(Session(enhanced_prompt="# Goal\nBuild a todo app"))
    assert w.output_pane.text().startswith("# Goal")
    assert w.output_pane.title_label.text() == "Agent Prompt (EN)"
    assert w.enhance_btn.isEnabled()


def test_result_state_shows_window(qtbot):
    w, c = make(qtbot)
    c.state_changed.emit(DictationState.RESULT)
    assert w.isVisible()


def test_close_hides_instead_of_quitting(qtbot):
    w, c = make(qtbot)
    w.show(); w.close()
    assert not w.isVisible() and w.isEnabled()
```

- [x] **Step 6: Çalıştır, FAIL gör** — `pytest tests/test_ui_result_window.py -v`

- [x] **Step 7: `result_window.py` yaz**

```python
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (QHBoxLayout, QListWidget, QMainWindow, QPushButton, QSplitter,
                               QStatusBar, QVBoxLayout, QWidget)

from dikte.core.state import DictationState, Session
from dikte.ui.text_pane import TextPane
from dikte.ui.toast import Toast

TITLE_TRANSLATION = "İngilizce Çeviri"
TITLE_PROMPT = "Agent Prompt (EN)"


class ResultWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Dikte")
        self.resize(1100, 620)
        self._controller = None
        self._pending: str | None = None  # "translation" | "enhanced_prompt"

        self.raw_pane = TextPane("Ham")
        self.corrected_pane = TextPane("Düzeltilmiş")
        self.output_pane = TextPane(TITLE_TRANSLATION)
        self.changes_list = QListWidget(); self.changes_list.setMaximumHeight(110)
        self.changes_list.setToolTip("LLM'in yaptığı düzeltmeler")

        self.translate_btn = QPushButton("İngilizce'ye Çevir")
        self.enhance_btn = QPushButton("Agent Prompt'a Dönüştür")
        self.translate_btn.clicked.connect(self._on_translate)
        self.enhance_btn.clicked.connect(self._on_enhance)

        left = QWidget(); ll = QVBoxLayout(left); ll.setContentsMargins(0, 0, 0, 0)
        ll.addWidget(self.raw_pane, 1)
        mid = QWidget(); ml = QVBoxLayout(mid); ml.setContentsMargins(0, 0, 0, 0)
        ml.addWidget(self.corrected_pane, 1); ml.addWidget(self.changes_list)
        split = QSplitter(Qt.Horizontal)
        for w in (left, mid, self.output_pane):
            split.addWidget(w)
        split.setSizes([330, 400, 370])

        buttons = QHBoxLayout(); buttons.addStretch(1)
        buttons.addWidget(self.translate_btn); buttons.addWidget(self.enhance_btn)
        root = QWidget(); rl = QVBoxLayout(root); rl.setContentsMargins(12, 12, 12, 12)
        rl.addWidget(split, 1); rl.addLayout(buttons)
        self.setCentralWidget(root)
        self.setStatusBar(QStatusBar())

        for pane in (self.raw_pane, self.corrected_pane, self.output_pane):
            pane.copied.connect(lambda _t, p=pane: self._on_copied(p))
        QShortcut(QKeySequence("Ctrl+Shift+C"), self, activated=self.corrected_pane._copy)

    # ---- bağlama
    def bind(self, controller) -> None:
        self._controller = controller
        controller.session_updated.connect(self.on_session)
        controller.state_changed.connect(self.on_state)
        controller.error.connect(self._on_error)

    # ---- slotlar
    def on_session(self, s: Session) -> None:
        self.raw_pane.set_text(s.raw_text)
        self.corrected_pane.set_text(s.corrected_text)
        self.changes_list.clear()
        for c in s.changes:
            self.changes_list.addItem(f"{c.original}  →  {c.replacement}   ({c.reason})")
        if self._pending == "translation" and s.translation:
            self.output_pane.set_text(s.translation); self._finish_pending()
        elif self._pending == "enhanced_prompt" and s.enhanced_prompt:
            self.output_pane.set_text(s.enhanced_prompt); self._finish_pending()

    def on_state(self, state: DictationState) -> None:
        if state is DictationState.RESULT:
            self.showNormal(); self.raise_(); self.activateWindow()
            self.corrected_pane.editor.setFocus()
        elif state is DictationState.RECORDING:
            self.output_pane.set_text(""); self._finish_pending()

    # ---- butonlar
    def _on_translate(self) -> None:
        text = self.corrected_pane.text().strip()
        if not text or self._controller is None:
            return
        self._start_pending("translation", TITLE_TRANSLATION)
        self._controller.request_translation(text)

    def _on_enhance(self) -> None:
        text = self.corrected_pane.text().strip()
        if not text or self._controller is None:
            return
        self._start_pending("enhanced_prompt", TITLE_PROMPT)
        self._controller.request_enhanced_prompt(text)

    def _start_pending(self, kind: str, title: str) -> None:
        self._pending = kind
        self.output_pane.title_label.setText(title)
        self.output_pane.set_text(""); self.output_pane.set_busy(True)
        self.translate_btn.setEnabled(False); self.enhance_btn.setEnabled(False)
        self.statusBar().showMessage("LLM çalışıyor…")

    def _finish_pending(self) -> None:
        self._pending = None
        self.output_pane.set_busy(False)
        self.translate_btn.setEnabled(True); self.enhance_btn.setEnabled(True)
        self.statusBar().clearMessage()

    def _on_copied(self, pane: TextPane) -> None:
        Toast.show_message(self, "Kopyalandı")
        if getattr(self, "close_after_copy", False) and pane is not self.raw_pane:
            self.hide()

    def _on_error(self, msg: str) -> None:
        self._finish_pending()
        self.statusBar().showMessage(msg, 8000)

    def closeEvent(self, event) -> None:  # pencere kapatma = gizle
        event.ignore()
        self.hide()
```

- [x] **Step 8: Çalıştır, PASS gör** — `pytest tests/test_ui_text_pane.py tests/test_ui_result_window.py -v`

- [x] **Step 9: Commit** — `git add -A && git commit -m "feat: result window with raw/corrected/output panes"`

---

### Task 9: Geçmiş (JSONL)

**Files:**
- Create: `src/dikte/core/history.py`
- Test: `tests/test_history.py`

**Interfaces:**
- Consumes: `Session` (Task 5).
- Produces: `History(path: Path, limit: int)`: `append(session: Session) -> None`, `load() -> tuple[Session, ...]` (en yeni en sonda).

- [x] **Step 1: Başarısız testi yaz** — `tests/test_history.py`

```python
from pathlib import Path
from dikte.core.history import History
from dikte.core.state import Session
from dikte.llm.tasks import Change


def test_append_and_load_roundtrip(tmp_path: Path):
    h = History(tmp_path / "h.jsonl", limit=10)
    s = Session(raw_text="a", corrected_text="A.", changes=(Change("a", "A.", "r"),), translation="x")
    h.append(s)
    loaded = h.load()
    assert len(loaded) == 1 and loaded[0].id == s.id and loaded[0].changes[0].reason == "r"


def test_limit_trims_oldest(tmp_path: Path):
    h = History(tmp_path / "h.jsonl", limit=2)
    for i in range(4):
        h.append(Session(raw_text=str(i)))
    assert [s.raw_text for s in h.load()] == ["2", "3"]


def test_corrupt_lines_are_skipped(tmp_path: Path):
    p = tmp_path / "h.jsonl"
    p.write_text('{"bad json\n', encoding="utf-8")
    h = History(p, limit=5)
    h.append(Session(raw_text="ok"))
    assert [s.raw_text for s in h.load()] == ["ok"]


def test_zero_limit_disables_history(tmp_path: Path):
    h = History(tmp_path / "h.jsonl", limit=0)
    h.append(Session(raw_text="x"))
    assert h.load() == ()
```

- [x] **Step 2: Çalıştır, FAIL gör** — `pytest tests/test_history.py -v`

- [x] **Step 3: `history.py` yaz**

```python
from __future__ import annotations

import json
import logging
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from dikte.core.state import Session
from dikte.llm.tasks import Change

log = logging.getLogger(__name__)


def _to_json(s: Session) -> str:
    d = asdict(s)
    d["created_at"] = s.created_at.isoformat()
    return json.dumps(d, ensure_ascii=False)


def _from_json(line: str) -> Session | None:
    try:
        d = json.loads(line)
        d["created_at"] = datetime.fromisoformat(d["created_at"])
        d["changes"] = tuple(Change(**c) for c in d.get("changes", ()))
        return Session(**d)
    except (ValueError, TypeError, KeyError) as exc:
        log.warning("geçmiş satırı atlandı: %s", exc)
        return None


class History:
    def __init__(self, path: Path, limit: int):
        self._path, self._limit = path, limit

    def load(self) -> tuple[Session, ...]:
        if self._limit <= 0 or not self._path.exists():
            return ()
        lines = self._path.read_text(encoding="utf-8").splitlines()
        sessions = [s for s in (_from_json(l) for l in lines if l.strip()) if s is not None]
        return tuple(sessions[-self._limit:])

    def append(self, session: Session) -> None:
        if self._limit <= 0:
            return
        kept = self.load()[-(self._limit - 1):] if self._limit > 1 else ()
        content = "\n".join(_to_json(s) for s in (*kept, session)) + "\n"
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(content, encoding="utf-8")
        tmp.replace(self._path)
```

- [x] **Step 4: Çalıştır, PASS gör** — `pytest tests/test_history.py -v`

- [x] **Step 5: Commit** — `git add -A && git commit -m "feat: JSONL session history"`

---

### Task 10: Otomatik başlatma ve tek örnek kilidi

**Files:**
- Create: `src/dikte/platform/autostart.py`, `src/dikte/platform/single_instance.py`
- Test: `tests/test_autostart.py`

**Interfaces:**
- Produces: `autostart.set_autostart(enabled: bool, exe_path: str | None = None, reg=None) -> None`, `autostart.is_autostart_enabled(reg=None) -> bool`, `autostart.launch_command() -> str`; `SingleInstance(name="dikte-single-instance")`: `try_acquire() -> bool`, `activated` sinyali (ikinci örnek başlatılınca ilk örneğe "show" mesajı gelir), `notify_existing() -> None`.

- [x] **Step 1: Başarısız autostart testini yaz** — `tests/test_autostart.py`

```python
from dikte.platform.autostart import RUN_KEY, VALUE_NAME, is_autostart_enabled, set_autostart


class FakeReg:
    """winreg'in kullanılan alt kümesi."""
    def __init__(self): self.values = {}
    def set_value(self, key, name, value): self.values[(key, name)] = value
    def get_value(self, key, name): return self.values.get((key, name))
    def delete_value(self, key, name): self.values.pop((key, name), None)


def test_enable_writes_run_value():
    r = FakeReg()
    set_autostart(True, exe_path=r"C:\Apps\Dikte\Dikte.exe", reg=r)
    assert r.values[(RUN_KEY, VALUE_NAME)] == '"C:\\Apps\\Dikte\\Dikte.exe" --minimized'
    assert is_autostart_enabled(reg=r)


def test_disable_removes_value():
    r = FakeReg()
    set_autostart(True, exe_path="x.exe", reg=r)
    set_autostart(False, reg=r)
    assert not is_autostart_enabled(reg=r)


def test_disable_when_absent_is_noop():
    r = FakeReg()
    set_autostart(False, reg=r)
    assert not is_autostart_enabled(reg=r)
```

- [x] **Step 2: Çalıştır, FAIL gör** — `pytest tests/test_autostart.py -v`

- [x] **Step 3: `autostart.py` ve `single_instance.py` yaz**

`src/dikte/platform/autostart.py`:
```python
from __future__ import annotations

import logging
import sys
from pathlib import Path

log = logging.getLogger(__name__)
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "Dikte"


class _WinReg:
    def __init__(self):
        import winreg
        self._w = winreg

    def set_value(self, key, name, value):
        with self._w.OpenKey(self._w.HKEY_CURRENT_USER, key, 0, self._w.KEY_SET_VALUE) as k:
            self._w.SetValueEx(k, name, 0, self._w.REG_SZ, value)

    def get_value(self, key, name):
        try:
            with self._w.OpenKey(self._w.HKEY_CURRENT_USER, key, 0, self._w.KEY_READ) as k:
                return self._w.QueryValueEx(k, name)[0]
        except FileNotFoundError:
            return None

    def delete_value(self, key, name):
        try:
            with self._w.OpenKey(self._w.HKEY_CURRENT_USER, key, 0, self._w.KEY_SET_VALUE) as k:
                self._w.DeleteValue(k, name)
        except FileNotFoundError:
            pass


def _reg(reg):
    if reg is not None:
        return reg
    if sys.platform != "win32":
        return None
    return _WinReg()


def launch_command(exe_path: str | None = None) -> str:
    if exe_path is not None:
        return f'"{exe_path}" --minimized'
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --minimized'
    pythonw = str(Path(sys.executable).with_name("pythonw.exe"))
    return f'"{pythonw}" -m dikte --minimized'


def set_autostart(enabled: bool, exe_path: str | None = None, reg=None) -> None:
    r = _reg(reg)
    if r is None:
        log.info("autostart yalnızca Windows'ta desteklenir")
        return
    if enabled:
        r.set_value(RUN_KEY, VALUE_NAME, launch_command(exe_path))
    else:
        r.delete_value(RUN_KEY, VALUE_NAME)


def is_autostart_enabled(reg=None) -> bool:
    r = _reg(reg)
    return bool(r and r.get_value(RUN_KEY, VALUE_NAME))
```

`src/dikte/platform/single_instance.py`:
```python
from __future__ import annotations

import logging

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

log = logging.getLogger(__name__)
SHOW_MESSAGE = b"show"


class SingleInstance(QObject):
    activated = Signal()

    def __init__(self, name: str = "dikte-single-instance", parent=None):
        super().__init__(parent)
        self._name = name
        self._server: QLocalServer | None = None

    def try_acquire(self) -> bool:
        sock = QLocalSocket()
        sock.connectToServer(self._name)
        if sock.waitForConnected(300):
            sock.write(SHOW_MESSAGE); sock.waitForBytesWritten(300); sock.disconnectFromServer()
            return False
        QLocalServer.removeServer(self._name)  # çökmüş önceki örnekten kalan soket
        self._server = QLocalServer(self)
        self._server.newConnection.connect(self._on_connection)
        if not self._server.listen(self._name):
            log.error("QLocalServer dinleyemedi: %s", self._server.errorString())
            return True  # kilit kurulamasa da çalışmaya devam et
        return True

    def _on_connection(self) -> None:
        conn = self._server.nextPendingConnection()
        if conn is None:
            return
        conn.waitForReadyRead(300)
        if conn.readAll().data().startswith(SHOW_MESSAGE):
            self.activated.emit()
        conn.disconnectFromServer()
```

- [x] **Step 4: Çalıştır, PASS gör** — `pytest tests/test_autostart.py -v`

- [x] **Step 5: Commit** — `git add -A && git commit -m "feat: autostart registry entry and single-instance lock"`

---

### Task 11: Ayarlar diyaloğu

**Files:**
- Create: `src/dikte/ui/settings_dialog.py`
- Test: `tests/test_settings_dialog.py`

**Interfaces:**
- Consumes: `Settings` (Task 1), `parse_hotkey` (Task 6).
- Produces: `SettingsDialog(settings: Settings, devices: tuple[tuple[int, str], ...], parent=None)`; `result_settings() -> Settings` (yeni nesne); `list_input_devices() -> tuple[tuple[int, str], ...]`.

- [x] **Step 1: Başarısız testi yaz** — `tests/test_settings_dialog.py`

```python
from dikte.config import Settings
from dikte.ui.settings_dialog import SettingsDialog

DEVICES = ((0, "Mikrofon A"), (3, "USB Mic"))


def test_dialog_populates_from_settings(qtbot):
    d = SettingsDialog(Settings(), DEVICES); qtbot.addWidget(d)
    assert d.hotkey_edit.text() == "ctrl+alt+space"
    assert d.provider_combo.currentText() == "ollama"
    assert d.device_combo.count() == 3  # "Sistem varsayılanı" + 2


def test_result_settings_returns_new_object_with_changes(qtbot):
    s = Settings()
    d = SettingsDialog(s, DEVICES); qtbot.addWidget(d)
    d.hotkey_edit.setText("ctrl+shift+d")
    d.device_combo.setCurrentIndex(2)
    d.autostart_check.setChecked(False)
    d.llm_model_edit.setText("gemma4:e4b-it-qat")
    out = d.result_settings()
    assert out is not s and s.hotkey == "ctrl+alt+space"
    assert out.hotkey == "ctrl+shift+d" and out.audio.device_index == 3
    assert out.autostart is False and out.llm.model == "gemma4:e4b-it-qat"


def test_invalid_hotkey_blocks_accept(qtbot):
    d = SettingsDialog(Settings(), DEVICES); qtbot.addWidget(d)
    d.hotkey_edit.setText("space")
    d.accept()
    assert d.result() != d.Accepted and "değiştirici" in d.error_label.text()
```

- [x] **Step 2: Çalıştır, FAIL gör** — `pytest tests/test_settings_dialog.py -v`

- [x] **Step 3: `settings_dialog.py` yaz**

```python
from __future__ import annotations

import logging

from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
                               QLabel, QLineEdit, QSpinBox, QVBoxLayout)

from dikte.config import Settings
from dikte.platform.hotkey_parse import HotkeyParseError, parse_hotkey

log = logging.getLogger(__name__)


def list_input_devices() -> tuple[tuple[int, str], ...]:
    try:
        import sounddevice as sd
        return tuple((i, d["name"]) for i, d in enumerate(sd.query_devices())
                     if d.get("max_input_channels", 0) > 0)
    except Exception:
        log.exception("ses cihazları listelenemedi")
        return ()


class SettingsDialog(QDialog):
    def __init__(self, settings: Settings, devices: tuple[tuple[int, str], ...], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Dikte Ayarları")
        self._settings = settings
        form = QFormLayout()

        self.hotkey_edit = QLineEdit(settings.hotkey)
        self.hotkey_edit.setPlaceholderText("ör. ctrl+alt+space")
        self.device_combo = QComboBox()
        self.device_combo.addItem("Sistem varsayılanı", None)
        for idx, name in devices:
            self.device_combo.addItem(name, idx)
        if settings.audio.device_index is not None:
            pos = self.device_combo.findData(settings.audio.device_index)
            self.device_combo.setCurrentIndex(max(pos, 0))
        self.stt_model_edit = QLineEdit(settings.stt.model)
        self.compute_combo = QComboBox(); self.compute_combo.addItems(["float16", "int8_float16", "int8"])
        self.compute_combo.setCurrentText(settings.stt.compute_type)
        self.provider_combo = QComboBox(); self.provider_combo.addItems(["ollama", "anthropic"])
        self.provider_combo.setCurrentText(settings.llm.provider)
        self.llm_model_edit = QLineEdit(settings.llm.model)
        self.ollama_host_edit = QLineEdit(settings.llm.ollama_host)
        self.autostart_check = QCheckBox("Windows ile başlat"); self.autostart_check.setChecked(settings.autostart)
        self.close_after_copy_check = QCheckBox("Kopyaladıktan sonra pencereyi gizle")
        self.close_after_copy_check.setChecked(settings.close_after_copy)
        self.history_spin = QSpinBox(); self.history_spin.setRange(0, 5000); self.history_spin.setValue(settings.history_limit)
        self.error_label = QLabel(""); self.error_label.setStyleSheet("color:#E53935;")

        form.addRow("Kısayol (toggle)", self.hotkey_edit)
        form.addRow("Mikrofon", self.device_combo)
        form.addRow("STT modeli", self.stt_model_edit)
        form.addRow("STT compute_type", self.compute_combo)
        form.addRow("LLM sağlayıcı", self.provider_combo)
        form.addRow("LLM modeli", self.llm_model_edit)
        form.addRow("Ollama host", self.ollama_host_edit)
        form.addRow("Geçmiş kayıt sayısı", self.history_spin)
        form.addRow(self.autostart_check)
        form.addRow(self.close_after_copy_check)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self); lay.addLayout(form); lay.addWidget(self.error_label); lay.addWidget(buttons)

    def accept(self) -> None:
        try:
            parse_hotkey(self.hotkey_edit.text())
        except HotkeyParseError as exc:
            self.error_label.setText(str(exc))
            return
        if not self.llm_model_edit.text().strip() or not self.stt_model_edit.text().strip():
            self.error_label.setText("Model adları boş olamaz")
            return
        super().accept()

    def result_settings(self) -> Settings:
        s = self._settings
        return s.model_copy(update={
            "hotkey": self.hotkey_edit.text().strip().lower(),
            "autostart": self.autostart_check.isChecked(),
            "close_after_copy": self.close_after_copy_check.isChecked(),
            "history_limit": self.history_spin.value(),
            "stt": s.stt.model_copy(update={"model": self.stt_model_edit.text().strip(),
                                            "compute_type": self.compute_combo.currentText()}),
            "llm": s.llm.model_copy(update={"provider": self.provider_combo.currentText(),
                                            "model": self.llm_model_edit.text().strip(),
                                            "ollama_host": self.ollama_host_edit.text().strip()}),
            "audio": s.audio.model_copy(update={"device_index": self.device_combo.currentData()}),
        })
```

- [x] **Step 4: Çalıştır, PASS gör** — `pytest tests/test_settings_dialog.py -v`

- [x] **Step 5: Commit** — `git add -A && git commit -m "feat: settings dialog"`

---

### Task 12: Tray, uygulama girişi ve composition root

**Files:**
- Create: `src/dikte/ui/tray.py`, `src/dikte/app.py`
- Modify: `src/dikte/ui/result_window.py` (`close_after_copy` özelliğini `bind` içinde ayarla — aşağıda)

**Interfaces:**
- Consumes: her şey.
- Produces: `TrayIcon(QSystemTrayIcon)`: `set_state(state: DictationState)`, `set_ready(bool)`, `notify(title, msg)`, sinyaller `show_requested`, `toggle_requested`, `settings_requested`, `quit_requested`; `app.main(argv=None) -> int`; `app.build_app(settings) -> AppContext`.

- [x] **Step 1: `tray.py` yaz**

```python
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from dikte.core.state import DictationState
from dikte.ui.icons import make_tray_icon

_ICON_STATE = {DictationState.IDLE: "idle", DictationState.RESULT: "idle",
               DictationState.RECORDING: "recording", DictationState.TRANSCRIBING: "busy",
               DictationState.CORRECTING: "busy"}


class TrayIcon(QSystemTrayIcon):
    show_requested = Signal()
    toggle_requested = Signal()
    settings_requested = Signal()
    quit_requested = Signal()

    def __init__(self, hotkey_label: str, parent=None):
        super().__init__(make_tray_icon("idle"), parent)
        self._hotkey_label = hotkey_label
        self._ready = False
        menu = QMenu()
        self._toggle_action = QAction("Kaydı Başlat", menu)
        self._toggle_action.triggered.connect(self.toggle_requested)
        show = QAction("Pencereyi Göster", menu); show.triggered.connect(self.show_requested)
        settings = QAction("Ayarlar…", menu); settings.triggered.connect(self.settings_requested)
        quit_ = QAction("Çıkış", menu); quit_.triggered.connect(self.quit_requested)
        for a in (self._toggle_action, show, settings):
            menu.addAction(a)
        menu.addSeparator(); menu.addAction(quit_)
        self.setContextMenu(menu)
        self.activated.connect(self._on_activated)
        self.set_state(DictationState.IDLE)

    def set_hotkey_label(self, label: str) -> None:
        self._hotkey_label = label
        self._refresh_tooltip("Hazır" if self._ready else "Model yükleniyor…")

    def set_ready(self, ready: bool) -> None:
        self._ready = ready
        self._refresh_tooltip("Hazır" if ready else "Model yükleniyor…")

    def set_state(self, state: DictationState) -> None:
        self.setIcon(make_tray_icon(_ICON_STATE[state]))
        self._toggle_action.setText("Kaydı Durdur" if state is DictationState.RECORDING else "Kaydı Başlat")
        self._toggle_action.setEnabled(state not in (DictationState.TRANSCRIBING, DictationState.CORRECTING))
        labels = {DictationState.RECORDING: "Kaydediliyor", DictationState.TRANSCRIBING: "Yazıya dökülüyor",
                  DictationState.CORRECTING: "Düzeltiliyor"}
        if state in labels:
            self._refresh_tooltip(labels[state])
        else:
            self.set_ready(self._ready)

    def notify(self, title: str, msg: str, critical: bool = False) -> None:
        icon = QSystemTrayIcon.Critical if critical else QSystemTrayIcon.Information
        self.showMessage(title, msg, icon, 4000)

    def _refresh_tooltip(self, status: str) -> None:
        self.setToolTip(f"Dikte — {status}\nKısayol: {self._hotkey_label}")

    def _on_activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.show_requested.emit()
```

- [x] **Step 2: `result_window.py` içindeki `bind` metodunu güncelle** — `close_after_copy` bayrağını controller'dan değil ayarlardan alması için imzayı `bind(controller, close_after_copy: bool = False)` yap ve gövdeye `self.close_after_copy = close_after_copy` ekle. `tests/test_ui_result_window.py` çalışmaya devam etmelidir (`pytest tests/test_ui_result_window.py -q`).

- [x] **Step 3: `app.py` yaz**

```python
from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass

from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon

from dikte import APP_NAME, __version__, paths
from dikte.audio.recorder import AudioRecorder
from dikte.config import Settings, load_settings, save_settings
from dikte.core.controller import DictationController
from dikte.core.history import History
from dikte.core.state import DictationState
from dikte.llm import LlmError, make_provider
from dikte.logging_setup import setup_logging
from dikte.platform.autostart import set_autostart
from dikte.platform.hotkey import GlobalHotkey
from dikte.platform.hotkey_parse import parse_hotkey
from dikte.platform.single_instance import SingleInstance
from dikte.stt.engine import FasterWhisperEngine
from dikte.ui.overlay import RecordingOverlay
from dikte.ui.result_window import ResultWindow
from dikte.ui.settings_dialog import SettingsDialog, list_input_devices
from dikte.ui.tray import TrayIcon

log = logging.getLogger(__name__)


@dataclass
class AppContext:
    settings: Settings
    controller: DictationController
    tray: TrayIcon
    overlay: RecordingOverlay
    window: ResultWindow
    hotkey: GlobalHotkey
    history: History


class _NullLlm:
    name = "none"
    def complete(self, *a, **k):
        raise LlmError("LLM sağlayıcı yapılandırılamadı; Ayarlar'dan kontrol edin")


def _make_llm(settings: Settings):
    try:
        return make_provider(settings.llm)
    except LlmError as exc:
        log.error("LLM sağlayıcı oluşturulamadı: %s", exc)
        return _NullLlm()


def build_app(settings: Settings) -> AppContext:
    recorder = AudioRecorder(settings.audio)
    stt = FasterWhisperEngine(settings.stt)
    controller = DictationController(settings, recorder=recorder, stt=stt, llm=_make_llm(settings),
                                     pool=QThreadPool.globalInstance())
    hotkey = GlobalHotkey()
    tray = TrayIcon(parse_hotkey(settings.hotkey).label)
    overlay = RecordingOverlay()
    window = ResultWindow()
    history = History(paths.history_path(), settings.history_limit)
    ctx = AppContext(settings, controller, tray, overlay, window, hotkey, history)
    _wire(ctx)
    return ctx


def _wire(ctx: AppContext) -> None:
    c = ctx.controller
    ctx.window.bind(c, close_after_copy=ctx.settings.close_after_copy)
    c.state_changed.connect(ctx.overlay.on_state)
    c.buckets_changed.connect(ctx.overlay.on_buckets)
    c.state_changed.connect(ctx.tray.set_state)
    c.ready_changed.connect(ctx.tray.set_ready)
    c.error.connect(lambda m: ctx.tray.notify(APP_NAME, m, critical=True))
    c.state_changed.connect(lambda s: s is DictationState.RESULT and ctx.history.append(c.session))
    ctx.hotkey.activated.connect(c.toggle)
    ctx.tray.toggle_requested.connect(c.toggle)
    ctx.tray.show_requested.connect(lambda: (ctx.window.showNormal(), ctx.window.raise_(), ctx.window.activateWindow()))
    ctx.tray.settings_requested.connect(lambda: _open_settings(ctx))
    ctx.tray.quit_requested.connect(lambda: _quit(ctx))


def _apply_hotkey(ctx: AppContext) -> None:
    if not ctx.hotkey.register(ctx.settings.hotkey):
        ctx.tray.notify(APP_NAME, f"Kısayol kaydedilemedi: {ctx.settings.hotkey}. "
                                  "Başka bir uygulama kullanıyor olabilir.", critical=True)
    ctx.tray.set_hotkey_label(ctx.hotkey.label or ctx.settings.hotkey)


def _open_settings(ctx: AppContext) -> None:
    dlg = SettingsDialog(ctx.settings, list_input_devices(), ctx.window)
    if dlg.exec() != SettingsDialog.Accepted:
        return
    new = dlg.result_settings()
    save_settings(new)
    needs_restart = new.stt != ctx.settings.stt or new.audio != ctx.settings.audio or new.llm != ctx.settings.llm
    ctx.settings = new
    set_autostart(new.autostart)
    ctx.controller.update_settings(new)
    ctx.window.close_after_copy = new.close_after_copy
    _apply_hotkey(ctx)
    if needs_restart:
        QMessageBox.information(ctx.window, APP_NAME,
                                "Model / ses / LLM ayarları uygulamayı yeniden başlatınca etkin olur.")


def _quit(ctx: AppContext) -> None:
    ctx.hotkey.unregister()
    ctx.tray.hide()
    QApplication.instance().quit()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="dikte")
    parser.add_argument("--minimized", action="store_true", help="pencere açmadan tray'de başla")
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {__version__}")
    args = parser.parse_args(argv)

    setup_logging()
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setQuitOnLastWindowClosed(False)

    single = SingleInstance()
    if not single.try_acquire():
        log.info("zaten çalışıyor, mevcut örneğe sinyal gönderildi")
        return 0
    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.critical(None, APP_NAME, "Sistem tepsisi bulunamadı.")
        return 1

    settings = load_settings()
    ctx = build_app(settings)
    single.activated.connect(ctx.tray.show_requested)
    ctx.tray.show()
    _apply_hotkey(ctx)
    set_autostart(settings.autostart)
    ctx.controller.warm_up()
    if not args.minimized:
        ctx.window.show()
    log.info("%s %s başladı", APP_NAME, __version__)
    return app.exec()
```

- [x] **Step 4: Duman testi (Linux'ta offscreen)**

Run: `QT_QPA_PLATFORM=offscreen python -c "from dikte.app import build_app; from dikte.config import Settings; from PySide6.QtWidgets import QApplication; a=QApplication([]); ctx=build_app(Settings()); print(type(ctx.controller).__name__)"`
Expected: `DictationController` yazdırır, istisna yok (STT modeli yüklenmez; `warm_up` çağrılmadı).

- [x] **Step 5: Tüm testleri çalıştır** — `pytest -v` → tümü PASS (gpu/win skip)

- [x] **Step 6: Commit** — `git add -A && git commit -m "feat: tray icon and application composition root"`

---

### Task 13: Windows'ta uçtan uca doğrulama ve model ön-indirme

**Files:**
- Create: `docs/manual_test_checklist.md`, `scripts/download_models.py`
- Modify: `README.md`

**Interfaces:** Yok (doğrulama görevi). Bu task **Windows 11 + RTX 3060 Ti** makinede yapılır.

- [ ] **Step 1: Ön koşulları kur (Windows)**

```powershell
winget install --id Python.Python.3.11 -e
winget install --id Ollama.Ollama -e
ollama pull qwen3.5:4b
ollama pull gemma4:e4b-it-qat
py -3.11 -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -U pip uv
uv pip install -e ".[dev,cuda]"
```
NVIDIA sürücüsü CUDA 12 uyumlu olmalı (≥ 525). Ayrı CUDA Toolkit kurulumu gerekmez; cuBLAS/cuDNN pip wheel'leri `cuda_dlls.register_nvidia_dll_dirs()` ile yüklenir.

- [ ] **Step 2: `scripts/download_models.py` yaz ve çalıştır**

```python
"""STT modelini ilk çalıştırmadan önce indirir (kurulum sonrası / build öncesi)."""
from dikte import paths
from dikte.cuda_dlls import register_nvidia_dll_dirs
from faster_whisper import WhisperModel

register_nvidia_dll_dirs()
m = WhisperModel("large-v3-turbo", device="cuda", compute_type="float16",
                 download_root=str(paths.models_dir()))
print("OK, model dizini:", paths.models_dir())
```
Run: `python scripts/download_models.py` → "OK" ve ≈ 1.6 GB indirme. `large-v3-turbo` adı çözülmezse (eski faster-whisper), model adı yerine `deepdml/faster-whisper-large-v3-turbo-ct2` kullan ve `SttSettings.model` varsayılanını buna çevir.

- [ ] **Step 3: GPU testini çalıştır** — `pytest -m gpu -v` → PASS

- [ ] **Step 3b: Türkçe LLM A/B testi — `scripts/eval_llm.py` yaz ve çalıştır**

```python
"""qwen3.5:4b ve gemma4:e4b-it-qat'i Türkçe STT-hatası düzeltmede karşılaştırır."""
import json, sys, time

from dikte.config import LlmSettings
from dikte.llm.ollama_provider import OllamaProvider
from dikte.llm.tasks import correct

SAMPLES = [
    "bugün hava çuk güzel dışarı çıkalım mı",
    "projeyi git hapa pushladım pull rikuest açar mısın",
    "toplantıyı yarın saat on beşe ertele yelim lütfen",
    "bu fonksiyonda nul pointer hatası alıyorum bak abilir misin",
    "faster whisper modelini large turbo ya güncelle",
    "kullanıcı giriş ekranında şifre alanı boş bırakılınca uyarı vermiyor",
    "docker kompoz dosyasında port çakışması var sanırım",
    "rapor u pdf olarak dışa aktar butonu ekle",
    "veri tabanı migrasyonunu geri almak için komut nedir",
    "bu promptu ingilizceye çevirip agent a ver",
]
MODELS = sys.argv[1:] or ["qwen3.5:4b", "gemma4:e4b-it-qat"]

for model in MODELS:
    p = OllamaProvider(LlmSettings(model=model))
    print(f"\n=== {model} ===")
    total = 0.0
    for raw in SAMPLES:
        t0 = time.perf_counter()
        res = correct(p, raw)
        dt = time.perf_counter() - t0
        total += dt
        print(f"[{dt:4.1f}s] {raw}\n        -> {res.corrected_text}")
        for c in res.changes:
            print(f"           {c.original} -> {c.replacement} ({c.reason})")
    print(f"toplam {total:.1f}s, ort. {total/len(SAMPLES):.1f}s/cümle")
```
Run: `python scripts/eval_llm.py`
Expected: iki model için de 10 çıktı; ilk istek model yüklemesi nedeniyle uzun, sonrakiler < 3 s. Daha doğal Türkçe üreten ve daha az yanlış "düzeltme" yapan model `SttSettings` değil `LlmSettings.model` varsayılanı olarak seçilir; Ollama VRAM kullanımı `nvidia-smi` ile not edilir (Whisper + LLM toplamı < 7.5 GB olmalı).

- [ ] **Step 4: Uygulamayı çalıştır ve manuel kontrol listesini uygula** — `python -m dikte`

`docs/manual_test_checklist.md`:
```markdown
# Manuel Test Kontrol Listesi (Windows 11)

- [ ] Uygulama açılınca tray ikonu görünür, tooltip "Model yükleniyor…" → ~10 s içinde "Hazır".
- [ ] Ctrl+Alt+Space → ekran alt-ortasında overlay; konuşunca dalga çubukları hareket eder; kırmızı nokta 0,5 s aralıkla yanıp söner; süre sayar.
- [ ] Ctrl+Alt+Space (ikinci) → overlay "Yazıya dökülüyor…" sonra "Düzeltiliyor…", ardından sonuç penceresi öne gelir.
- [ ] 20 s'lik Türkçe kayıt için STT + düzeltme toplam < 8 s.
- [ ] Ham ve Düzeltilmiş pane'ler dolu; değişiklik listesi mantıklı ("çuk → çok").
- [ ] Düzeltilmiş pane elle düzenlenebilir; sağ üst kopyala → "Kopyalandı" toast'ı; Notepad'e yapıştırınca aynı metin.
- [ ] "İngilizce'ye Çevir" → üçüncü pane başlığı "İngilizce Çeviri", içerik İngilizce; butonlar işlem sırasında kilitli.
- [ ] "Agent Prompt'a Dönüştür" → "# Goal" ile başlayan İngilizce Markdown prompt; kopyalanabilir.
- [ ] Sonuç penceresi açıkken Ctrl+Alt+Space → yeni kayıt başlar, pane'ler temizlenir.
- [ ] Transkripsiyon sırasında kısayol yok sayılır.
- [ ] Pencereyi X ile kapat → tray'de kalır; tray çift tık → pencere geri gelir.
- [ ] İkinci kez `python -m dikte` → yeni örnek açılmaz, mevcut pencere öne gelir.
- [ ] Ollama kapalıyken kayıt → tray'de kırmızı bildirim, ham metin yine de gösterilir (düzeltilmiş = ham).
- [ ] Mikrofon yokken kayıt → hata bildirimi, IDLE'a döner.
- [ ] Ayarlar → kısayolu ctrl+shift+d yap → yeni kısayol anında çalışır; regedit HKCU\...\Run altında "Dikte" değeri var/yok toggle'a göre.
- [ ] Oturumu kapat/aç → uygulama tray'de otomatik başlar (`--minimized`).
- [ ] %APPDATA%\Dikte\history.jsonl her sonuçtan sonra bir satır büyür.
- [ ] `nvidia-smi`: boşta VRAM ≈ 1,6 GB (Whisper) + Ollama ≈ 3,5–4,5 GB (4B model); toplam < 7,5 GB, CPU offload yok (`ollama ps` → "100% GPU").
```

- [ ] **Step 5: Bulunan hataları düzelt, ilgili birim testini ekle, commit et** — `git commit -m "fix: <bulgu>"` (her düzeltme ayrı commit).

- [ ] **Step 6: README.md'yi kurulum ve kullanım adımlarıyla güncelle, commit** — `git commit -m "docs: README and manual test checklist"`

---

### Task 14: Paketleme (PyInstaller + Inno Setup)

**Files:**
- Create: `packaging/dikte.spec`, `packaging/installer.iss`, `packaging/build.ps1`, `packaging/dikte.ico` (make_tray_icon'dan `QIcon.pixmap(256).save("dikte.png")` ile üretilip `.ico`'ya çevrilir)

**Interfaces:** Yok. Çıktı: `dist/Dikte/Dikte.exe` (onedir) ve `dist/Dikte-Setup-0.1.0.exe`.

- [x] **Step 1: `packaging/dikte.spec` yaz**

```python
# -*- mode: python -*-
from PyInstaller.utils.hooks import collect_all, collect_dynamic_libs

datas, binaries, hiddenimports = [], [], []
for pkg in ("faster_whisper", "ctranslate2", "ollama", "sounddevice", "av"):
    d, b, h = collect_all(pkg)
    datas += d; binaries += b; hiddenimports += h
for pkg in ("nvidia.cublas", "nvidia.cudnn"):
    binaries += collect_dynamic_libs(pkg)

a = Analysis(
    ["../src/dikte/__main__.py"],
    pathex=["../src"],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports + ["dikte.app", "PySide6.QtNetwork"],
    excludes=["tkinter", "matplotlib", "PySide6.QtWebEngineCore", "PySide6.Qt3DCore"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Dikte", console=False,
          icon="dikte.ico", version=None)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="Dikte")
```

- [x] **Step 2: `packaging/installer.iss` yaz**

```ini
#define AppName "Dikte"
#define AppVersion "0.1.0"
[Setup]
AppId={{7B1C0E52-3D7A-4B54-9C8F-2E1D6A5F0D1E}
AppName={#AppName}
AppVersion={#AppVersion}
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=Dikte-Setup-{#AppVersion}
Compression=lzma2/ultra64
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
SetupIconFile=dikte.ico
[Files]
Source: "..\dist\Dikte\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion
[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\Dikte.exe"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\Dikte.exe"; Tasks: desktopicon
[Tasks]
Name: "desktopicon"; Description: "Masaüstü kısayolu oluştur"; Flags: unchecked
[Run]
Filename: "{app}\Dikte.exe"; Description: "{#AppName} uygulamasını başlat"; Flags: nowait postinstall skipifsilent
[UninstallRun]
Filename: "reg.exe"; Parameters: "delete HKCU\Software\Microsoft\Windows\CurrentVersion\Run /v Dikte /f"; Flags: runhidden; RunOnceId: "RemoveAutostart"
```

- [x] **Step 3: `packaging/build.ps1` yaz**

```powershell
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..
.\.venv\Scripts\Activate.ps1
pytest -q
pyinstaller --noconfirm --clean packaging\dikte.spec
& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" packaging\installer.iss
Write-Host "Kurulum paketi: dist\Dikte-Setup-0.1.0.exe"
```

- [ ] **Step 4: Build al ve temiz bir Windows kullanıcı hesabında doğrula**

Run: `powershell -ExecutionPolicy Bypass -File packaging\build.ps1`
Expected: `dist\Dikte\Dikte.exe` çalışır; kısayol, overlay, STT (GPU), Ollama düzeltmesi çalışır; `dist\Dikte-Setup-0.1.0.exe` kurulumu sonrası `docs/manual_test_checklist.md` listesi tekrar geçilir. Model ilk açılışta `%LOCALAPPDATA%\Dikte\models` altına iner (ilk açılışta tooltip "Model yükleniyor…" birkaç dakika sürebilir).

- [x] **Step 5: Commit** — `git add -A && git commit -m "chore: PyInstaller spec and Inno Setup installer"`

---

## Bölüm 3 — Riskler ve Kararlar

| Risk | Karar / Önlem |
|---|---|
| Whisper + LLM aynı anda 8 GB VRAM'e sığmayabilir | Whisper fp16 ≈ 1.6 GB + qwen3.5:4b ≈ 3.8 GB. `num_ctx=8192` ile KV küçük tutulur. Sığmazsa: `compute_type="int8_float16"` veya `qwen3.5:2b`. 9B/12B modeller bu kartta CPU offload'a düşer, önerilmez. |
| `large-v3-turbo` model adı faster-whisper sürümüne göre çözülmeyebilir | Task 13 Step 2'de HF repo adı fallback'i tanımlı. |
| cuDNN/cuBLAS DLL bulunamıyor | `cuda_dlls.register_nvidia_dll_dirs()` model yüklemeden önce çağrılır; PyInstaller spec DLL'leri paketler. |
| RegisterHotKey başka uygulama tarafından alınmış | `register()` False döner, tray bildirimi çıkar; Ayarlar'dan farklı kombinasyon seçilir. |
| İlk açılışta model indirme (1.6 GB) | Tray tooltip "Model yükleniyor…"; `scripts/download_models.py` ile ön-indirme. |
| Ollama çalışmıyor | LLM hatası kullanıcıya bildirilir; ham metin yine gösterilir (Task 5 `_on_llm_error`). |
| Windows Service beklentisi | Session 0 izolasyonu nedeniyle UI mümkün değil; HKCU Run + single-instance tray ile "hep açık" davranışı sağlanır. |
| Türkçe LLM kalitesi | qwen3.5:4b ve gemma4:e4b-it-qat MMMLU'da eşdeğer (76.1 / 76.6); Türkçe'ye özel yayınlanmış kıyas yok, Task 13 A/B betiği karar verir. Düşük temperature + JSON şema halüsinasyonu sınırlar; `changes` listesi şeffaflık verir. |
| Qwen3.5 thinking modu JSON'u bozar / gecikme ekler | `OllamaProvider` her çağrıda `think=False` gönderir; Ollama ≥ 0.9 gerekir. |

## Bölüm 4 — Yürütme Sırası ve Süre Tahmini (agent başına)

| Görevler | Bağımlılık | Tahmini süre |
|---|---|---|
| 1 → 2 → 3 → 4 | sıralı | 2 saat |
| 5 | 2, 3, 4 | 45 dk |
| 6, 7, 9, 10, 11 | 1 (birbirinden bağımsız, paralel yapılabilir) | toplam 2 saat |
| 8 | 5, 7 | 1 saat |
| 12 | hepsi | 45 dk |
| 13 | 12 (Windows + GPU gerekir) | 2 saat |
| 14 | 13 | 1 saat |

Linux/WSL üzerinde Task 1–12 tamamen geliştirilip test edilebilir; Task 13–14 Windows makinede yapılır.
