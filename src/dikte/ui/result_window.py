from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QHBoxLayout,
    QListWidget,
    QMainWindow,
    QPushButton,
    QSplitter,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from dikte.core.state import DictationState, Session
from dikte.ui.text_pane import TextPane
from dikte.ui.toast import Toast

TITLE_TRANSLATION = "İngilizce Çeviri"
TITLE_PROMPT = "Agent Prompt (EN)"


class ResultWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Dikte")
        self.resize(1100, 620)
        self._controller = None
        self._pending: str | None = None  # "translation" | "enhanced_prompt"
        self.close_after_copy = False

        self.raw_pane = TextPane("Ham")
        self.corrected_pane = TextPane("Düzeltilmiş")
        self.output_pane = TextPane(TITLE_TRANSLATION)
        self.changes_list = QListWidget()
        self.changes_list.setMaximumHeight(110)
        self.changes_list.setToolTip("LLM'in yaptığı düzeltmeler")

        self.translate_btn = QPushButton("İngilizce'ye Çevir")
        self.enhance_btn = QPushButton("Agent Prompt'a Dönüştür")
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
        self.setStatusBar(QStatusBar())

        for pane in (self.raw_pane, self.corrected_pane, self.output_pane):
            pane.copied.connect(lambda _t, p=pane: self._on_copied(p))
        QShortcut(QKeySequence("Ctrl+Shift+C"), self, activated=self.corrected_pane._copy)

    # ---- bağlama
    def bind(self, controller) -> None:
        self._controller = controller
        controller.session_updated.connect(self.on_session)
        controller.state_changed.connect(self.on_state)
        controller.error.connect(self._on_error)

    # ---- slotlar
    def on_session(self, s: Session) -> None:
        self.raw_pane.set_text(s.raw_text)
        self.corrected_pane.set_text(s.corrected_text)
        self.changes_list.clear()
        for c in s.changes:
            self.changes_list.addItem(f"{c.original}  →  {c.replacement}   ({c.reason})")
        if self._pending == "translation" and s.translation:
            self.output_pane.set_text(s.translation)
            self._finish_pending()
        elif self._pending == "enhanced_prompt" and s.enhanced_prompt:
            self.output_pane.set_text(s.enhanced_prompt)
            self._finish_pending()

    def on_state(self, state: DictationState) -> None:
        if state is DictationState.RESULT:
            self.showNormal()
            self.raise_()
            self.activateWindow()
            self.corrected_pane.editor.setFocus()
        elif state is DictationState.RECORDING:
            self.output_pane.set_text("")
            self._finish_pending()

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
        self.output_pane.title_label.setText(title)
        self.output_pane.set_text("")
        self.output_pane.set_busy(True)
        self.translate_btn.setEnabled(False)
        self.enhance_btn.setEnabled(False)
        self.statusBar().showMessage("LLM çalışıyor…")

    def _finish_pending(self) -> None:
        self._pending = None
        self.output_pane.set_busy(False)
        self.translate_btn.setEnabled(True)
        self.enhance_btn.setEnabled(True)
        self.statusBar().clearMessage()

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
