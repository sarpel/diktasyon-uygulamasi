from PySide6.QtCore import QObject, Signal

from dikte.core.state import DictationState, Session
from dikte.llm.tasks import Change
from dikte.ui.result_window import ResultWindow


class FakeController(QObject):
    state_changed = Signal(object)
    session_updated = Signal(object)
    error = Signal(str)

    def __init__(self):
        super().__init__()
        self.translations, self.prompts = [], []
        self.session = Session()

    def request_translation(self, t):
        self.translations.append(t)

    def request_enhanced_prompt(self, t):
        self.prompts.append(t)


def make(qtbot):
    c = FakeController()
    w = ResultWindow()
    qtbot.addWidget(w)
    w.bind(c)
    return w, c


def test_session_fills_panes_and_changes(qtbot):
    w, c = make(qtbot)
    s = Session(
        raw_text="hava çuk güzel",
        corrected_text="Hava çok güzel.",
        changes=(Change("çuk", "çok", "yazım"),),
    )
    c.session_updated.emit(s)
    assert w.raw_pane.text() == "hava çuk güzel"
    assert w.corrected_pane.text() == "Hava çok güzel."
    assert w.changes_list.count() == 1 and "çuk" in w.changes_list.item(0).text()


def test_translate_button_sends_current_corrected_text(qtbot):
    w, c = make(qtbot)
    w.corrected_pane.set_text("Merhaba dünya.")
    w.corrected_pane.editor.appendPlainText("Elle eklendi.")  # kullanıcı düzenlemesi
    w.translate_btn.click()
    assert c.translations == ["Merhaba dünya.\nElle eklendi."]
    assert w.output_pane.title_label.text() == "İngilizce Çeviri"
    assert not w.translate_btn.isEnabled()  # bekleme sırasında kilit


def test_enhance_button_sends_text_and_result_fills_output(qtbot):
    w, c = make(qtbot)
    w.corrected_pane.set_text("bana todo uygulaması yaz")
    w.enhance_btn.click()
    assert c.prompts == ["bana todo uygulaması yaz"]
    c.session_updated.emit(Session(enhanced_prompt="# Goal\nBuild a todo app"))
    assert w.output_pane.text().startswith("# Goal")
    assert w.output_pane.title_label.text() == "Agent Prompt (EN)"
    assert w.enhance_btn.isEnabled()


def test_result_state_shows_window(qtbot):
    w, c = make(qtbot)
    c.state_changed.emit(DictationState.RESULT)
    assert w.isVisible()


def test_close_hides_instead_of_quitting(qtbot):
    w, c = make(qtbot)
    w.show()
    w.close()
    assert not w.isVisible() and w.isEnabled()
