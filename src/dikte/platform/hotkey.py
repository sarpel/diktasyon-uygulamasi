from __future__ import annotations

import ctypes
import logging
import sys

from PySide6.QtCore import QAbstractNativeEventFilter, QCoreApplication, QObject, Signal

from dikte.platform.hotkey_parse import HotkeyParseError, HotkeySpec, parse_hotkey

if sys.platform == "win32":  # MSG yapısı yalnızca Windows'ta gerekli
    import ctypes.wintypes

log = logging.getLogger(__name__)
WM_HOTKEY = 0x0312
HOTKEY_ID = 0xD1C7


class _Filter(QAbstractNativeEventFilter):
    def __init__(self, on_hotkey, hotkey_id: int):
        super().__init__()
        self._on_hotkey = on_hotkey
        self._id = hotkey_id

    def nativeEventFilter(self, event_type, message):
        if event_type == b"windows_generic_MSG":
            msg = ctypes.wintypes.MSG.from_address(int(message))
            if msg.message == WM_HOTKEY and msg.wParam == self._id:
                self._on_hotkey()
                return True, 0
        return False, 0


class GlobalHotkey(QObject):
    activated = Signal()

    def __init__(self, hotkey_id: int = HOTKEY_ID, parent=None):
        super().__init__(parent)
        self._id = hotkey_id  # her örnek kendi kimliğiyle kaydolur
        self._filter: _Filter | None = None
        self._spec: HotkeySpec | None = None

    def register(self, spec: str, *, allow_bare: bool = False) -> bool:
        """allow_bare yalnızca uygulamanın ürettiği tek tuşluk kısayollar (Esc) içindir."""
        try:
            parsed = parse_hotkey(spec, allow_bare=allow_bare)
        except HotkeyParseError as exc:
            log.error("kısayol ayrıştırılamadı (%s): %s", spec, exc)
            return False
        self.unregister()
        if sys.platform != "win32":
            log.warning("Global kısayol yalnızca Windows'ta desteklenir (%s)", parsed.label)
            return False
        ok = ctypes.windll.user32.RegisterHotKey(None, self._id, parsed.modifiers, parsed.vk)
        if not ok:
            err = ctypes.GetLastError()
            log.error("RegisterHotKey başarısız (%s), hata=%s", parsed.label, err)
            return False
        self._filter = _Filter(self.activated.emit, self._id)
        QCoreApplication.instance().installNativeEventFilter(self._filter)
        self._spec = parsed
        log.info("Global kısayol kaydedildi: %s", parsed.label)
        return True

    def unregister(self) -> None:
        if sys.platform == "win32" and self._spec is not None:
            ctypes.windll.user32.UnregisterHotKey(None, self._id)
        if self._filter is not None:
            app = QCoreApplication.instance()
            if app is not None:
                app.removeNativeEventFilter(self._filter)
        self._filter, self._spec = None, None

    @property
    def label(self) -> str:
        return self._spec.label if self._spec else ""
