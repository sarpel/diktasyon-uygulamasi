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


def test_translate_mode_session_auto_fills_output_without_pending(qtbot):
    """Çeviri kısayoluyla gelen sonuç, pencere içi düğmeye basılmasa da çıkış paneline yazılır."""
    w, c = make(qtbot)
    c.session_updated.emit(Session(mode="translate", corrected_text="a", translation="b"))
    assert w.output_pane.text() == "b"
    assert w.output_pane.title_label.text() == "İngilizce Çeviri"


def test_prompt_mode_session_auto_fills_output_without_pending(qtbot):
    w, c = make(qtbot)
    c.session_updated.emit(Session(mode="prompt", corrected_text="a", enhanced_prompt="# Goal"))
    assert w.output_pane.text() == "# Goal"
    assert w.output_pane.title_label.text() == "Agent Prompt (EN)"


def test_enhance_button_sends_text_and_result_fills_output(qtbot):
    w, c = make(qtbot)
    w.corrected_pane.set_text("bana todo uygulaması yaz")
    w.enhance_btn.click()
    assert c.prompts == ["bana todo uygulaması yaz"]
    c.session_updated.emit(Session(enhanced_prompt="# Goal\nBuild a todo app"))
    assert w.output_pane.text().startswith("# Goal")
    assert w.output_pane.title_label.text() == "Agent Prompt (EN)"
    assert w.enhance_btn.isEnabled()


def test_result_state_shows_window_when_raise_enabled(qtbot):
    w, c = make(qtbot)
    w.raise_on_result = True
    c.state_changed.emit(DictationState.RESULT)
    qtbot.waitUntil(lambda: w.isVisible(), timeout=1000)


def test_close_hides_instead_of_quitting(qtbot):
    w, c = make(qtbot)
    w.show()
    w.close()
    assert not w.isVisible() and w.isEnabled()


def test_llm_buttons_disabled_when_llm_off(qtbot):
    w = ResultWindow()
    qtbot.addWidget(w)
    w.set_llm_enabled(False)
    assert not w.translate_btn.isEnabled() and not w.enhance_btn.isEnabled()
    assert "LLM" in w.translate_btn.toolTip()
    w.set_llm_enabled(True)
    assert w.translate_btn.isEnabled() and w.enhance_btn.isEnabled()


def test_pending_cycle_keeps_buttons_disabled_when_llm_off(qtbot):
    w = ResultWindow()
    qtbot.addWidget(w)
    w.set_llm_enabled(False)
    w._start_pending("translation", "x")
    w._finish_pending()
    assert not w.translate_btn.isEnabled()


def test_window_not_raised_on_result_by_default(qtbot):
    w, c = make(qtbot)
    w.hide()
    c.state_changed.emit(DictationState.RESULT)
    assert not w.isVisible()


def test_window_raised_when_setting_enabled(qtbot):
    w, c = make(qtbot)
    w.raise_on_result = True
    w.hide()
    c.state_changed.emit(DictationState.RESULT)
    qtbot.waitUntil(lambda: w.isVisible(), timeout=1000)


def test_identical_changes_are_hidden(qtbot):
    w, c = make(qtbot)
    c.session_updated.emit(
        Session(
            changes=(
                Change("a", "a", "noktalama"),
                Change(" boşluk ", "boşluk", "boşluk"),
                Change("promt", "prompt", "yazım"),
            )
        )
    )
    assert w.changes_list.count() == 1


def test_status_bar_shows_duration_and_word_count(qtbot):
    w, c = make(qtbot)
    c.session_updated.emit(Session(corrected_text="bir iki üç", duration_s=12.4))
    msg = w.statusBar().currentMessage()
    assert "12 sn" in msg and "3 kelime" in msg


