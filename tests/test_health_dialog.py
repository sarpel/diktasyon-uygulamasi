import threading

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox

from dikte.core.health import HealthItem
from dikte.ui import health_dialog as hd_mod
from dikte.ui.health_dialog import HealthDialog

OK_ITEMS = (
    HealthItem("GPU", True, "1 CUDA aygıtı", ""),
    HealthItem("Whisper modeli", True, "önbellekte", ""),
    HealthItem("LLM", True, "bağlantı kuruldu", ""),
)

MODEL_MISSING_ITEMS = (
    HealthItem("GPU", True, "1 CUDA aygıtı", ""),
    HealthItem("Whisper modeli", False, "indirilmemiş", 'Aşağıdaki "Modeli indir" ile indirin.'),
    HealthItem("LLM", True, "bağlantı kuruldu", ""),
)


def test_dialog_shows_one_row_per_item(qtbot):
    d = HealthDialog(OK_ITEMS)
    qtbot.addWidget(d)
    assert len(d._labels) == 3
    assert "✓ GPU: 1 CUDA aygıtı" in d._labels["GPU"].text()


def test_dialog_shows_failed_item_with_cross(qtbot):
    d = HealthDialog(MODEL_MISSING_ITEMS)
    qtbot.addWidget(d)
    assert d._labels["Whisper modeli"].text().startswith("✗")


def test_download_button_hidden_when_model_cached(qtbot):
    d = HealthDialog(OK_ITEMS)
    qtbot.addWidget(d)
    assert not d.download_btn.isVisible()


def test_download_button_visible_when_model_missing(qtbot):
    d = HealthDialog(MODEL_MISSING_ITEMS, on_download=lambda progress: None)
    qtbot.addWidget(d)
    d.show()
    assert d.download_btn.isVisible()


def test_download_reports_progress_and_marks_row_done(qtbot):
    def fake_download(progress):
        progress(50, 100)
        progress(100, 100)

    d = HealthDialog(MODEL_MISSING_ITEMS, on_download=fake_download)
    qtbot.addWidget(d)
    d.show()
    d.download_btn.click()
    qtbot.waitUntil(lambda: d._labels["Whisper modeli"].text().startswith("✓"), timeout=2000)
    assert not d.download_btn.isVisible()
    assert not d.progress_bar.isVisible()


def test_download_failure_shows_warning_and_re_enables_button(qtbot, monkeypatch):
    warned = []
    monkeypatch.setattr(
        hd_mod.QMessageBox, "warning", staticmethod(lambda *a, **k: warned.append(a))
    )

    def failing_download(progress):
        raise RuntimeError("bağlantı koptu")

    d = HealthDialog(MODEL_MISSING_ITEMS, on_download=failing_download)
    qtbot.addWidget(d)
    d.download_btn.click()
    qtbot.waitUntil(lambda: bool(warned), timeout=2000)
    assert d.download_btn.isEnabled()


# ---- yardımcılar

UNREACHABLE = (
    "Ollama'ya ulaşılamadı veya yanıt vermedi (http://127.0.0.1:11434): "
    "Failed to connect to Ollama. Please check that Ollama is downloaded, running and accessible."
)
MISSING_MODEL = (
    "Ollama'ya ulaşılamadı veya yanıt vermedi (http://127.0.0.1:11434): "
    'model "gemma4:e4b-it-qat" not found, try pulling it first (status code: 404)'
)


def _items(llm_ok=True, llm_detail="bağlantı kuruldu"):
    return (
        HealthItem("GPU", True, "1 CUDA aygıtı", ""),
        HealthItem("Whisper modeli", True, "önbellekte", ""),
        HealthItem("LLM", llm_ok, llm_detail, "" if llm_ok else "Ayarlar → …"),
    )


def _destroyed_flag(d):
    flag = []
    d.destroyed.connect(lambda *_: flag.append(1))
    return flag


# ---- Whisper indirmesi sonrası sinyal
def test_successful_download_emits_model_downloaded(qtbot):
    d = HealthDialog(MODEL_MISSING_ITEMS, on_download=lambda progress: progress(1, 1))
    qtbot.addWidget(d)
    d.show()
    with qtbot.waitSignal(d.model_downloaded, timeout=2000):
        d.download_btn.click()


def test_failed_download_does_not_emit_model_downloaded(qtbot, monkeypatch):
    monkeypatch.setattr(hd_mod.QMessageBox, "warning", staticmethod(lambda *a, **k: None))
    d = HealthDialog(MODEL_MISSING_ITEMS, on_download=lambda progress: 1 / 0)
    qtbot.addWidget(d)
    fired = []
    d.model_downloaded.connect(lambda: fired.append(1))
    d.download_btn.click()
    qtbot.waitUntil(d.download_btn.isEnabled, timeout=2000)
    qtbot.wait(20)
    assert fired == []


