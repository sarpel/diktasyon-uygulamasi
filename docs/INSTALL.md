# Kurulum

Bu belge Dikte'nin Windows 11 ve Linux üzerinde kurulumunu, kaldırılmasını ve sık görülen
sorunların çözümünü anlatır. Günlük kullanım için bkz. [USAGE.md](USAGE.md).

## İçindekiler

- [Sistem gereksinimleri](#sistem-gereksinimleri)
- [Windows: kurulum paketiyle (önerilen)](#windows-kurulum-paketiyle-önerilen)
- [Windows: kaynaktan](#windows-kaynaktan)
- [Linux](#linux)
- [LLM (isteğe bağlı): Ollama ve diğer sağlayıcılar](#llm-isteğe-bağlı-ollama-ve-diğer-sağlayıcılar)
- [İsteğe bağlı extra'lar](#isteğe-bağlı-extralar)
- [Güncelleme](#güncelleme)
- [Kaldırma](#kaldırma)
- [Sorun giderme](#sorun-giderme)

## Sistem gereksinimleri

| Bileşen | Gereksinim |
|---|---|
| İşletim sistemi | Windows 11 (birincil) veya masaüstü ortamlı bir Linux dağıtımı (X11 veya Wayland). macOS desteklenmez: NVIDIA/CUDA GPU yoktur |
| GPU | **NVIDIA, CUDA destekli.** CPU'da çalışmaz (bilinçli ürün kararı). Hedef donanım: RTX 3060 Ti 8 GB |
| GPU sürücüsü | CUDA 12 uyumlu NVIDIA sürücüsü (≥ 525). Ayrı CUDA Toolkit kurulumu **gerekmez** |
| VRAM | Whisper `large-v3-turbo` ≈ 1,6 GB; yerel LLM (4B, q4) ≈ 3,5–4,5 GB. LLM'siz kullanımda 4 GB yeterli |
| Disk | Uygulama birkaç GB (CUDA kütüphaneleri dâhil) + Whisper modeli ≈ 1,6 GB + (isteğe bağlı) Ollama modeli ≈ 4 GB |
| Python (yalnızca kaynaktan kurulumda) | 3.11 veya daha yenisi; 3.11–3.14 test edilir. Python 3.15, PySide6/ctranslate2/onnxruntime o sürüm için paket yayımlayınca kendiliğinden çalışır |
| Mikrofon | Sistemin tanıdığı herhangi bir giriş cihazı |

`float16` hassasiyeti için Compute Capability ≥ 7.0 (RTX 20xx ve üzeri) gerekir. Daha eski
kartlarda (ör. GTX 970) Dikte otomatik olarak `float32`'ye düşer ve uyarı gösterir.

## Windows: kurulum paketiyle (önerilen)

1. [Releases](https://github.com/sarpel/diktasyon-uygulamasi/releases) sayfasından en son
   `Dikte-Setup-<sürüm>.exe` dosyasını indirin.
2. Çalıştırın. Kurulum yönetici izni istemez; uygulama `%LOCALAPPDATA%\Programs\Dikte\`
   altına kurulur.
3. Dikte'yi başlatın. İlk açılışta **"Durum kontrolü"** penceresi açılır:
   - **Whisper modeli** henüz yoksa "Modeli indir" düğmesine basın (~1,6 GB, bir kerelik).
   - **LLM** satırı kırmızıysa aşağıdaki [Ollama](#llm-isteğe-bağlı-ollama-ve-diğer-sağlayıcılar)
     adımını uygulayın ya da Ayarlar → Metin Düzeltme'den LLM'i kapatın.
4. `Ctrl+Alt+Space` ile ilk diktenizi yapın.

Kurulum paketi Python, CUDA kütüphaneleri (cuBLAS/cuDNN), tüm LLM sağlayıcı SDK'larını ve
medya duraklatma için pywinrt (`winrt-*`) paketlerini içerir. Bilgisayarda yalnızca NVIDIA sürücüsü kurulu olmalıdır.

> Windows SmartScreen imzasız kurulum dosyaları için "Windows bilgisayarınızı korudu" uyarısı
> gösterebilir. Dosyayı bu repodaki Releases sayfasından indirdiyseniz "Ek bilgi" →
> "Yine de çalıştır" ile devam edebilirsiniz.

## Windows: kaynaktan

```powershell
winget install --id Python.Python.3.11 -e
git clone https://github.com/sarpel/diktasyon-uygulamasi.git
cd diktasyon-uygulamasi

py -3.11 -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -U pip uv
uv pip install -e ".[cuda]"          # geliştirme için: ".[dev,cuda]"
python scripts\download_models.py    # Whisper modelini önceden indirir (~1,6 GB)
python -m dikte
```

- `cuda` extra'sı cuBLAS/cuDNN'i pip paketleri olarak getirir; `dikte.cuda_dlls` bunları açılışta
  DLL arama yoluna ekler.
- LLM sağlayıcıları ve medya duraklatma için ek extra'lar: bkz. [İsteğe bağlı extra'lar](#isteğe-bağlı-extralar).

### Kendi kurulum paketinizi üretmek

```powershell
python scripts\make_icon.py                                     # packaging\dikte.ico
powershell -ExecutionPolicy Bypass -File packaging\build.ps1
```

Betik bağımlılıkları kurar, testleri çalıştırır, PyInstaller ile `dist\Dikte\Dikte.exe`
(onedir) üretir ve [Inno Setup 6](https://jrsoftware.org/isinfo.php) kuruluysa
`dist\Dikte-Setup-<sürüm>.exe` kurulum paketini derler. Sürüm `pyproject.toml`'dan okunur.

Derleme sırasında PyInstaller'ın `sounddevice ... is not a package`, `No module named 'aiohttp'`
ve `Hidden import "tzdata" not found` uyarıları zararsızdır: bunlar Dikte'nin kullanmadığı
isteğe bağlı parçalarla ilgilidir.

## Linux

Windows'a özgü olan tek şey global kısayoldur. Linux'ta masaüstü ortamınızın kısayol ayarına
`dikte --toggle` komutunu bağlarsınız (Wayland'da da çalışır).

### 1. Sistem paketleri

```bash
# Debian / Ubuntu
sudo apt install python3.11 python3.11-venv libportaudio2 pipx
sudo apt install xdotool      # X11: otomatik yapıştırma ve uygulama profilleri
sudo apt install wtype        # Wayland: otomatik yapıştırma
sudo apt install playerctl    # isteğe bağlı: kayıtta medyayı duraklatma
```

Diğer dağıtımlarda aynı paketlerin karşılıklarını kurun (PortAudio çalışma zamanı kütüphanesi zorunludur).

### 2. Kurulum betiği (önerilen)

```bash
git clone https://github.com/sarpel/diktasyon-uygulamasi.git
cd diktasyon-uygulamasi
./packaging/linux/install.sh
```

Betik root gerektirmez ve şunları yapar:

1. Uygulamayı `pipx` ile `[cuda]` extra'sıyla yalıtılmış bir ortama kurar
   (en yeni uygun Python 3.11+ sürümünü kendisi bulur; farklı bir yorumlayıcı için `DIKTE_PYTHON=/yol/python`).
2. pip'in CUDA kütüphanelerini `LD_LIBRARY_PATH`'e ekleyen bir başlatıcı yazar
   (`~/.local/share/dikte/dikte-launcher`).
3. Uygulama menüsü kaydını ve ikonu yazar.
4. Whisper modelini indirir. İndirme başarısız olursa kurulum durmaz; model ilk açılışta da indirilebilir.

Uygulama başlatıcı olmadan açılsa bile (`python -m dikte`, otomatik başlatma) CUDA kütüphaneleri
açılışta önceden yüklenir.

### 2b. Elle kurulum

```bash
uv venv --python 3.11 .venv && source .venv/bin/activate
uv pip install -e ".[cuda]"          # geliştirme için: ".[dev,cuda]"
python scripts/download_models.py
python -m dikte
```

### 3. Global kısayol

| Ortam | Yol |
|---|---|
| GNOME | Ayarlar → Klavye → Özel Kısayollar → Komut: `dikte --toggle` |
| KDE | Sistem Ayarları → Kısayollar → Özel → Komut: `dikte --toggle` |
| i3 / sway | `bindsym $mod+space exec dikte --toggle` |

Çeviri veya agent prompt'u için ayrı tuşlar: `dikte --toggle --mode translate`,
`dikte --toggle --mode prompt`. Bas-konuş için tuşa basma/bırakmaya `dikte --start` / `dikte --stop` bağlayın.

`dikte --toggle` çalışan örneğe yerel soket üzerinden komut yollar; uygulama açık değilse hata
verip 1 döner. Otomatik başlatma ayarı Linux'ta `~/.config/autostart/dikte.desktop` dosyasını yazar.

## LLM (isteğe bağlı): Ollama ve diğer sağlayıcılar

Metin düzeltme, çeviri ve agent prompt'u bir LLM ister. LLM olmadan da Dikte çalışır; o zaman ham
STT metni doğrudan sonuç olur (Ayarlar → Metin Düzeltme → "LLM ile metin düzeltme" kapalı).

Varsayılan ve önerilen yerel kurulum:

```bash
# Windows
winget install --id Ollama.Ollama -e
# Linux
curl -fsSL https://ollama.com/install.sh | sh

ollama pull gemma4:e4b-it-qat      # varsayılan model (~4 GB)
```

Model seçiminin gerekçesi: [llm_benchmark.md](llm_benchmark.md). "Durum kontrolü" penceresi
Ollama kapalıysa "Ollama'yı başlat", model eksikse (onayınızı alarak) "Modeli indir" seçeneği sunar.

LM Studio, OpenAI, Anthropic, Gemini ve özel uç noktalar için bkz.
[USAGE.md → LLM sağlayıcıları](USAGE.md#llm-sağlayıcıları). API anahtarları yalnızca **ortam
değişkeninden** okunur. Windows'ta kalıcı ortam değişkeni tanımlamak için:

```powershell
setx OPENAI_API_KEY "sk-..."     # sonra Dikte'yi yeniden başlatın
```

## İsteğe bağlı extra'lar

Kaynaktan kurulumda ihtiyacınıza göre extra'ları birleştirin, ör. `uv pip install -e ".[cuda,openai,media]"`.

| Extra | Ne getirir | Ne zaman gerekir |
|---|---|---|
| `cuda` | NVIDIA cuBLAS + cuDNN (pip paketleri) | Neredeyse her zaman (sistemde CUDA Toolkit yoksa) |
| `openai` | `openai` SDK | OpenAI, LM Studio veya OpenAI-uyumlu özel uç nokta |
| `anthropic` | `anthropic` SDK | Anthropic veya Anthropic-uyumlu özel uç nokta |
| `gemini` | `google-genai` SDK | Gemini |
| `media` | `winrt-*` (pywinrt, yalnızca Windows) | Kayıtta çalan medyayı duraklatma (Linux'ta `playerctl` kullanılır) |
| `dev` | pytest, ruff, pyright, PyInstaller ve sağlayıcı SDK'ları | Geliştirme ve paketleme |

## Güncelleme

- **Kurulum paketi:** yeni `Dikte-Setup-<sürüm>.exe`'yi çalıştırın; ayarlarınız ve geçmişiniz korunur.
- **Kaynaktan:** `git pull` ve ardından aynı `uv pip install -e ".[...]"` komutu.
- **Linux betiği:** `git pull` ve `./packaging/linux/install.sh` (betik `pipx install --force` kullanır).

## Kaldırma

**Windows (kurulum paketi):** Ayarlar → Uygulamalar → Dikte → Kaldır. Otomatik başlatma kaydı da
silinir. Kullanıcı verileri bilerek korunur; tamamen temizlemek için:

```powershell
Remove-Item -Recurse "$env:APPDATA\Dikte", "$env:LOCALAPPDATA\Dikte"
```

**Linux (kurulum betiği):**

```bash
pipx uninstall dikte
rm -f ~/.local/share/applications/dikte.desktop ~/.config/autostart/dikte.desktop \
      ~/.local/share/icons/hicolor/256x256/apps/dikte.png
rm -rf ~/.local/share/dikte
rm -rf ~/.config/Dikte ~/.cache/Dikte      # ayarlar, geçmiş ve model (isteğe bağlı)
```

## Sorun giderme

Önce Ayarlar → Hakkında → **"Durum kontrolü…"** penceresine bakın; çoğu sorun orada ✗ ile ve
bir çözüm ipucuyla görünür. Ayrıntılı log: `%APPDATA%\Dikte\dikte.log` (Linux:
`~/.config/Dikte/dikte.log`). Ayarlar → Hakkında'daki düğmeyle log klasörünü açabilirsiniz.

| Belirti | Olası neden ve çözüm |
|---|---|
| "CUDA destekli GPU bulunamadı" | NVIDIA sürücüsü eksik/eski (≥ 525 gerekir) veya GPU devre dışı. `nvidia-smi` çalışıyor mu kontrol edin. Dikte CPU'ya düşmez |
| `cublas64_12.dll` / `libcudnn` bulunamadı | Kaynaktan kurulumda `[cuda]` extra'sı eksik: `uv pip install -e ".[cuda]"` |
| "GPU … desteklemiyor" uyarısı | Kart `float16` desteklemiyor (CC < 7.0); Dikte `float32`'ye düştü. Çalışır, ama daha yavaş ve daha çok VRAM kullanır |
| Metin düzeltilmiyor, ham metin geliyor | LLM'e ulaşılamıyor. Ollama çalışıyor mu (`ollama ps`), model indirildi mi (`ollama list`)? Uzak sağlayıcıda anahtar "✓ tanımlı" mı? |
| Kısayol çalışmıyor (Windows) | Başka bir uygulama aynı kısayolu kullanıyor olabilir; Dikte bunu bildirir. Ayarlar → Genel'den farklı bir kısayol seçin |
| Metin yapıştırılmıyor | Yönetici olarak çalışan pencerelere normal bir uygulamadan yapıştırma Windows tarafından engellenir. Linux'ta `xdotool` (X11) / `wtype` (Wayland) kurulu olmalı. Metin her durumda panodadır |
| Terminalde `Ctrl+V` çalışmıyor | Ayarlar → Profiller'de o terminal için Yapıştırma=`ctrl+shift+v` tanımlayın |
| "Mikrofondan ses gelmiyor" uyarısı | Mikrofon sessizde veya yanlış cihaz seçili. Ayarlar → Ses'teki canlı seviye testini kullanın |
| "Konuşma algılanmadı" | VAD konuşma bulamadı. Kısık seste VAD eşiğini 0,35'e indirin (Ayarlar → Konuşma Tanıma) |
| `dikte --toggle` "çalışmıyor" diyor | Uygulama açık değil; önce `dikte --minimized` ile başlatın |
| Ayarlarım sıfırlandı | `config.json` bozuktu; geçersiz alanlar varsayılana döndü ve eski dosya `config.json.bak` olarak yedeklendi |

Sorun devam ederse log dosyasıyla birlikte bir [issue](https://github.com/sarpel/diktasyon-uygulamasi/issues)
açın. Log dosyası kullanıcı adınızı içeren dosya yolları gibi kişisel bilgiler içerebilir;
paylaşmadan önce göz atın.
