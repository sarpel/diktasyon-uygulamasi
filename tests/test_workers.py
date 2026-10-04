from PySide6.QtCore import QThreadPool

from dikte.core.workers import run_in_pool


def test_result_callback_exception_is_routed_to_on_error(qtbot):
    """Sonuç geri çağrısındaki istisna yutulmamalı: on_error'a Türkçe mesajla iletilir,
    on_finished yine çağrılır (çağıran taraf takılı kalmasın)."""
    errors, finished = [], []

    def boom(_result):
        raise ValueError("bozuk sonuç")

    signals = run_in_pool(
        lambda: 42, boom, errors.append, QThreadPool(), on_finished=lambda: finished.append(1)
    )
    qtbot.waitUntil(lambda: bool(finished), timeout=3000)
    assert errors and "beklenmeyen" in errors[0] and "bozuk sonuç" in errors[0]
    del signals


def test_error_callback_exception_is_logged_not_raised(qtbot, caplog):
    finished = []

    def bad_error(_msg):
        raise RuntimeError("hata işleyici bozuk")

    def fail():
        raise OSError("iş başarısız")

    signals = run_in_pool(
        fail, lambda _r: None, bad_error, QThreadPool(), on_finished=lambda: finished.append(1)
    )
    qtbot.waitUntil(lambda: bool(finished), timeout=3000)
    assert "hata işleyici bozuk" in caplog.text
    del signals
