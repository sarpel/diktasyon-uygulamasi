"""Kayıt sırasında ekranda duran çerçevesiz gösterge (HUD): dalga, süre, durum, canlı metin."""

from __future__ import annotations

from PySide6.QtCore import QElapsedTimer, QPoint, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QCursor, QGuiApplication, QMouseEvent
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from dikte.core.state import DictationState
from dikte.ui.waveform import WaveformWidget

_STATUS = {
    DictationState.TRANSCRIBING: "Yazıya dökülüyor…",
    DictationState.CORRECTING: "Düzeltiliyor…",
}
PARTIAL_MAX_CHARS = 70
EDGE_MARGIN = 80  # alt/üst konumda ekran kenarından uzaklık (piksel)


class RecordingOverlay(QWidget):
    """Odak çalmadan her zaman üstte duran kayıt göstergesi; `on_state` ile duruma uyar.

    Fareyle sürüklenerek taşınabilir; bırakıldığında konum "custom" olur ve `moved(x, y)`
    yayılır (kaydetmek uygulamanın işidir). "Vazgeç" düğmesi `cancel_requested` yayar.
    """

    cancel_requested = Signal()
    moved = Signal(int, int)  # sürükleme bırakıldığında yeni sol-üst köşe (global)

    def __init__(self, parent=None):
        super().__init__(
            parent,
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        # Bilerek koyu: yarı saydam, her masaüstü arka planının üzerinde okunaklı kalması gereken
        # bir HUD panelidir; sistem temasına bağlamak kontrastı öngörülemez kılar.
        self.setStyleSheet(
            "QWidget#panel{background:rgba(20,20,20,225);border-radius:14px;}"
            "QLabel{color:white;font-size:14px;}"
            "QPushButton{color:white;background:rgba(255,255,255,30);border:0;"
            "border-radius:6px;padding:4px 10px;font-size:13px;}"
            "QPushButton:hover{background:rgba(255,255,255,55);}"
        )
        panel = QWidget(self)
        panel.setObjectName("panel")
        row = QHBoxLayout()
        row.setSpacing(12)
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
        self.cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setCursor(Qt.CursorShape.OpenHandCursor)  # panel sürüklenerek taşınabilir
        for w in (self._dot, self._wave, self._time, self._status, self.cancel_btn):
            row.addWidget(w)
        self._partial = QLabel("")
        self._partial.setStyleSheet("color:#BBBBBB;font-size:12px;")
        self._partial.hide()
        self._warning = QLabel("")
        self._warning.setStyleSheet("color:#F5A623;font-size:12px;")
        self._warning.hide()
        panel_lay = QVBoxLayout(panel)
        panel_lay.setContentsMargins(16, 10, 16, 10)
        panel_lay.setSpacing(6)
        panel_lay.addLayout(row)
        panel_lay.addWidget(self._partial)
        panel_lay.addWidget(self._warning)
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
        self._error_token = 0
        self._pending_error_token = 0
        self._showing_error = False
        self._error_timer = QTimer(self)
        self._error_timer.setSingleShot(True)
        self._error_timer.timeout.connect(self._on_error_timeout)
        self._warning_timer = QTimer(self)
        self._warning_timer.setSingleShot(True)
        self._warning_timer.timeout.connect(self._hide_warning)
        self._position = "bottom"
        self._custom_xy: tuple[int, int] | None = None
        self._drag_offset: QPoint | None = None
        self._drag_start: QPoint | None = None

    # ---- kamu
    def set_position(self, position: str, xy: tuple[int, int] | None) -> None:
        """ "bottom"/"top": imlecin ekranında alt/üst orta; "custom": kaydedilmiş sol-üst köşe.

        "custom" konumu hiçbir ekranda değilse (ör. monitör çıkarıldı) alt ortaya düşülür."""
        self._position = position
        self._custom_xy = (int(xy[0]), int(xy[1])) if xy is not None else None
        if self.isVisible():
            self._place()

    def show_recording(self) -> None:
        self._showing_error = False
        self._clear_warning()
        self._wave.clear()
        self._wave.show()
        self._time.show()
        self._status.hide()
        self._partial.setText("")
        self._partial.hide()
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
        self._showing_error = False
        self._clear_warning()
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

    def show_error(self, text: str, ms: int = 2500) -> None:
        """Hatayı `ms` boyunca gösterip gizler; araya giren durum değişikliği gizlemeyi
        iptal eder."""
        self._clear_warning()
        self._blink.stop()
        self._clock.stop()
        self._error_timer.stop()
        self._showing_error = True
        self._error_token += 1
        self._pending_error_token = self._error_token
        self._dot.setStyleSheet("color:#E53935;font-size:22px;")
        self._dot.setVisible(True)
        self._wave.hide()
        self._time.hide()
        self._status.setText(f"✗ {text}")
        self._status.show()
        self.adjustSize()
        self._place()
        self.show()
        self._error_timer.start(ms)

    def _on_error_timeout(self) -> None:
        # `self._error_token`, aradan yeni bir on_state(...) veya show_error çağrısıyla
        # değişmiş olur; bu durumda gizleme atlanır, yeni duruma dokunulmaz.
        if self._pending_error_token == self._error_token:
            self.hide_overlay()

    def hide_overlay(self) -> None:
        self._blink.stop()
        self._clock.stop()
        self._showing_error = False
        self._clear_warning()
        self._dot.setStyleSheet("color:#E53935;font-size:22px;")
        self._partial.setText("")
        self._partial.hide()
        self.hide()

    def show_warning(self, text: str, ms: int = 4000) -> None:
        """Kaydı bozmadan ölümcül olmayan bir uyarı satırı gösterir; `ms` sonra kendisi kalkar.

        Hata yolundan (show_error) bilerek ayrıdır: kayıt modu, dalga ve süre sayacı sürer.
        """
        self._warning.setText(f"⚠ {text}")
        self._warning.show()
        self._resize_keeping_anchor()
        self._warning_timer.start(ms)

    def show_partial(self, text: str) -> None:
        """Kayıt sırasında henüz teslim edilmemiş canlı transkripti dalganın altında gösterir."""
        truncated = text[-PARTIAL_MAX_CHARS:]
        if len(text) > PARTIAL_MAX_CHARS:
            truncated = "…" + truncated
        self._partial.setText(truncated)
        self._partial.setVisible(bool(truncated))

    def on_buckets(self, buckets) -> None:
        self._wave.push_buckets(tuple(buckets))

    def on_state(self, state: DictationState) -> None:
        """RECORDING'de kayıt görünümü, TRANSCRIBING/CORRECTING'de durum metni; diğerlerinde
        gizlenir (gösterilen bir hata varsa kendi süresi dolana kadar kalır)."""
        if state is DictationState.RECORDING:
            self._error_token += 1  # bekleyen hata gizleme zamanlayıcısını geçersiz kılar
            self.show_recording()
        elif state in _STATUS:
            self._error_token += 1
            self.show_status(_STATUS[state])
        elif not self._showing_error:
            # error sinyali her zaman state_changed'dan hemen önce gelir (bkz.
            # controller._on_stt_error); IDLE/RESULT'a bu geçiş yüzünden anında gizlemek,
            # kullanıcının hata mesajını hiç görmeden overlay'in kaybolmasına yol açardı.
            # Gösterilen bir hata varsa kendi zamanlayıcısı (_error_timer) bitirsin.
            self._error_token += 1
            self.hide_overlay()

    # ---- sürükleme
    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            global_pos = event.globalPosition().toPoint()
            self._drag_start = global_pos
            self._drag_offset = global_pos - self.frameGeometry().topLeft()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._drag_offset is not None:
            dragged = event.globalPosition().toPoint() != self._drag_start
            self._drag_offset = self._drag_start = None
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            event.accept()
            if dragged:
                # Uygulama ayarı kaydedene kadar da sonraki gösterimler bu konumda kalsın.
                self._position = "custom"
                self._custom_xy = (self.x(), self.y())
                self.moved.emit(self.x(), self.y())
            return
        super().mouseReleaseEvent(event)

    # ---- iç
    def _hide_warning(self) -> None:
        self._warning.hide()
        self._resize_keeping_anchor()

    def _clear_warning(self) -> None:
        self._warning_timer.stop()
        self._warning.setText("")
        self._warning.hide()

    def _resize_keeping_anchor(self) -> None:
        """Yükseklik değişince alt konumda alt kenarı sabit tutar (panel yukarı büyür)."""
        old = self.geometry()
        self.adjustSize()
        if self._position == "bottom" and self.isVisible():
            self.move(old.x(), old.y() + old.height() - self.height())

    def _toggle_dot(self) -> None:
        self._dot_on = not self._dot_on
        self._dot.setVisible(self._dot_on)

    def _update_time(self) -> None:
        s = self._elapsed.elapsed() // 1000
        self._time.setText(f"{s // 60:02d}:{s % 60:02d}")

    def _place(self) -> None:
        self.adjustSize()
        if self._position == "custom":
            target = self._custom_target()
            if target is not None:
                self.move(target)
                return
        # Overlay imlecin bulunduğu ekrana konur; çok ekranlı kurulumda birincil ekrana kaçmaz.
        current = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        screen = current.availableGeometry()
        x = screen.center().x() - self.width() // 2
        if self._position == "top":
            self.move(x, screen.top() + EDGE_MARGIN)
        else:
            self.move(x, screen.bottom() - self.height() - EDGE_MARGIN)

    def _custom_target(self) -> QPoint | None:
        """Kaydedilmiş konumu içeren ekrana sığacak biçimde kırpar; hiçbir ekranda değilse
        (ör. ikinci monitör çıkarıldı) None döner ve varsayılan alt konuma düşülür."""
        if self._custom_xy is None:
            return None
        point = QPoint(*self._custom_xy)
        screen = QGuiApplication.screenAt(point)
        if screen is None:
            return None
        return _clamp(point, self.size().width(), self.size().height(), screen.availableGeometry())


def _clamp(point: QPoint, width: int, height: int, area: QRect) -> QPoint:
    x = max(area.left(), min(point.x(), area.right() - width + 1))
    y = max(area.top(), min(point.y(), area.bottom() - height + 1))
    return QPoint(x, y)
