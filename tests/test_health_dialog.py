from dikte.core.health import HealthItem
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
    from dikte.ui import health_dialog as hd_mod

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