# ---- kapanınca kendini silme
def test_dialog_deletes_itself_on_close(qtbot):
    d = HealthDialog(OK_ITEMS)
    assert d.testAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
    destroyed = _destroyed_flag(d)
    d.show()
    d.close()
    qtbot.waitUntil(lambda: bool(destroyed), timeout=2000)


def test_closing_during_download_defers_delete_and_still_emits_signal(qtbot, monkeypatch):
    warned = []
    monkeypatch.setattr(
        hd_mod.QMessageBox, "warning", staticmethod(lambda *a, **k: warned.append(a))
    )
    release = threading.Event()

    def slow_download(progress):
        release.wait(5)
        progress(10, 10)

    d = HealthDialog(MODEL_MISSING_ITEMS, on_download=slow_download)
    destroyed = _destroyed_flag(d)
    downloaded = []
    d.model_downloaded.connect(lambda: downloaded.append(1))
    d.show()
    d.download_btn.click()
    d.close()
    qtbot.wait(50)
    assert destroyed == []  # işçi sürerken nesne canlı kalmalı
    release.set()
    qtbot.waitUntil(lambda: bool(destroyed), timeout=3000)
    assert downloaded == [1]
    assert warned == []


# ---- Ollama: başlat
def test_start_ollama_button_visible_only_when_unreachable(qtbot):
    d = HealthDialog(_items(False, UNREACHABLE), ollama_model="gemma4:e4b-it-qat")
    qtbot.addWidget(d)
    d.show()
    assert d.start_ollama_btn.isVisible()
    assert not d.pull_ollama_btn.isVisible()


def test_ollama_buttons_hidden_when_llm_ok_or_not_ollama(qtbot):
    ok = HealthDialog(_items(), ollama_model="gemma4:e4b-it-qat")
    other = HealthDialog(_items(False, "OpenAI anahtarı yok"), ollama_model=None)
    for d in (ok, other):
        qtbot.addWidget(d)
        d.show()
        assert not d.start_ollama_btn.isVisible()
        assert not d.pull_ollama_btn.isVisible()


def test_start_ollama_launches_and_rechecks_after_delay(qtbot):
    launched = []
    d = HealthDialog(
        _items(False, UNREACHABLE),
        ollama_model="gemma4:e4b-it-qat",
        ollama_launcher=lambda: launched.append(1),
        health_probe=lambda: _items(),
        recheck_delay_ms=30,
    )
    qtbot.addWidget(d)
    d.show()
    d.start_ollama_btn.click()
    assert launched == [1]
    assert not d.start_ollama_btn.isEnabled()
    qtbot.waitUntil(lambda: d._labels["LLM"].text().startswith("✓"), timeout=3000)
    assert not d.start_ollama_btn.isVisible()


def test_start_ollama_missing_binary_shows_download_hint(qtbot, monkeypatch):
    warned = []
    monkeypatch.setattr(
        hd_mod.QMessageBox, "warning", staticmethod(lambda *a, **k: warned.append(a))
    )

    def missing():
        raise FileNotFoundError("ollama")

    d = HealthDialog(
        _items(False, UNREACHABLE), ollama_model="gemma4:e4b-it-qat", ollama_launcher=missing
    )
    qtbot.addWidget(d)
    d.show()
    d.start_ollama_btn.click()
    assert warned and "ollama.com/download" in warned[0][2]
    assert d.start_ollama_btn.isEnabled()


class _FakePopen:
    calls: list = []

    def __init__(self, args, **kwargs):
        _FakePopen.calls.append((args, kwargs))


def test_launch_ollama_serve_windows_is_detached_without_console():
    _FakePopen.calls = []
    hd_mod.launch_ollama_serve(
        popen=_FakePopen, which=lambda: r"C:\Ollama\ollama.exe", platform="win32"
    )
    args, kwargs = _FakePopen.calls[0]
    assert args == [r"C:\Ollama\ollama.exe", "serve"]
    assert kwargs["creationflags"] == 0x08000000 | 0x00000008


def test_launch_ollama_serve_posix_starts_new_session():
    _FakePopen.calls = []
    hd_mod.launch_ollama_serve(popen=_FakePopen, which=lambda: "/usr/bin/ollama", platform="linux")
    args, kwargs = _FakePopen.calls[0]
    assert args == ["/usr/bin/ollama", "serve"]
    assert kwargs["start_new_session"] is True
    assert "creationflags" not in kwargs


