# Dikte

Windows 11 için Türkçe odaklı, tamamen yerel çalışan diktasyon uygulaması.

- **STT:** faster-whisper `large-v3-turbo`, CUDA (RTX 3060 Ti 8 GB hedefi)
- **Düzeltme:** Ollama üzerinde yerel LLM (varsayılan `qwen3.5:4b`)
- **UI:** PySide6 tray uygulaması, global toggle kısayolu (`Ctrl+Alt+Space`)

## Kurulum (geliştirme)

```bash
uv venv --python 3.11 .venv
uv pip install -e ".[dev]"          # Windows'ta: ".[dev,cuda]"
pytest
```

Ayrıntılı plan: [`implementation_plan.md`](implementation_plan.md).
