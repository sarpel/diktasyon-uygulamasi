# Katkı rehberi

Dikte'ye katkı vermek istediğiniz için teşekkürler. Bu belge geliştirme ortamını, projenin
yapısını ve bir değişikliğin kabul edilmesi için gerekenleri anlatır. Issue ve PR'lar Türkçe veya
İngilizce olabilir.

> Kodlama ajanları (Claude Code, Codex vb.) için kısa kurallar [AGENTS.md](AGENTS.md) dosyasındadır.

## Geliştirme ortamı

```bash
git clone https://github.com/sarpel/diktasyon-uygulamasi.git
cd diktasyon-uygulamasi
uv venv --python 3.11 .venv
uv pip install -e ".[dev]"          # Windows'ta ve gerçek GPU testleri için: ".[dev,cuda]"
```

Linux'ta Qt ve ses için sistem kütüphaneleri gerekir (CI'daki liste):

```bash
sudo apt install libegl1 libgl1 libglib2.0-0 libdbus-1-3 libxkbcommon0 libxcb-cursor0 \
  libxcb-icccm4 libxcb-keysyms1 libxcb-shape0 libportaudio2
```

Her zaman sanal ortamdaki yorumlayıcıyı kullanın (`.venv/bin/python`, Windows'ta
`.venv\Scripts\python`); sistem Python'u kullanılmaz.

## Komutlar

```bash
.venv/bin/python -m pytest -q                                        # tüm testler
.venv/bin/python -m pytest -q --cov=src --cov-report=term-missing    # kapsam (CI eşiği %80)
.venv/bin/python -m pytest -m gpu                                    # yalnızca CUDA'lı makinede
.venv/bin/ruff check src tests scripts
.venv/bin/ruff format --check src tests scripts
.venv/bin/pyright
.venv/bin/python -m dikte                                            # uygulamayı çalıştır
```

