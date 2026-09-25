import struct

from dikte.platform.clipboard import (
    CLOUD_FORMAT,
    EXCLUDE_FORMAT,
    HISTORY_FORMAT,
    build_mime,
    restore_delay_ms,
    should_restore,
    windows_mime,
)


def test_windows_mime_uses_qt_registered_format_syntax():
    assert windows_mime("X") == 'application/x-qt-windows-mime;value="X"'


def test_build_mime_sets_text(qapp):
    mime = build_mime("merhaba dünya", exclude_history=False, platform="win32")
    assert mime.text() == "merhaba dünya"
    assert not mime.hasFormat(windows_mime(HISTORY_FORMAT))


def test_build_mime_excludes_from_history_on_windows(qapp):
    mime = build_mime("gizli", exclude_history=True, platform="win32")
    assert mime.text() == "gizli"
    assert mime.hasFormat(windows_mime(EXCLUDE_FORMAT))
    zero = struct.pack("<I", 0)
    assert bytes(mime.data(windows_mime(HISTORY_FORMAT)).data()) == zero
    assert bytes(mime.data(windows_mime(CLOUD_FORMAT)).data()) == zero


def test_build_mime_adds_no_windows_formats_on_linux(qapp):
    mime = build_mime("metin", exclude_history=True, platform="linux")
    assert mime.formats() == ["text/plain"]


def test_should_restore_only_when_clipboard_still_holds_our_text():
    assert should_restore("dikte metni", "dikte metni") is True
    assert should_restore("kullanıcı kopyaladı", "dikte metni") is False
    assert should_restore(None, "dikte metni") is False
    assert should_restore("", "") is False


def test_restore_delay_scales_and_is_capped():
    assert restore_delay_ms("") == 300
    assert 300 < restore_delay_ms("a" * 1000) < 1500
    assert restore_delay_ms("a" * 100_000) == 1500
