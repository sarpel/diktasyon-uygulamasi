from dikte.config import LlmSettings, Settings
from dikte.core.health import check_health, model_is_cached


def test_check_health_returns_three_items_with_fake_probes():
    items = check_health(
        Settings(),
        cuda_probe=lambda: 1,
        model_probe=lambda m: True,
        llm_probe=lambda llm: None,
    )
    assert [i.name for i in items] == ["GPU", "Whisper modeli", "LLM"]
    assert all(i.ok for i in items)


def test_check_health_gpu_missing_is_not_ok():
    items = check_health(
        Settings(), cuda_probe=lambda: 0, model_probe=lambda m: True, llm_probe=lambda llm: None
    )
    gpu = items[0]
    assert gpu.ok is False and gpu.hint


def test_check_health_model_missing_is_not_ok():
    items = check_health(
        Settings(), cuda_probe=lambda: 1, model_probe=lambda m: False, llm_probe=lambda llm: None
    )
    model_item = items[1]
    assert model_item.ok is False and model_item.hint


def test_check_health_llm_error_is_not_ok():
    items = check_health(
        Settings(),
        cuda_probe=lambda: 1,
        model_probe=lambda m: True,
        llm_probe=lambda llm: "bağlantı hatası",
    )
    llm_item = items[2]
    assert llm_item.ok is False and llm_item.detail == "bağlantı hatası"


def test_check_health_llm_disabled_is_ok_without_probing():
    called = []
    items = check_health(
        Settings(llm=LlmSettings(enabled=False)),
        cuda_probe=lambda: 1,
        model_probe=lambda m: True,
        llm_probe=lambda llm: called.append(1) or "ignored",
    )
    llm_item = items[2]
    assert llm_item.ok is True and llm_item.detail == "kapalı"
    assert called == []


def test_model_is_cached_finds_model_bin(tmp_path):
    d = tmp_path / "models--x--faster-whisper-large-v3-turbo" / "snapshots" / "a"
    d.mkdir(parents=True)
    (d / "model.bin").write_bytes(b"x")
    assert model_is_cached("large-v3-turbo", tmp_path) is True


def test_model_is_cached_false_when_missing(tmp_path):
    assert model_is_cached("large-v3-turbo", tmp_path) is False


def test_model_is_cached_does_not_match_turbo_as_plain_large_v3(tmp_path):
    """F: yalnızca "large-v3-turbo" önbellekteyken "large-v3" istenirse yanlış pozitif
    üretmemeli — ikisi farklı modeller."""
    d = tmp_path / "models--x--faster-whisper-large-v3-turbo" / "snapshots" / "a"
    d.mkdir(parents=True)
    (d / "model.bin").write_bytes(b"x")
    assert model_is_cached("large-v3", tmp_path) is False


def test_model_is_cached_survives_unreadable_entry(tmp_path, monkeypatch):
    """F: Windows'ta HF önbelleğindeki symlink'ler dizin gezilirken OSError (WinError 448)
    fırlatabiliyor; tarama çökmek yerine o girdiyi atlamalı."""
    import os as _os

    broken = tmp_path / "models--x--broken"
    broken.mkdir()
    good = tmp_path / "models--x--faster-whisper-large-v3-turbo" / "snapshots" / "a"
    good.mkdir(parents=True)
    (good / "model.bin").write_bytes(b"x")

    real_scandir = _os.scandir

    def fake_scandir(path):
        if str(path) == str(broken):
            raise OSError(448, "The path cannot be traversed")
        return real_scandir(path)

    monkeypatch.setattr("dikte.core.health.os.scandir", fake_scandir)
    assert model_is_cached("large-v3-turbo", tmp_path) is True


def test_model_is_cached_is_false_when_every_entry_is_unreadable(tmp_path, monkeypatch):
    (tmp_path / "models--x--faster-whisper-large-v3-turbo").mkdir()

    def fake_scandir(path):
        raise OSError(448, "The path cannot be traversed")

    monkeypatch.setattr("dikte.core.health.os.scandir", fake_scandir)
    assert model_is_cached("large-v3-turbo", tmp_path) is False


def test_model_is_cached_finds_model_bin_behind_symlink(tmp_path):
    """HF önbelleği snapshots/<rev>/model.bin'i blobs/<sha>'ya symlink'ler."""
    blobs = tmp_path / "models--x--faster-whisper-large-v3-turbo" / "blobs"
    blobs.mkdir(parents=True)
    blob = blobs / "deadbeef"
    blob.write_bytes(b"x")
    snap = tmp_path / "models--x--faster-whisper-large-v3-turbo" / "snapshots" / "a"
    snap.mkdir(parents=True)
    (snap / "model.bin").symlink_to(blob)
    assert model_is_cached("large-v3-turbo", tmp_path) is True
