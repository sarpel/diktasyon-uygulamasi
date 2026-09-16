from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QAction, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMainWindow,
    QPushButton,
    QSplitter,
    QStatusBar,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from dikte.core.state import BUSY_STATES, DictationState, Session
from dikte.ui.history_panel import HistoryPanel
from dikte.ui.text_pane import TextPane
from dikte.ui.toast import Toast

TITLE_TRANSLATION = "İngilizce Çeviri"
TITLE_PROMPT = "Agent Prompt (EN)"


class ResultWindow(QMainWindow):
    record_requested = Signal()
    cancel_requested = Signal()
    settings_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Dikte")
        self.resize(1100, 620)
        self._controller = None
        self._pending: str | None = None  # "translation" | "enhanced_prompt"
        self._ignored_session_id: str | None = None  # geçmiş görüntülenirken geç gelen sonuç
        self.close_after_copy = False
        self.raise_on_result = False

        self.raw_pane = TextPane("Ham")
        self.corrected_pane = TextPane("Düzeltilmiş")
        self.output_pane = TextPane(TITLE_TRANSLATION)
        self.changes_list = QListWidget()
        self.changes_list.setMaximumHeight(110)
        self.changes_list.setToolTip("LLM'in yaptığı düzeltmeler")

        self.translate_btn = QPushButton("İngilizce'ye Çevir")
        self.enhance_btn = QPushButton("Agent Prompt'a Dönüştür")
        self._llm_enabled = True
        self.translate_btn.clicked.connect(self._on_translate)
        self.enhance_btn.clicked.connect(self._on_enhance)

        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.addWidget(self.raw_pane, 1)
        mid = QWidget()
        ml = QVBoxLayout(mid)
        ml.setContentsMargins(0, 0, 0, 0)
        ml.addWidget(self.corrected_pane, 1)
        ml.addWidget(self.changes_list)
        split = QSplitter(Qt.Horizontal)
        for w in (left, mid, self.output_pane):
            split.addWidget(w)
        split.setSizes([330, 400, 370])

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(self.translate_btn)
        buttons.addWidget(self.enhance_btn)
        root = QWidget()
        rl = QVBoxLayout(root)
        rl.setContentsMargins(12, 12, 12, 12)
        rl.addWidget(split, 1)
        rl.addLayout(buttons)
        self.setCentralWidget(root)

        self._build_toolbar()
        self._build_status_bar()
        self.history_panel = HistoryPanel(self)
        self.addDockWidget(Qt.RightDockWidgetArea, self.history_panel)
        self.history_panel.hide()
        self.history_panel.visibilityChanged.connect(self._on_dock_visibility)
        self.history_panel.session_selected.connect(self.load_session)

        for pane in (self.raw_pane, self.corrected_pane, self.output_pane):
            pane.copied.connect(lambda _t, p=pane: self._on_copied(p))
        QShortcut(QKeySequence("Ctrl+Shift+C"), self, activated=self.corrected_pane._copy)
        QShortcut(QKeySequence(Qt.Key_Escape), self, activated=self._on_escape)

    # ---- kurulum
    def _build_toolbar(self) -> None:
        self.toolbar = QToolBar("Ana")
        self.toolbar.setObjectName("mainToolBar")
        self.toolbar.setMovable(False)
        self.record_action = QAction("Kaydet", self)
        self.record_action.setToolTip("Kaydı başlat / durdur")
        self.record_action.triggered.connect(self.record_requested)
        self.cancel_action = QAction("Vazgeç", self)
        self.cancel_action.setToolTip("Süren işi iptal et (Esc)")
        self.cancel_action.setEnabled(False)
        self.cancel_action.triggered.connect(self.cancel_requested)
        self.history_action = QAction("Geçmiş", self)
        self.history_action.setCheckable(True)
        self.history_action.setToolTip("Geçmiş panelini aç / kapat")
        self.history_action.toggled.connect(self._set_history_visible)
        self.settings_action = QAction("Ayarlar…", self)
        self.settings_action.triggered.connect(self.settings_requested)
        for action in (self.record_action, self.cancel_action):
            self.toolbar.addAction(action)
        self.toolbar.addSeparator()
        for action in (self.history_action, self.settings_action):
            self.toolbar.addAction(action)
        self.addToolBar(self.toolbar)

    def _build_status_bar(self) -> None:
        self.setStatusBar(QStatusBar())
        self.status_info = QLabel("")
        self.status_info.setStyleSheet("color:#888;")
        self.statusBar().addPermanentWidget(self.status_info)

    # ---- bağlama
    def set_llm_enabled(self, enabled: bool) -> None:
        """LLM kapalıyken çeviri / prompt düğmeleri kullanılamaz."""
        self._llm_enabled = enabled
        hint = "" if enabled else "LLM kapalı; Ayarlar'dan açabilirsiniz."
        for btn in (self.translate_btn, self.enhance_btn):
            btn.setEnabled(enabled)
            btn.setToolTip(hint)

    def set_status_info(self, model: str, compute: str, llm: str) -> None:
        self.status_info.setText(f"{model} · {compute} · LLM: {llm}")

    def bind(
        self, controller, close_after_copy: bool = False, raise_on_result: bool = False
    ) -> None:
        self._controller = controller
        self.close_after_copy = close_after_copy
        self.raise_on_result = raise_on_result
        self.set_llm_enabled(getattr(controller, "llm_enabled", True))
        controller.session_updated.connect(self.on_session)
        controller.state_changed.connect(self.on_state)
        controller.error.connect(self._on_error)

    # ---- slotlar
    def on_session(self, s: Session) -> None:
        if s.id == self._ignored_session_id:
            # Geçmişten bir oturum görüntüleniyor; iptal edilen isteğin geç sonucu yok sayılır.
            return
        self.raw_pane.set_text(s.raw_text)
        self.corrected_pane.set_text(s.corrected_text)
        self._fill_changes(s)
        if self._pending == "translation" and s.translation:
            self.output_pane.set_text(s.translation)
            self._finish_pending()
        elif self._pending == "enhanced_prompt" and s.enhanced_prompt:
            self.output_pane.set_text(s.enhanced_prompt)
            self._finish_pending()
        elif self._pending is None and s.mode == "translate" and s.translation:
            self.output_pane.title_label.setText(TITLE_TRANSLATION)
            self.output_pane.set_text(s.translation)
        elif self._pending is None and s.mode == "prompt" and s.enhanced_prompt:
            self.output_pane.title_label.setText(TITLE_PROMPT)
            self.output_pane.set_text(s.enhanced_prompt)
        self._show_session_stats(s)  # _finish_pending mesajı temizledikten sonra yazılır

    def on_state(self, state: DictationState) -> None:
        self.record_action.setText("Durdur" if state is DictationState.RECORDING else "Kaydet")
        self.record_action.setEnabled(
            state not in (DictationState.TRANSCRIBING, DictationState.CORRECTING)
        )
        self.cancel_action.setEnabled(state in BUSY_STATES)
        if state is DictationState.RESULT:
            if self.raise_on_result:
                # 0 ms'ye erteleme: result_ready önce işlenir, yapıştırma hedefi korunur.
                QTimer.singleShot(0, self._activate_result)
        elif state is DictationState.RECORDING:
            self.output_pane.set_text("")
            self._finish_pending()

    def _activate_result(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()
        self.corrected_pane.editor.setFocus()

    def load_session(self, s: Session) -> None:
        """Geçmişten seçilen oturumu pencereye yükler; bekleyen LLM isteği iptal edilir."""
        self._pending = None
        live = getattr(self._controller, "session", None)
        self._ignored_session_id = getattr(live, "id", None)
        self.output_pane.set_busy(False)
        self.raw_pane.set_text(s.raw_text)
        self.corrected_pane.set_text(s.corrected_text)
        self.output_pane.set_text(s.translation or s.enhanced_prompt)
        self.output_pane.title_label.setText(
            TITLE_PROMPT if (s.enhanced_prompt and not s.translation) else TITLE_TRANSLATION
        )
        self._fill_changes(s)
        self._show_session_stats(s)
        self.translate_btn.setEnabled(self._llm_enabled)
        self.enhance_btn.setEnabled(self._llm_enabled)

    # ---- butonlar
    def _on_translate(self) -> None:
        text = self.corrected_pane.text().strip()
        if not text or self._controller is None:
            return
        self._start_pending("translation", TITLE_TRANSLATION)
        self._controller.request_translation(text)

    def _on_enhance(self) -> None:
        text = self.corrected_pane.text().strip()
        if not text or self._controller is None:
            return
        self._start_pending("enhanced_prompt", TITLE_PROMPT)
        self._controller.request_enhanced_prompt(text)

    def _start_pending(self, kind: str, title: str) -> None:
        self._pending = kind
        self._ignored_session_id = None  # kullanıcı yeni istek başlattı; sonuçlar yine gösterilir
        self.output_pane.title_label.setText(title)
        self.output_pane.set_text("")
        self.output_pane.set_busy(True)
        self.translate_btn.setEnabled(False)
        self.enhance_btn.setEnabled(False)
        self.statusBar().showMessage("LLM çalışıyor…")

    def _finish_pending(self) -> None:
        self._pending = None
        self.output_pane.set_busy(False)
        self.translate_btn.setEnabled(self._llm_enabled)
        self.enhance_btn.setEnabled(self._llm_enabled)
        self.statusBar().clearMessage()

    # ---- iç
    def _fill_changes(self, s: Session) -> None:
        self.changes_list.clear()
        for c in s.changes:
            if c.original.strip() == c.replacement.strip():  # görünür bir fark yok
                continue
            self.changes_list.addItem(f"{c.original}  →  {c.replacement}   ({c.reason})")

    def _show_session_stats(self, s: Session) -> None:
        if not s.corrected_text and not s.raw_text:
            return
        words = len((s.corrected_text or s.raw_text).split())
        self.statusBar().showMessage(f"{round(s.duration_s)} sn · {words} kelime")

    def _set_history_visible(self, visible: bool) -> None:
        self.history_panel.setVisible(visible)
        if visible:
            self.history_panel.raise_()

    def _on_dock_visibility(self, visible: bool) -> None:
        if self.history_action.isChecked() != visible:
            self.history_action.setChecked(visible)

    def _on_escape(self) -> None:
        """Esc: iş sürüyorsa iptal eder, boştaysa pencereyi gizler."""
        state = getattr(self._controller, "state", None)
        if self._controller is not None and state in BUSY_STATES:
            self._controller.cancel()
            return
        self.hide()

    def _on_copied(self, pane: TextPane) -> None:
        Toast.show_message(self, "Kopyalandı")
        if self.close_after_copy and pane is not self.raw_pane:
            self.hide()

    def _on_error(self, msg: str) -> None:
        self._finish_pending()
        self.statusBar().showMessage(msg, 8000)

    def closeEvent(self, event) -> None:  # pencere kapatma = gizle
        event.ignore()
        self.hide()
