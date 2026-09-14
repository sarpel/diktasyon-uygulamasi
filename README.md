# Dikte

Windows 11 (birincil) ve Linux için Türkçe odaklı, tamamen yerel çalışan
diktasyon uygulaması.
Tray'de sürekli açık durur, tek bir global kısayolla kaydı başlatır/durdurur,
sesi GPU'da metne çevirir, yerel bir LLM ile yanlış tanınan kelimeleri düzeltir
ve metni isteğe bağlı olarak İngilizce'ye ya da bir AI agent prompt'una dönüştürür.

- **STT:** faster-whisper `large-v3-turbo`, CUDA (hedef: RTX 3060 Ti 8 GB)
- **Düzeltme / çeviri / prompt:** Ollama üzerinde yerel LLM (varsayılan `qwen3.5:4b`,
  alternatif `gemma4:e4b-it-qat`), isteğe bağlı Anthropic API
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
| Pencereyi gizle | `X` (uygulama tray'de kalır) |
| Çıkış | Tray menüsü → "Çıkış" |

Kullanıcı verileri: `%APPDATA%\Dikte\` (config.json, history.jsonl, dikte.log).
Model önbelleği: `%LOCALAPPDATA%\Dikte\models\`.

## Geliştirme

```bash
uv venv --python 3.11 .venv
uv pip install -e ".[dev]"      # Windows'ta: ".[dev,cuda]"
pytest                          # GPU ve Windows testleri yoksa atlanır
pytest -m gpu                   # CUDA gerektirir
ruff check src tests
```

- Ayrıntılı plan: [`implementation_plan.md`](implementation_plan.md)
- Windows manuel test listesi: [`docs/manual_test_checklist.md`](docs/manual_test_checklist.md)
- LLM model karşılaştırması: `python scripts/eval_llm.py` (Ollama çalışır durumda olmalı)

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
