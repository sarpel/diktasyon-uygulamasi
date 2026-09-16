# Dikte

Windows 11 (birincil) ve Linux için Türkçe odaklı, tamamen yerel çalışan
diktasyon uygulaması.
Tray'de sürekli açık durur, tek bir global kısayolla kaydı başlatır/durdurur,
sesi GPU'da metne çevirir, yerel bir LLM ile yanlış tanınan kelimeleri düzeltir
ve metni isteğe bağlı olarak İngilizce'ye ya da bir AI agent prompt'una dönüştürür.

- **STT:** faster-whisper `large-v3-turbo`, **yalnızca CUDA** (hedef: RTX 3060 Ti 8 GB).
  CPU'ya geri dönüş yoktur; GPU bulunamazsa uygulama hata verir.
  60 saniyeyi aşan kayıtlarda `BatchedInferencePipeline` devreye girer (ayarlardan kapatılabilir).
  `float16` için Compute Capability ≥ 7.0 (RTX 20xx ve üzeri) gerekir; daha eski kartlarda
  (ör. GTX 970 = CC 5.2) motor otomatik olarak `float32`'ye düşer ve tray'de uyarı gösterir.
- **Düzeltme / çeviri / prompt:** varsayılan olarak yereldeki Ollama (`qwen3.5:4b`,
  alternatif `gemma4:e4b-it-qat`); LM Studio, OpenAI, Anthropic, Gemini veya kendi
  uç noktanız da seçilebilir (bkz. [LLM sağlayıcıları](#llm-sağlayıcıları)).
  **Tamamen kapatılabilir** (Ayarlar → "LLM ile metin düzeltme"): kapalıyken ham metin
  doğrudan sonuç olarak gösterilir, Ollama hiç çağrılmaz ve ek VRAM kullanılmaz.
  Düşük VRAM'de `keep_alive` değerini `0` yaparak modeli her istekten sonra boşaltabilirsiniz.
- **UI:** PySide6 tray uygulaması + kayıt overlay'i + üç panelli sonuç penceresi

## Kurulum (Windows 11)

```powershell
winget install --id Python.Python.3.11 -e
winget install --id Ollama.Ollama -e
ollama pull qwen3.5:4b

py -3.11 -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -U pip uv
uv pip install -e ".[dev,cuda]"
python scripts\download_models.py   # Whisper modelini önceden indirir (~1,6 GB)
python -m dikte
```

NVIDIA sürücüsü CUDA 12 uyumlu olmalıdır (≥ 525). Ayrı CUDA Toolkit kurulumu
gerekmez; cuBLAS/cuDNN pip wheel'leri `dikte.cuda_dlls` tarafından DLL arama
yoluna eklenir.

## Kurulum (Linux)

Windows'a özgü olan tek şey global kısayoldur; onun yerine masaüstü ortamınızın
kısayol ayarına `dikte --toggle` komutunu bağlarsınız (Wayland'da da çalışır).

```bash
sudo apt install python3.11 python3.11-venv libportaudio2   # Debian/Ubuntu
sudo apt install xdotool                                    # X11'de otomatik yapıştırma
# Wayland kullanıyorsanız xdotool yerine: sudo apt install wtype
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen3.5:4b

./packaging/linux/install.sh      # pipx ile kurar, .desktop + ikon yazar, modeli indirir
```

Elle kurulum yapmak isterseniz:

```bash
uv venv --python 3.11 .venv && source .venv/bin/activate
uv pip install -e ".[dev,cuda]"
python scripts/download_models.py
python -m dikte
```

Global kısayol tanımı:

| Ortam | Yol |
|---|---|
| GNOME | Ayarlar → Klavye → Özel Kısayollar → Komut: `dikte --toggle` |
| KDE | Sistem Ayarları → Kısayollar → Özel → Komut: `dikte --toggle` |
| i3/sway | `bindsym $mod+space exec dikte --toggle` |

`dikte --toggle` çalışan örneğe yerel soket üzerinden komut yollar; uygulama
açık değilse hata verip 1 döner. Otomatik başlatma ayarı Linux'ta
`~/.config/autostart/dikte.desktop` dosyasını yazar.

Kullanıcı verileri: `~/.config/Dikte/`, model önbelleği: `~/.cache/Dikte/models/`.

## Kullanım

| Eylem | Kısayol / yer |
|---|---|
| Kaydı başlat / durdur | Windows: `Ctrl+Alt+Space` (ayarlardan değiştirilebilir) · Linux: `dikte --toggle`'a bağladığınız tuş |
| Düzeltilmiş metni kopyala | Pane'in sağ üstündeki kopyala ikonu veya `Ctrl+Shift+C` |
| İngilizce çeviri | Alt araç çubuğu → "İngilizce'ye Çevir" |
| Agent prompt'u | Alt araç çubuğu → "Agent Prompt'a Dönüştür" |
| Kaydı/çözümlemeyi iptal et | `Esc` (Windows'ta global) · overlay ya da araç çubuğunda "Vazgeç" · tray menüsü |
| Geçmiş panelini aç/kapat | Araç çubuğu → "Geçmiş" |
| Pencereyi gizle | `X` (uygulama tray'de kalır) |
| Çıkış | Tray menüsü → "Çıkış" |

### Sonuç nasıl teslim edilir

Kayıt bitip metin hazır olduğunda üç şey birden olur:

1. Düzeltilmiş metin **panoya** yazılır (Ayarlar → "Sonucu panoya kopyala").
2. Ön plandaki uygulama Dikte değilse metin oraya **Ctrl+V** ile yapıştırılır
   (Ayarlar → "Sonucu aktif pencereye yapıştır"). Windows'ta yerleşik; Linux'ta
   `xdotool` (X11) veya `wtype` (Wayland) kurulu olmalıdır, yoksa metin yalnızca panoda kalır.
3. Oturum **geçmişe** yazılır.

Sonuç penceresi varsayılan olarak öne gelmez; odağınız çalıştığınız uygulamada kalır.
İsterseniz Ayarlar → "Sonuçta pencereyi öne getir" ile açabilirsiniz.

Kayıt süresi varsayılan olarak **sınırsızdır** (Ayarlar → "Kayıt süresi sınırı" = 0). Bellek
kullanımı 16 kHz float32 ham ses için yaklaşık **230 MB/saat**'tir. Bir sınır girilirse süre
dolunca kayıt sessizce kesilmez; otomatik durur ve o ana kadarki ses çözümlenir.

### Halüsinasyon ve sessizlik

Whisper, sessiz veya çok gürültülü parçalarda eğitim verisindeki altyazı kalıplarını tekrar
edebilir ("Altyazı M.K.", "İzlediğiniz için teşekkürler"). Dikte bunu üç katmanda engeller:

1. **Ön kontrol:** Kayıtta hiç konuşma yoksa (Silero VAD) model **hiç çağrılmaz**;
   "Konuşma algılanmadı" uyarısı verilir.
2. **Eşikler:** Çözümlemeye `no_speech_threshold`, `log_prob_threshold` ve
   `hallucination_silence_threshold` geçilir; düşük güvenli segmentler elenir.
3. **Kara liste:** Bilinen uydurma kalıpları yalnızca tek başına bir segmenti kapladığında atılır;
   gerçek bir cümlenin içinde geçtiğinde korunur.

Eşik önerileri (Ayarlar → Konuşma Tanıma → "Sessizlik ve halüsinasyon"):

| Ortam | VAD eşiği |
|---|---|
| Gürültülü (açık ofis, fan) | 0,60 |
| Normal | 0,50 (varsayılan) |
| Kısık / yumuşak ses | 0,35 |

VAD kapatılırsa toplu çözümleme de devre dışı kalır (boru hattı konuşma aralıklarını VAD'den alır).

### LLM sağlayıcıları

Metin düzeltme varsayılan olarak yereldeki Ollama ile yapılır. Yerel bir alternatif (LM Studio)
veya uzak bir sağlayıcı da seçebilirsiniz:

| Sağlayıcı | Ortam değişkeni (varsayılan ad) | Kurulum | Base URL |
|---|---|---|---|
| Ollama (yerel) | — | çekirdek | `http://127.0.0.1:11434` |
| LM Studio (yerel) | gerekmez (boş bırakın) | `uv pip install -e ".[openai]"` | `http://127.0.0.1:1234/v1` |
| OpenAI | `OPENAI_API_KEY` | `uv pip install -e ".[openai]"` | `https://api.openai.com/v1` |
| Anthropic | `ANTHROPIC_API_KEY` | `uv pip install -e ".[anthropic]"` | — |
| Gemini | `GEMINI_API_KEY` | `uv pip install -e ".[gemini]"` | — |
| Custom (OpenAI-uyumlu) | kendi belirlediğiniz ad (boş bırakılabilir) | `.[openai]` | ör. `http://localhost:1234/v1` |
| Custom (Anthropic-uyumlu) | kendi belirlediğiniz ad (boş bırakılabilir) | `.[anthropic]` | proxy adresiniz |

Tablodaki adresler ilgili uygulamaların **varsayılan portlarıdır**: Ollama 11434, LM Studio 1234.
İki uygulamayı aynı makinede çalıştırıyorsanız veya portu başka bir şey kullanıyorsa, sunucuyu
taşıyıp adresi Ayarlar → Metin Düzeltme altındaki "Host" / "Base URL" kutusundan değiştirin.
LM Studio'da sunucuyu açmak için: Developer sekmesi → **Start Server**; "Model" kutusuna
LM Studio'nun listelediği model kimliğini yazın.

**Gizlilik:** Uzak sağlayıcı seçtiğinizde dikte edilen metin ilgili servise gönderilir.
API anahtarları **yalnızca ortam değişkeninden** okunur; `config.json`'a yazılmaz, loglanmaz ve
arayüzde gösterilmez — ayarlarda yalnızca "✓ tanımlı / ✗ yok" bilgisi görünür.

Özel uç noktanın hangi protokolü konuştuğunu Ayarlar → Metin Düzeltme → "Format" ile seçersiniz
(OpenAI-uyumlu ya da Anthropic-uyumlu). OpenAI-uyumlu sunucu `json_schema` desteklemiyorsa
otomatik olarak `json_object` moduna düşülür.

### Ayarlar

Ayarlar penceresi (tepsi menüsü veya araç çubuğu → "Ayarlar…") altı sekmeden oluşur:

| Sekme | İçerik |
|---|---|
| Genel | Kısayol (tuşa basarak yakalanır), geçmiş kayıt sayısı, açılışta başlat, panoya kopyala / yapıştır / pencereyi öne getir |
| Ses | Mikrofon, kayıt süresi sınırı (0 = sınırsız), canlı seviye testi |
| Konuşma Tanıma | Whisper modeli, hassasiyet (compute_type), dil, toplu çözümleme, açılışta ısıtma, "Sessizlik ve halüsinasyon" (VAD eşiği, en kısa sessizlik, konuşma yok eşiği, kara liste) |
| Metin Düzeltme | LLM aç/kapa, sağlayıcı ve sağlayıcıya özel alanlar, bellekte tutma |
| Gelişmiş | beam_size, başlangıç promptu, num_ctx, top_p, top_k, zaman aşımı, düşünme modu |
| Hakkında | Sürümler, GPU ve desteklenen hassasiyetler, log / ayar klasörünü aç |

Model ve ses ayarları uygulamayı yeniden başlatınca etkin olur; ipucu alanın üstüne gelince görünür.
`config.json` içindeki kısayol bozuksa uygulama çökmez, varsayılana döner ve bunu bildirir.

Kullanıcı verileri: `%APPDATA%\Dikte\` (config.json, history.jsonl, dikte.log).
Model önbelleği: `%LOCALAPPDATA%\Dikte\models\`.

## Geliştirme

```bash
uv venv --python 3.11 .venv
uv pip install -e ".[dev]"      # Windows'ta: ".[dev,cuda]"
.venv/bin/python -m pytest -q --cov=src --cov-report=term-missing   # GPU/Windows testleri atlanır
.venv/bin/python -m pytest -m gpu               # CUDA gerektirir
.venv/bin/ruff check src tests scripts          # CI ile aynı kapsam
.venv/bin/ruff format --check src tests scripts
```

Başsız (headless) ortamda Qt testleri için `QT_QPA_PLATFORM=offscreen` gerekir; CI bunu
ortam değişkeni olarak ayarlar.

- Ayrıntılı plan: [`implementation_plan.md`](implementation_plan.md)
- İyileştirme planı ve durumu: [`improvement_plan.md`](improvement_plan.md)
- Windows manuel test listesi: [`docs/manual_test_checklist.md`](docs/manual_test_checklist.md)
- LLM model karşılaştırması: `.venv/bin/python scripts/eval_llm.py --models <model…>` (Ollama çalışır durumda olmalı) · yöntem ve puanlama: [`docs/llm_benchmark.md`](docs/llm_benchmark.md)

## Paketleme (Windows)

```powershell
python scripts\make_icon.py                 # packaging\dikte.ico üretir
powershell -ExecutionPolicy Bypass -File packaging\build.ps1
```

Çıktı: `dist\Dikte\Dikte.exe` (onedir) ve `dist\Dikte-Setup-0.1.0.exe`
(Inno Setup 6 kurulu olmalı).

## Paketleme (Linux)

```bash
python scripts/make_icon.py       # packaging/dikte.ico + packaging/linux/dikte.png
./packaging/linux/install.sh      # pipx tabanlı kullanıcı kurulumu
```

Kaldırmak için: `pipx uninstall dikte` ve
`rm ~/.local/share/applications/dikte.desktop ~/.config/autostart/dikte.desktop`.

<!-- LAST-SYNCED: 2026-09-15 -->