def test_session_stats_survive_translation_post_processing(qtbot):
    w, c = make(qtbot)
    w._start_pending("translation", "x")
    c.session_updated.emit(
        Session(corrected_text="bir iki üç", duration_s=12.4, translation="one two three")
    )
    msg = w.statusBar().currentMessage()
    assert "12 sn" in msg and "3 kelime" in msg


def test_session_stats_survive_enhanced_prompt_post_processing(qtbot):
    w, c = make(qtbot)
    w._start_pending("enhanced_prompt", "x")
    c.session_updated.emit(
        Session(corrected_text="bir iki üç", duration_s=12.4, enhanced_prompt="# Goal")
    )
    msg = w.statusBar().currentMessage()
    assert "12 sn" in msg and "3 kelime" in msg


def test_result_state_activation_is_deferred_so_paste_target_is_preserved(qtbot):
    w, c = make(qtbot)
    w.raise_on_result = True
    w.hide()
    c.state_changed.emit(DictationState.RESULT)
    # Aktivasyon 0 ms'ye ertelenir; qtbot.waitUntil senkron olmayan gösterimi bekler.
    qtbot.waitUntil(lambda: w.isVisible(), timeout=1000)
    assert w.isVisible()


def test_status_info_label_shows_model_and_llm(qtbot):
    w, _ = make(qtbot)
    w.set_status_info("large-v3-turbo", "float16", "qwen3.5:4b")
    text = w.status_info.text()
    assert "large-v3-turbo" in text and "float16" in text and "qwen3.5:4b" in text


def test_history_action_toggles_dock(qtbot):
    w, _ = make(qtbot)
    w.show()
    assert not w.history_panel.isVisible()
    w.history_action.trigger()
    assert w.history_panel.isVisible()
    w.history_action.trigger()
    assert not w.history_panel.isVisible()


def test_load_session_fills_panes_and_clears_pending(qtbot):
    w, _ = make(qtbot)
    w._pending = "translation"
    w.load_session(Session(raw_text="h", corrected_text="D", translation="T"))
    assert w.corrected_pane.text() == "D"
    assert w.output_pane.text() == "T"
    assert w._pending is None


def test_toolbar_actions_emit_signals(qtbot):
    w, _ = make(qtbot)
    fired = []
    w.record_requested.connect(lambda: fired.append("record"))
    w.cancel_requested.connect(lambda: fired.append("cancel"))
    w.settings_requested.connect(lambda: fired.append("settings"))
    w.record_action.trigger()
    w.cancel_action.setEnabled(True)
    w.cancel_action.trigger()
    w.settings_action.trigger()
    assert fired == ["record", "cancel", "settings"]


def test_record_action_label_follows_state(qtbot):
    w, c = make(qtbot)
    c.state_changed.emit(DictationState.RECORDING)
    assert w.record_action.text() == "Durdur" and w.cancel_action.isEnabled()
    c.state_changed.emit(DictationState.IDLE)
    assert w.record_action.text() == "Kaydet" and not w.cancel_action.isEnabled()


def test_late_llm_result_does_not_overwrite_loaded_history(qtbot):
    """Geçmiş yüklendikten sonra gelen (iptal edilmiş) çeviri sonucu ekranı ezmemeli."""
    w, c = make(qtbot)
    c.session = Session(raw_text="canlı", corrected_text="Canlı.")
    w._start_pending("translation", "İngilizce Çeviri")
    w.load_session(Session(raw_text="eski", corrected_text="Eski."))
    c.session_updated.emit(Session(id=c.session.id, raw_text="canlı", translation="late"))
    assert w.raw_pane.text() == "eski" and w.output_pane.text() == ""


def test_new_request_after_history_load_is_shown_again(qtbot):
    w, c = make(qtbot)
    c.session = Session(raw_text="canlı")
    w.load_session(Session(raw_text="eski", corrected_text="Eski."))
    w._start_pending("translation", "İngilizce Çeviri")
    c.session_updated.emit(Session(id=c.session.id, raw_text="canlı", translation="yeni"))
    assert w.output_pane.text() == "yeni"
