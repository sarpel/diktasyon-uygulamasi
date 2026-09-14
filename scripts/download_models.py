"""STT modelini ilk çalıştırmadan önce indirir (kurulum sonrası / build öncesi)."""

from faster_whisper import WhisperModel

from dikte import paths
from dikte.cuda_dlls import register_nvidia_dll_dirs

register_nvidia_dll_dirs()
m = WhisperModel(
    "large-v3-turbo",
    device="cuda",
    compute_type="float16",
    download_root=str(paths.models_dir()),
)
print("OK, model dizini:", paths.models_dir())
