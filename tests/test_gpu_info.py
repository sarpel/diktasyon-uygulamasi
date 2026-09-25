from dikte.platform.gpu_info import VramInfo, format_vram, query_vram


def test_query_vram_parses_nvidia_smi_output():
    info = query_vram(runner=lambda: "3277, 8192\n")
    assert info == VramInfo(3277, 8192)


def test_query_vram_returns_none_when_nvidia_smi_missing():
    def boom():
        raise FileNotFoundError("nvidia-smi bulunamadı")

    assert query_vram(runner=boom) is None


def test_query_vram_returns_none_on_unparseable_output():
    assert query_vram(runner=lambda: "beklenmedik çıktı") is None


def test_query_vram_returns_none_on_empty_output():
    assert query_vram(runner=lambda: "") is None


def test_format_vram_renders_turkish_decimal_comma():
    assert format_vram(VramInfo(3277, 8192)) == "3,2 / 8,0 GB"


def test_format_vram_none_is_unknown():
    assert format_vram(None) == "bilinmiyor"


def test_nvidia_smi_hides_console_window_on_windows():
    from dikte.platform.gpu_info import _run_nvidia_smi

    seen = {}

    def fake(cmd, **kwargs):
        seen.update(kwargs)
        return "1, 2\n"

    assert _run_nvidia_smi(platform="win32", check_output=fake) == "1, 2\n"
    assert seen["creationflags"] == 0x08000000


def test_nvidia_smi_has_no_creationflags_on_linux():
    from dikte.platform.gpu_info import _run_nvidia_smi

    seen = {}

    def fake(cmd, **kwargs):
        seen.update(kwargs)
        return ""

    _run_nvidia_smi(platform="linux", check_output=fake)
    assert "creationflags" not in seen
