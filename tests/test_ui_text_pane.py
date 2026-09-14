from PySide6.QtWidgets import QApplication

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
