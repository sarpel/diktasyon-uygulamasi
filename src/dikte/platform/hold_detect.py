"""Bas-konuş desteği: kısayolun basılı tutulup tutulmadığını tuş durumunu yoklayarak ayırt eder.

Gerçek tuş durumu yalnızca Windows'ta okunur; diğer platformlarda her basış kısa basış sayılır.
"""

from __future__ import annotations

import sys
from collections.abc import Callable

from PySide6.QtCore import QElapsedTimer, QObject, QTimer, Signal


def _default_key_probe(vk: int) -> bool:
    """Windows'ta gerçek tuş durumunu okur; diğer platformlarda bas-konuş desteklenmez."""
    if sys.platform == "win32":
        import ctypes

        return bool(ctypes.windll.user32.GetAsyncKeyState(vk) & 0x8000)
    return False


class HoldDetector(QObject):
    """Kısayol basılı mı, kısa mı basıldı ayırt eder (bas-konuş / tıkla-aç melezi)."""

    held = Signal()  # tuş hold_ms boyunca basılı kaldı → bas-konuş başlar
    released = Signal()  # bas-konuş sırasında tuş bırakıldı
    tapped = Signal()  # hold_ms'den önce bırakıldı → tıkla-aç

    def __init__(
        self,
        key_probe: Callable[[int], bool] | None = None,
        *,
        hold_ms: int = 250,
        poll_ms: int = 30,
        parent=None,
    ):
        super().__init__(parent)
        self._probe = key_probe or _default_key_probe
        self._hold_ms = hold_ms
        self._vk = 0
        self._held = False
        self._armed = False
        self._elapsed = QElapsedTimer()
        self._timer = QTimer(self)
        self._timer.setInterval(poll_ms)
        self._timer.timeout.connect(self._poll)

    @property
    def armed(self) -> bool:
        return self._armed

    def arm(self, vk: int) -> None:
        """Kısayol tetiklendiğinde çağrılır: `vk` tuşunu bırakılana kadar yoklamaya başlar.

        Zaten kuruluysa (önceki basış sürüyorsa) çağrı yok sayılır."""
        if self._armed:
            return
        self._vk = vk
        self._held = False
        self._armed = True
        self._elapsed.start()
        self._timer.start()

    def _poll(self) -> None:
        elapsed = self._elapsed.elapsed()
        down = self._probe(self._vk)
        if down and elapsed >= self._hold_ms and not self._held:
            self._held = True
            self.held.emit()
            return
        if down:
            return
        self._timer.stop()
        self._armed = False
        (self.released if self._held else self.tapped).emit()
