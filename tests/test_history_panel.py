from datetime import UTC, datetime

from dikte.core.state import Session
from dikte.ui.history_panel import HistoryPanel


def _panel(qtbot) -> HistoryPanel:
    p = HistoryPanel()
    qtbot.addWidget(p)
    return p


def _visible(panel) -> list:
    return [
        panel.list_widget.item(i)
        for i in range(panel.list_widget.count())
        if not panel.list_widget.item(i).isHidden()
    ]


def test_panel_lists_sessions_newest_first(qtbot):
    p = _panel(qtbot)
    old = Session(
        raw_text="eski", corrected_text="Eski.", created_at=datetime(2026, 1, 1, 9, 0, tzinfo=UTC)
    )
    new = Session(
        raw_text="yeni", corrected_text="Yeni.", created_at=datetime(2026, 1, 2, 9, 0, tzinfo=UTC)
    )
    p.set_sessions((old, new))
    assert p.list_widget.item(0).text().endswith("Yeni.")


def test_search_filters_by_text(qtbot):
    p = _panel(qtbot)
    p.set_sessions(
        (
            Session(corrected_text="Docker port çakışması"),
            Session(corrected_text="Toplantı 15:00"),
        )
    )
    p.search_edit.setText("docker")
    assert len(_visible(p)) == 1


def test_search_is_case_and_diacritic_aware(qtbot):
    p = _panel(qtbot)
    p.set_sessions((Session(corrected_text="İstanbul toplantısı"),))
    p.search_edit.setText("istanbul")
    assert len(_visible(p)) == 1


def test_clicking_item_emits_session(qtbot):
    p = _panel(qtbot)
    s = Session(corrected_text="X")
    p.set_sessions((s,))
    got = []
    p.session_selected.connect(got.append)
    p.list_widget.itemClicked.emit(p.list_widget.item(0))
    assert got == [s]


def test_delete_emits_id(qtbot):
    p = _panel(qtbot)
    s = Session(corrected_text="X")
    p.set_sessions((s,))
    got = []
    p.delete_requested.connect(got.append)
    p.list_widget.setCurrentRow(0)
    p.delete_btn.click()
    assert got == [s.id]


def test_delete_without_selection_does_nothing(qtbot):
    p = _panel(qtbot)
    p.set_sessions((Session(corrected_text="X"),))
    got = []
    p.delete_requested.connect(got.append)
    p.list_widget.setCurrentRow(-1)
    p.delete_btn.click()
    assert got == []


def test_copy_puts_selected_text_on_clipboard(qtbot):
    from PySide6.QtWidgets import QApplication

    p = _panel(qtbot)
    p.set_sessions((Session(corrected_text="Kopyalanacak"),))
    p.list_widget.setCurrentRow(0)
    p.copy_btn.click()
    assert QApplication.clipboard().text() == "Kopyalanacak"


def test_clear_requires_confirmation(qtbot, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    p = _panel(qtbot)
    p.set_sessions((Session(corrected_text="X"),))
    fired = []
    p.clear_requested.connect(lambda: fired.append(1))
    monkeypatch.setattr(
        QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.No)
    )
    p.clear_btn.click()
    assert fired == []
    monkeypatch.setattr(
        QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
    )
    p.clear_btn.click()
    assert fired == [1]


def test_empty_history_shows_hint(qtbot):
    p = _panel(qtbot)
    p.set_sessions(())
    assert p.list_widget.count() == 0 and p.empty_label.isVisibleTo(p)


def test_search_ignores_missing_diacritics(qtbot):
    p = _panel(qtbot)
    p.set_sessions((Session(corrected_text="Toplantısı erteledik"),))
    p.search_edit.setText("toplantisi")
    assert len(_visible(p)) == 1
