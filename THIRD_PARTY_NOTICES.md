# Üçüncü taraf bildirimleri

Dikte'nin kendi kaynak kodu [MIT lisansı](LICENSE) ile dağıtılır. Windows kurulum paketi
(`Dikte-Setup-*.exe`) ve kaynaktan kurulum, aşağıdaki üçüncü taraf bileşenleri içerir veya
kullanır. Her bileşen kendi lisansına tabidir; tam lisans metinleri ilgili projelerde ve kurulu
paketlerin `*.dist-info/` klasörlerinde bulunur.

Bu liste bilgilendirme amaçlıdır ve doğrudan bağımlılıkları kapsar. Geçişli bağımlılıkların
güncel listesi için: `pip list` / `pip show <paket>`.

## Uygulama çekirdeği

| Bileşen | Lisans | Proje |
|---|---|---|
| PySide6 / Qt for Python, shiboken6 | LGPL-3.0-only (veya GPL-2.0/3.0) | <https://www.qt.io/qt-for-python> |
| Qt 6 kütüphaneleri | LGPL-3.0-only | <https://www.qt.io/licensing/open-source-lgpl-obligations> |
| faster-whisper | MIT | <https://github.com/SYSTRAN/faster-whisper> |
| CTranslate2 | MIT | <https://github.com/OpenNMT/CTranslate2> |
| Silero VAD (faster-whisper içinde) | MIT | <https://github.com/snakers4/silero-vad> |
| ONNX Runtime | MIT | <https://github.com/microsoft/onnxruntime> |
| Hugging Face tokenizers | Apache-2.0 | <https://github.com/huggingface/tokenizers> |
| huggingface_hub | Apache-2.0 | <https://github.com/huggingface/huggingface_hub> |
| PyAV | BSD-3-Clause | <https://github.com/PyAV-Org/PyAV> |
| FFmpeg (PyAV ile birlikte gelen kütüphaneler) | LGPL-2.1-or-later | <https://ffmpeg.org/legal.html> |
| python-sounddevice | MIT | <https://github.com/spatialaudio/python-sounddevice> |
| PortAudio | MIT | <https://www.portaudio.com> |
| NumPy | BSD-3-Clause | <https://numpy.org> |
| pydantic | MIT | <https://github.com/pydantic/pydantic> |
| ollama-python | MIT | <https://github.com/ollama/ollama-python> |

## GPU kütüphaneleri (`cuda` extra'sı, kurulum paketinde dâhil)

| Bileşen | Lisans | Proje |
|---|---|---|
| NVIDIA cuBLAS (`nvidia-cublas-cu12`) | NVIDIA Software License Agreement / CUDA EULA | <https://docs.nvidia.com/cuda/eula/> |
| NVIDIA cuDNN (`nvidia-cudnn-cu12`) | NVIDIA cuDNN Software License Agreement | <https://docs.nvidia.com/deeplearning/cudnn/latest/reference/eula.html> |

Bu kütüphaneler NVIDIA'nın lisansının izin verdiği yeniden dağıtım koşullarıyla, değiştirilmeden dağıtılır.

## LLM sağlayıcı SDK'ları (isteğe bağlı extra'lar, kurulum paketinde dâhil)

| Bileşen | Lisans | Proje |
|---|---|---|
| openai-python | Apache-2.0 | <https://github.com/openai/openai-python> |
| anthropic-sdk-python | MIT | <https://github.com/anthropics/anthropic-sdk-python> |
| google-genai | Apache-2.0 | <https://github.com/googleapis/python-genai> |
| winsdk (`media` extra'sı, yalnızca Windows) | MIT | <https://github.com/pywinrt/python-winsdk> |

## İndirilen modeller (pakete dâhil değil)

| Model | Lisans | Kaynak |
|---|---|---|
| Whisper `large-v3-turbo` (CTranslate2 biçimi) | MIT | <https://huggingface.co/mobiuslabsgmbh/faster-whisper-large-v3-turbo> |
| Ollama modelleri (ör. `gemma4:e4b-it-qat`) | Her modelin kendi lisansı | <https://ollama.com/library> |

Whisper modeli ilk kullanımda Hugging Face'ten indirilir. LLM modellerini kullanıcı kendisi indirir;
model lisanslarına uymak kullanıcının sorumluluğundadır.

## LGPL bileşenleri hakkında

Qt/PySide6 ve FFmpeg, LGPL koşullarına uygun olarak ayrı, dinamik bağlı kütüphaneler hâlinde
dağıtılır (kurulum klasöründeki `_internal\` altında). Kullanıcı bu kütüphaneleri uyumlu
sürümleriyle değiştirebilir. Kaynak kodlarına yukarıdaki proje bağlantılarından ulaşılabilir.

## Araçlar (dağıtılmaz)

Derleme ve geliştirme sırasında kullanılır, kurulum paketine girmez: PyInstaller (GPL-2.0 +
bootloader istisnası; üretilen paketin lisansını etkilemez), Inno Setup, pytest, ruff, pyright.
