from __future__ import annotations

from PySide6.QtCore import QElapsedTimer, Qt, QTimer, Signal
from PySide6.QtGui import QCursor, QGuiApplication
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

from dikte.core.state import DictationState
from dikte.ui.waveform import WaveformWidget

_STATUS = {
    DictationState.TRANSCRIBING: "Yazıya dökülüyor…",
    DictationState.CORRECTING: "Düzeltiliyor…",
}


class RecordingOverlay(QWidget):
    cancel_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setStyleSheet(
            "QWidget#panel{background:rgba(20,20,20,225);border-radius:14px;}"
            "QLabel{color:white;font-size:14px;}"
            "QPushButton{color:white;background:rgba(255,255,255,30);border:0;"
            "border-radius:6px;padding:4px 10px;font-size:13px;}"
            "QPushButton:hover{background:rgba(255,255,255,55);}"
        )
        panel = QWidget(self)
        panel.setObjectName("panel")
        lay = QHBoxLayout(panel)
        lay.setContentsMargins(16, 10, 16, 10)
        lay.setSpacing(12)
        self._dot = QLabel("●")
        self._dot.setStyleSheet("color:#E53935;font-size:22px;")
        self._wave = WaveformWidget()
        self._wave.setFixedSize(220, 44)
        self._time = QLabel("00:00")
        self._time.setMinimumWidth(48)
        self._status = QLabel("")
        self._status.hide()
        self.cancel_btn = QPushButton("Vazgeç")
        self.cancel_btn.setToolTip("Kaydı iptal et (Esc)")
        self.cancel_btn.clicked.connect(self.cancel_requested)
        for w in (self._dot, self._wave, self._time, self._status, self.cancel_btn):
            lay.addWidget(w)
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(panel)
        self._blink = QTimer(self)
        self._blink.setInterval(500)
        self._blink.timeout.connect(self._toggle_dot)
        self._clock = QTimer(self)
        self._clock.setInterval(250)
        self._clock.timeout.connect(self._update_time)
        self._elapsed = QElapsedTimer()
        self._dot_on = True

    # ---- kamu
    def show_recording(self) -> None:
        self._wave.clear()
        self._wave.show()
        self._time.show()
        self._status.hide()
        self._dot.show()
        self._dot_on = True
        self._dot.setVisible(True)
        self._elapsed.start()
        self._update_time()
        self._blink.start()
        self._clock.start()
        self._place()
        self.show()

    def show_status(self, text: str) -> None:
        self._blink.stop()
        self._clock.stop()
        self._dot.setStyleSheet("color:#F5A623;font-size:22px;")
        self._dot.setVisible(True)
        self._wave.hide()
        self._time.hide()
        self._status.setText(text)
        self._status.show()
        self.adjustSize()
        self._place()
        self.show()

    def hide_overlay(self) -> None:
        self._blink.stop()
        self._clock.stop()
        self._dot.setStyleSheet("color:#E53935;font-size:22px;")
        self.hide()

    def on_buckets(self, buckets) -> None:
        self._wave.push_buckets(tuple(buckets))

    def on_state(self, state: DictationState) -> None:
        if state is DictationState.RECORDING:
            self.show_recording()
        elif state in _STATUS:
            self.show_status(_STATUS[state])
        else:
            self.hide_overlay()

    # ---- iç
    def _toggle_dot(self) -> None:
        self._dot_on = not self._dot_on
        self._dot.setVisible(self._dot_on)

    def _update_time(self) -> None:
        s = self._elapsed.elapsed() // 1000
        self._time.setText(f"{s // 60:02d}:{s % 60:02d}")

    def _place(self) -> None:
        self.adjustSize()
        # Overlay imlecin bulunduğu ekrana konur; çok ekranlı kurulumda birincil ekrana kaçmaz.
        current = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        screen = current.availableGeometry()
        self.move(screen.center().x() - self.width() // 2, screen.bottom() - self.height() - 80)
