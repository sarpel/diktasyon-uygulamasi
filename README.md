# Dikte

Windows 11 için Türkçe odaklı, tamamen yerel çalışan diktasyon uygulaması.
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

## Kullanım

| Eylem | Kısayol / yer |
|---|---|
| Kaydı başlat / durdur | `Ctrl+Alt+Space` (ayarlardan değiştirilebilir) |
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
