# Dikte

[![CI](https://github.com/sarpel/diktasyon-uygulamasi/actions/workflows/ci.yml/badge.svg)](https://github.com/sarpel/diktasyon-uygulamasi/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

**A Turkish-focused, fully local desktop dictation app for Windows 11 and Linux.**

Press a hotkey, speak, and press it again. Your speech is transcribed on the GPU, optionally
cleaned up by a local LLM, and pasted into the window you are working in. By default, audio and
text never leave your machine.

> The user interface and the full documentation are in Turkish. This page is a short English
> overview.

## Features

- **Local, fast speech-to-text:** [faster-whisper](https://github.com/SYSTRAN/faster-whisper)
  `large-v3-turbo` on an NVIDIA GPU, with live chunked transcription while you are still speaking.
- **Optional LLM correction:** fixes misrecognized words, punctuation and casing with a local
  Ollama model (`gemma4:e4b-it-qat`). LM Studio, OpenAI, Anthropic, Gemini or any
  OpenAI/Anthropic-compatible endpoint can be used instead. The LLM step can be turned off.
- **Translate to English** or **turn a dictation into a structured prompt** for an AI coding agent.
- **Direct paste** into the active window. The previous clipboard content can be restored, and
  dictated text is kept out of the Windows clipboard history.
- **Custom dictionary**, **voice commands** ("yeni satır" = new line, "son cümleyi sil" =
  delete last sentence, "geri al" = undo…), and **per-application profiles**.
- **Hallucination guard:** silent recordings never reach the model, and known Whisper
  hallucinations are filtered out.
- Push-to-talk, auto-stop on silence, pause media while recording, searchable history, retry a
  failed recording, drag-and-drop audio files, and a first-run health check with one-click model download.

## Requirements

- Windows 11 (primary) or Linux (X11 / Wayland)
- **An NVIDIA GPU with CUDA** and driver ≥ 525. There is intentionally no CPU fallback.
  Target: RTX 3060 Ti 8 GB (Whisper ≈ 1.6 GB VRAM + local LLM ≈ 4 GB)
- Optional: [Ollama](https://ollama.com) or another LLM provider for text correction

## Install

**Windows:** download `Dikte-Setup-<version>.exe` from
[Releases](https://github.com/sarpel/diktasyon-uygulamasi/releases) and run it. On first launch,
use the "Durum kontrolü" (health check) window to download the Whisper model (~1.6 GB).

**Linux:**

```bash
sudo apt install python3.11 python3.11-venv libportaudio2 pipx xdotool
git clone https://github.com/sarpel/diktasyon-uygulamasi.git && cd diktasyon-uygulamasi
./packaging/linux/install.sh
```

Then bind `dikte --toggle` to a key in your desktop environment's keyboard settings.

**Optional LLM correction:** `ollama pull gemma4:e4b-it-qat`

From source:

```bash
uv venv --python 3.11 .venv && source .venv/bin/activate
uv pip install -e ".[cuda]"
python scripts/download_models.py
python -m dikte
```

Detailed guide (Turkish): [docs/INSTALL.md](docs/INSTALL.md) · Usage (Turkish): [docs/USAGE.md](docs/USAGE.md)

## Privacy

Speech recognition always runs locally. If you pick a cloud LLM provider, only the dictated text
is sent to it, never the audio. API keys are read from environment variables only and are never
written to disk or logged. There is no telemetry.

## Contributing

Issues and pull requests are welcome, in English or Turkish. See [CONTRIBUTING.md](CONTRIBUTING.md).
Security issues: [SECURITY.md](SECURITY.md).

## License

[MIT](LICENSE) © Sarpel GÜRAY. Third-party components bundled in the Windows installer come
with their own licenses. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
