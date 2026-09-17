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