def test_launch_ollama_serve_missing_binary_raises():
    with pytest.raises(FileNotFoundError):
        hd_mod.launch_ollama_serve(popen=_FakePopen, which=lambda: None, platform="linux")


# ---- Ollama: model indir
def _pull_dialog(qtbot, pull, **kw):
    d = HealthDialog(
        _items(False, MISSING_MODEL),
        ollama_model="gemma4:e4b-it-qat",
        ollama_host="http://127.0.0.1:11434",
        ollama_pull=pull,
        **kw,
    )
    qtbot.addWidget(d)
    d.show()
    return d


def test_pull_button_visible_when_model_missing(qtbot):
    d = _pull_dialog(qtbot, lambda *a: None)
    assert d.pull_ollama_btn.isVisible()
    assert not d.start_ollama_btn.isVisible()


def test_pull_requires_confirmation_naming_model(qtbot, monkeypatch):
    asked, pulled = [], []
    monkeypatch.setattr(
        hd_mod.QMessageBox,
        "question",
        staticmethod(lambda *a, **k: asked.append(a) or QMessageBox.StandardButton.No),
    )
    d = _pull_dialog(qtbot, lambda *a: pulled.append(a))
    d.pull_ollama_btn.click()
    qtbot.wait(30)
    assert pulled == []
    assert "gemma4:e4b-it-qat" in asked[0][2] and "GB" in asked[0][2]
    assert d.pull_ollama_btn.isEnabled()


def test_confirmed_pull_reports_status_and_rechecks(qtbot, monkeypatch):
    monkeypatch.setattr(
        hd_mod.QMessageBox,
        "question",
        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes),
    )
    calls = []

    def fake_pull(host, model, status):
        calls.append((host, model))
        status("pulling manifest", 0, 0)
        status("downloading", 50, 100)

    d = _pull_dialog(qtbot, fake_pull, health_probe=lambda: _items())
    d.pull_ollama_btn.click()
    assert d._jobs  # işçi sinyalleri iş bitene kadar referanslı tutulur
    qtbot.waitUntil(lambda: d._labels["LLM"].text().startswith("✓"), timeout=3000)
    assert calls == [("http://127.0.0.1:11434", "gemma4:e4b-it-qat")]
    assert "gemma4:e4b-it-qat" in d.ollama_status.text()
    assert not d.pull_ollama_btn.isVisible()
    assert not d._jobs


def test_pull_status_shows_percentage(qtbot):
    d = _pull_dialog(qtbot, lambda *a: None)
    d._on_pull_status("downloading", 25, 100)
    assert "%25" in d.ollama_status.text()


def test_failed_pull_warns_and_re_enables(qtbot, monkeypatch):
    warned = []
    monkeypatch.setattr(
        hd_mod.QMessageBox,
        "question",
        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes),
    )
    monkeypatch.setattr(
        hd_mod.QMessageBox, "warning", staticmethod(lambda *a, **k: warned.append(a))
    )

    def failing(host, model, status):
        raise RuntimeError("disk dolu")

    d = _pull_dialog(qtbot, failing)
    d.pull_ollama_btn.click()
    qtbot.waitUntil(lambda: bool(warned), timeout=3000)
    assert "disk dolu" in warned[0][2]
    assert d.pull_ollama_btn.isEnabled()


def test_closing_during_pull_stops_ui_updates_and_deletes_after(qtbot, monkeypatch):
    warned = []
    monkeypatch.setattr(
        hd_mod.QMessageBox,
        "question",
        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes),
    )
    monkeypatch.setattr(
        hd_mod.QMessageBox, "warning", staticmethod(lambda *a, **k: warned.append(a))
    )
    release = threading.Event()

    def slow_failing(host, model, status):
        release.wait(5)
        status("downloading", 1, 2)
        raise RuntimeError("iptal")

    d = HealthDialog(
        _items(False, MISSING_MODEL), ollama_model="gemma4:e4b-it-qat", ollama_pull=slow_failing
    )
    destroyed = _destroyed_flag(d)
    d.show()
    d.pull_ollama_btn.click()
    d.close()
    release.set()
    qtbot.waitUntil(lambda: bool(destroyed), timeout=3000)
    assert warned == []  # kapatılmış pencere için uyarı kutusu açılmaz


def test_classify_ollama_problem():
    assert hd_mod.classify_ollama_problem(HealthItem("LLM", False, UNREACHABLE, "")) == (
        "unreachable"
    )
    assert hd_mod.classify_ollama_problem(HealthItem("LLM", False, MISSING_MODEL, "")) == (
        "model_missing"
    )
    assert hd_mod.classify_ollama_problem(HealthItem("LLM", True, "bağlantı kuruldu", "")) is None
