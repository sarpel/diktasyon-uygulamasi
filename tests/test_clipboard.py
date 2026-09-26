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


def test_copy_text_marks_windows_clipboard_as_excluded(qapp):
    from PySide6.QtWidgets import QApplication

    from dikte.platform.clipboard import copy_text

    copy_text("gizli dikte", exclude_history=True, platform="win32")
    mime = QApplication.clipboard().mimeData()
    assert mime is not None and mime.text() == "gizli dikte"
    assert mime.hasFormat(windows_mime(EXCLUDE_FORMAT))


def test_mime_data_is_cpp_allocated(qapp):
    """Python'da kurulan QMimeData, sanal metotları Python'a yönlenen bir shiboken alt
    sınıfıdır; panoda kalırsa Qt kapanışta onu çağırır ve süreç segfault ile çöker."""
    from shiboken6 import Shiboken

    from dikte.platform.clipboard import new_mime_data

    mime = new_mime_data()
    assert not Shiboken.createdByPython(mime)
    assert mime.formats() == []
    assert not Shiboken.createdByPython(build_mime("x", exclude_history=True, platform="win32"))


def test_process_exits_cleanly_with_our_mime_on_clipboard():
    import os
    import subprocess
    import sys

    code = (
        "from PySide6.QtWidgets import QApplication\n"
        "from dikte.platform.clipboard import copy_text\n"
        "app = QApplication([])\n"
        "copy_text('kapanışta panoda', exclude_history=True, platform='win32')\n"
    )
    env = {**os.environ, "QT_QPA_PLATFORM": "offscreen"}
    proc = subprocess.run([sys.executable, "-c", code], env=env, timeout=60, check=False)
    assert proc.returncode == 0
