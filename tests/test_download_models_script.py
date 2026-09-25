"""scripts/download_models.py: GPU'suz indirme ve anlaşılır hata."""

import importlib.util
from pathlib import Path

from dikte.config import Settings, SttSettings

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "download_models.py"


def _load():
    spec = importlib.util.spec_from_file_location("download_models_script", SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_downloads_configured_model_without_loading_engine(tmp_path, capsys):
    mod = _load()
    calls = []

    def fake_download(model, root, progress):
        calls.append((model, root))
        progress(50, 100)
        progress(100, 100)
        return tmp_path / "snap"

    code = mod.main(
        download=fake_download,
        settings_loader=lambda: Settings(stt=SttSettings(model="small")),
        models_dir=lambda: tmp_path,
    )
    assert code == 0
    assert calls == [("small", tmp_path)]
    assert "small" in capsys.readouterr().out
    assert "engine" not in vars(mod) and "FasterWhisperEngine" not in vars(mod)


def test_failure_returns_nonzero_with_guidance(tmp_path, capsys):
    mod = _load()

    def boom(model, root, progress):
        raise OSError("ağ yok")

    code = mod.main(download=boom, settings_loader=Settings, models_dir=lambda: tmp_path)
    err = capsys.readouterr().err
    assert code == 1
    assert "ağ yok" in err and "download_models.py" in err
