# AGENTS.md — Dikte

<!-- LAST-SYNCED: 2026-09-15 -->

Kodlama ajanları için çalışma kılavuzu. Kullanıcıya dönük anlatım `README.md`'dedir;
burada yalnızca komutlar, sınırlar ve sözleşmeler var.

## Proje

Türkçe odaklı, tamamen yerel masaüstü diktasyon uygulaması (Windows 11 birincil, Linux
ikincil). Kısayol → kayıt → GPU'da faster-whisper ile STT → isteğe bağlı LLM düzeltmesi →
metin panoya yazılır ve aktif pencereye yapıştırılır.

## Teknoloji (pyproject.toml'dan)

Python 3.11–3.12 · PySide6 ≥ 6.7 · faster-whisper ≥ 1.1 · ctranslate2 ≥ 4.5 ·
sounddevice · numpy · ollama ≥ 0.4 · pydantic ≥ 2.7
İsteğe bağlı extra'lar: `cuda`, `anthropic`, `openai`, `gemini`, `dev`.

## Komutlar

```bash
uv pip install -e ".[dev]"                          # Windows'ta ".[dev,cuda]"
.venv/bin/python -m pytest -q                       # tüm testler
.venv/bin/python -m pytest -q --cov=src --cov-report=term-missing
.venv/bin/python -m pytest -m gpu                   # CUDA gerektirir
.venv/bin/ruff check src tests scripts              # CI ile aynı kapsam
.venv/bin/ruff format --check src tests scripts
python -m dikte                                     # uygulamayı çalıştır
python scripts/download_models.py                   # Whisper modelini indirir
python scripts/eval_llm.py --models <model…>        # Türkçe LLM benchmark'ı
```

Başsız ortamda Qt testleri `QT_QPA_PLATFORM=offscreen` ister (CI bunu ayarlar).
Sistem Python'u kullanılmaz; her zaman `.venv/bin/python`.

## Mimari haritası

| Dizin | Sorumluluk |
|---|---|
| `src/dikte/core/` | `DictationController` durum makinesi, `Session`, geçmiş (JSONL), thread-pool worker'ları |
| `src/dikte/audio/` | `sounddevice` kaydı (16 kHz mono float32), seviye ölçümü |
| `src/dikte/stt/` | faster-whisper motoru, VAD ön-kontrolü, halüsinasyon filtresi |
| `src/dikte/llm/` | `LlmProvider` protokolü + altı sağlayıcı, promptlar, görevler, anahtar okuma |
| `src/dikte/platform/` | Global kısayol, yapıştırma, otomatik başlatma, tek örnek/IPC |
| `src/dikte/ui/` | Tray, overlay, sonuç penceresi, geçmiş paneli, `settings/` sekmeleri |
| `scripts/`, `packaging/`, `docs/` | Yardımcı betikler, PyInstaller/Inno + Linux kurulumu, belgeler |

Giriş noktaları: `python -m dikte` (`src/dikte/__main__.py`) ve `dikte` konsol betiği
(`dikte.app:main`). `dikte --toggle` çalışan örneğe IPC ile komut yollar.

## Sözleşmeler

- **TDD zorunlu:** önce başarısız test, sonra en küçük uygulama, sonra commit.
  Kapsam ≥ %80 (bugün %91, 326 test). Conventional Commits, Türkçe mesaj.
- **Değişmezlik:** pydantic modelleri `frozen=True`; değişiklik yalnızca
  `model_copy(update=...)` ile. Yerinde mutasyon yok.
- **Enjekte edilebilir dış dünya:** GPU, ağ ve SDK erişimleri `*_factory` / `*_probe`
  parametreleriyle verilir ki testler GPU'suz ve SDK'sız CI'da geçsin.

```python
# İYİ — test edilebilir, değişmez
def transcribe(self, audio, *, speech_probe=_default_speech_probe): ...
new = settings.model_copy(update={"provider": "lmstudio"})

# KÖTÜ — gizli bağımlılık + mutasyon
def transcribe(self, audio):
    model = WhisperModel(...)          # doğrudan kurar, test edilemez
settings.provider = "lmstudio"          # frozen model; mutasyon yasak
```

- Yeni ayar alanı eklerken **varsayılan değer** ver: eski `config.json` dosyaları
  doğrulamadan geçmeye devam etmeli.
- Kullanıcıya görünen tüm metinler Türkçe ve tam diakritikli; kod tanımlayıcıları İngilizce.
- Hatalar sessizce yutulmaz; kullanıcıya ne yapacağını söyleyen mesaj + `log.exception`.

## Dikkatli değiştirilecek dosyalar

| Dosya | Neden |
|---|---|
| `src/dikte/config.py` | Tüm ayar şeması; alan silmek eski config'leri bozar |
| `src/dikte/core/controller.py` | Durum makinesi ve iptal kuşak sayacı; yarış koşullarına açık |
| `src/dikte/stt/engine.py` | VAD/batch etkileşimi — VAD kapalıyken toplu çözümleme çalışmaz |
| `src/dikte/llm/keys.py` | Anahtar sınırı; değeri asla döndürmez/loglamaz |
| `src/dikte/ui/settings_dialog.py` | `_PROXIED` tablosu sekme widget'larını dışarı açar |

## Asla

- API anahtarı, parola veya token'ı koda ya da `config.json`'a yazma. Yalnızca ortam
  değişkeni adı saklanır; arayüzde yalnızca "✓ tanımlı / ✗ yok" gösterilir.
- CPU'ya geri dönüş ekleme: STT GPU zorunludur (ürün kararı).
- Çekirdek bağımlılıkları büyütme; yeni SDK'lar `pyproject.toml`'da isteğe bağlı extra olur.
- Kullanıcı onayı almadan `ollama pull` çalıştırma (benchmark aday listesi kuralı,
  `docs/llm_benchmark.md`).
- `.venv/`, `dist/`, `build/`, `__pycache__` içeriğini düzenleme veya commit'leme.