- Başsız (headless) ortamda Qt testleri `QT_QPA_PLATFORM=offscreen` ister (CI bunu ayarlar).
- `gpu` ve `win` işaretli testler uygun donanım/işletim sistemi yoksa atlanır.
- Testler GPU'suz, ağsız ve SDK'sız geçecek şekilde yazılır; bkz. [Sözleşmeler](#sözleşmeler).

## Mimari

```text
kısayol / IPC ─► DictationController ─► AudioRecorder ─► SttEngine (faster-whisper, GPU)
                   (durum makinesi)                        │
                                                           ▼
                 panoya yaz + yapıştır ◄─ LLM görevleri ◄─ sözlük + sesli komutlar
                                           (düzelt / çevir / prompt)
```

| Dizin | Sorumluluk |
|---|---|
| `src/dikte/app.py` | Uygulamanın bileşim kökü: bileşenleri kurar, sinyalleri bağlar, komut satırını işler |
| `src/dikte/config.py` | Tüm ayar şeması (pydantic, `frozen=True`), yükleme/kaydetme ve bozuk alan kurtarma |
| `src/dikte/core/` | `DictationController` durum makinesi, `Session`, geçmiş (JSONL), sağlık denetimi, thread-pool worker'ları |
| `src/dikte/audio/` | `sounddevice` ile kayıt (16 kHz mono float32), seviye ölçümü, cihaz seçimi |
| `src/dikte/stt/` | faster-whisper motoru, VAD ön kontrolü, halüsinasyon filtresi, model indirme |
| `src/dikte/llm/` | `LlmProvider` protokolü ve altı sağlayıcı, promptlar, görevler, anahtar okuma |
| `src/dikte/platform/` | Global kısayol, yapıştırma, pano, medya, otomatik başlatma, tek örnek/IPC, ön plan süreci |
| `src/dikte/text/` | Sözlük kuralları, sesli komutlar, uygulama profili eşleştirme |
| `src/dikte/ui/` | Tray, overlay, sonuç penceresi, geçmiş paneli, durum kontrolü, `settings/` sekmeleri |
| `scripts/` | Model indirme, ikon üretimi, LLM ve STT benchmark'ları |
| `packaging/` | PyInstaller spec, Inno Setup betiği, Windows derleme betiği, Linux kurulumu |
| `tests/` | pytest + pytest-qt testleri |

Ağır işler (STT, LLM, model yükleme) Qt thread-pool'unda çalışır; sonuçlar sinyallerle GUI
thread'ine döner. Denetleyici her oturum için bir kuşak sayacı (`_gen`) tutar; iptal edilen
oturumdan geç gelen sonuçlar bu sayaçla ayıklanır.

## Sözleşmeler

- **Önce test (TDD):** önce başarısız test, sonra en küçük uygulama. Kapsam %80'in altına düşmemeli.
- **Değişmez ayarlar:** pydantic modelleri `frozen=True`; değişiklik yalnızca
  `model_copy(update=...)` ile yapılır.
- **Enjekte edilebilir dış dünya:** GPU, ağ, SDK ve işletim sistemi erişimi `*_factory` /
  `*_probe` parametreleriyle verilir ki testler bunlar olmadan çalışsın.

  ```python
  # İYİ: test edilebilir
  def transcribe(self, audio, *, speech_probe=_default_speech_probe): ...
  # KÖTÜ: gizli bağımlılık
  def transcribe(self, audio):
      model = WhisperModel(...)
  ```

- **Yeni ayar alanı = varsayılan değer.** Eski `config.json` dosyaları doğrulamadan geçmeye devam
  etmeli. Alan silmek veya yeniden adlandırmak eski ayarları bozar.
- **Dil:** kullanıcıya görünen tüm metinler Türkçe ve tam diakritikli; kod tanımlayıcıları İngilizce.
  Docstring ve yorumlar Türkçe yazılır.
- **Hatalar yutulmaz:** kullanıcıya ne yapacağını söyleyen bir mesaj + `log.exception`.
- **Windows'a özgü kod** `sys.platform == "win32"` dalında kalır; Linux CI'da da içe aktarılabilir olmalı.

### Değişmeyecek ürün kararları

- **CPU'ya geri dönüş eklenmez.** STT GPU zorunludur.
- **API anahtarları** koda veya `config.json`'a yazılmaz; yalnızca ortam değişkeni adı saklanır ve
  arayüzde yalnızca "✓ tanımlı / ✗ yok" gösterilir. `llm/keys.py` anahtar değerini asla döndürmez
  veya loglamaz.
- **Çekirdek bağımlılıklar büyütülmez;** yeni SDK'lar `pyproject.toml`'da isteğe bağlı extra olur.
- **Kullanıcı onayı olmadan `ollama pull` çalıştırılmaz** (uygulama içinde de, benchmark'ta da).

### Dikkatle değiştirilecek dosyalar

| Dosya | Neden |
|---|---|
| `src/dikte/config.py` | Tüm ayar şeması; alan silmek eski config'leri bozar |
| `src/dikte/core/controller.py` | Durum makinesi ve iptal kuşak sayacı; yarış koşullarına açık |
| `src/dikte/stt/engine.py` | VAD ile toplu çözümleme etkileşimi: VAD kapalıyken toplu çözümleme çalışmaz |
| `src/dikte/llm/keys.py` | Anahtar sınırı |
| `src/dikte/ui/settings_dialog.py` | `_PROXIED` tablosu sekme widget'larını dışarı açar |

## Commit ve pull request

- Commit mesajları [Conventional Commits](https://www.conventionalcommits.org/) biçiminde ve
  Türkçe: `feat(stt): …`, `fix(ui): …`, `docs: …`, `test: …`, `chore: …`.
- Bir PR tek bir konuya odaklanmalı; alakasız biçimlendirme veya refactor eklemeyin.
- PR açmadan önce yerelde şunlar temiz olmalı: `ruff check`, `ruff format --check`, `pyright`, `pytest`.
- Kullanıcıya görünen bir davranış değiştiyse `docs/USAGE.md` / `docs/INSTALL.md` ve
  `CHANGELOG.md`'nin "Yayımlanmamış" bölümünü güncelleyin.
- Gerçek donanım gerektiren davranışlar (mikrofon, GPU, yapıştırma, pano) için
  [docs/manual_test_checklist.md](docs/manual_test_checklist.md)'ye madde ekleyin.

CI her PR'da Linux ve Windows üzerinde Python 3.11/3.12 ile testleri, ruff ve pyright'ı,
ayrıca Linux `.desktop` dosyası ile kurulum betiğinin doğrulamasını çalıştırır.

## Sürüm yayımlama

1. `pyproject.toml` ve `src/dikte/__init__.py` içindeki sürümü birlikte yükseltin.
2. `CHANGELOG.md`'de "Yayımlanmamış" bölümünü yeni sürüm başlığına taşıyın.
3. `vX.Y.Z` etiketini (tag) push edin. `release.yml` iş akışı testleri çalıştırır, PyInstaller
   paketini ve Inno Setup kurulum paketini üretir, paketlenmiş exe için `--version` duman testi
   yapar ve `Dikte-Setup-X.Y.Z.exe`'yi GitHub Release'e ekler.

## Benchmark'lar

- **LLM:** `.venv/bin/python scripts/eval_llm.py --models <model…>` (Ollama çalışıyor olmalı).
  Yöntem ve sonuçlar: [docs/llm_benchmark.md](docs/llm_benchmark.md).
- **STT:** `.venv/bin/python scripts/eval_stt.py --manifest <manifest.json> --write` (GPU gerekir).
  Yöntem: [docs/stt_benchmark.md](docs/stt_benchmark.md), veri formatı:
  [scripts/eval_data/stt/README.md](scripts/eval_data/stt/README.md).
