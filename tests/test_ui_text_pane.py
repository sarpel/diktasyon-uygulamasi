from PySide6.QtWidgets import QApplication

from dikte.llm.diff import Change
from dikte.ui.text_pane import TextPane


def test_set_and_get_text(qtbot):
    p = TextPane("Ham")
    qtbot.addWidget(p)
    p.set_text("merhaba")
    assert p.text() == "merhaba" and p.title_label.text() == "Ham"


def test_copy_button_puts_text_on_clipboard_and_emits(qtbot):
    p = TextPane("Ham")
    qtbot.addWidget(p)
    p.set_text("kopyala beni")
    with qtbot.waitSignal(p.copied) as blocker:
        p.copy_btn.click()
    assert blocker.args[0] == "kopyala beni"
    assert QApplication.clipboard().text() == "kopyala beni"


def test_editor_is_editable(qtbot):
    p = TextPane("Düzeltilmiş")
    qtbot.addWidget(p)
    assert not p.editor.isReadOnly()
    qtbot.keyClicks(p.editor, "abc")
    assert p.text() == "abc"


def test_busy_disables_copy(qtbot):
    p = TextPane("X")
    qtbot.addWidget(p)
    p.set_busy(True)
    assert not p.copy_btn.isEnabled()


def test_highlights_follow_change_offsets(qtbot):
    p = TextPane("Düzeltilmiş")
    qtbot.addWidget(p)
    p.set_text("Hava çok güzel.")
    p.set_highlights((Change("çuk", "çok", "değiştirildi", 5, 8),))
    sel = p.editor.extraSelections()
    assert len(sel) == 1 and sel[0].cursor.selectedText() == "çok"
    p.set_text("başka")
    assert p.editor.extraSelections() == []


def test_copy_honours_exclude_history_flag(qtbot, monkeypatch):
    calls = []
    monkeypatch.setattr(
        "dikte.ui.text_pane.copy_text",
        lambda text, *, exclude_history: calls.append((text, exclude_history)),
    )
    p = TextPane("Ham")
    qtbot.addWidget(p)
    assert p.exclude_history is True  # varsayılan ayarla aynı
    p.exclude_history = False
    p.set_text("x")
    p.copy_btn.click()
    assert calls == [("x", False)]


def test_old_side_marks_removed_words_in_red(qtbot):
    from dikte.ui.text_pane import ADDED_COLOR, REMOVED_COLOR

    p = TextPane("Ham")
    qtbot.addWidget(p)
    p.set_text("hava çuk güzel")
    p.set_highlights((Change("çuk", "çok", "değiştirildi", 5, 8, 5, 8),), side="old")
    (sel,) = p.editor.extraSelections()
    assert sel.cursor.selectedText() == "çuk"
    assert sel.format.background().color() == REMOVED_COLOR
    assert REMOVED_COLOR != ADDED_COLOR


def test_new_side_marks_added_words_in_green(qtbot):
    from dikte.ui.text_pane import ADDED_COLOR

    p = TextPane("Düzeltilmiş")
    qtbot.addWidget(p)
    p.set_text("Hava çok güzel.")
    p.set_highlights((Change("çuk", "çok", "değiştirildi", 5, 8, 5, 8),))
    (sel,) = p.editor.extraSelections()
    assert sel.cursor.selectedText() == "çok"
    assert sel.format.background().color() == ADDED_COLOR


def test_pure_deletion_marks_only_old_side(qtbot):
    old = TextPane("Ham")
    new = TextPane("Düzeltilmiş")
    qtbot.addWidget(old)
    qtbot.addWidget(new)
    old.set_text("bugün ee toplantı")
    new.set_text("bugün toplantı")
    change = Change("ee", "", "silindi", 5, 5, 6, 8)
    old.set_highlights((change,), side="old")
    new.set_highlights((change,))
    assert [s.cursor.selectedText() for s in old.editor.extraSelections()] == ["ee"]
    assert new.editor.extraSelections() == []


def test_old_side_tooltip_offsets_use_original_range(qtbot):
    p = TextPane("Ham")
    qtbot.addWidget(p)
    p.set_text("hava çuk güzel")
    p.set_highlights((Change("çuk", "çok", "değiştirildi", 5, 8, 5, 8),), side="old")
    assert p._change_at(6) is not None and p._change_at(0) is None
