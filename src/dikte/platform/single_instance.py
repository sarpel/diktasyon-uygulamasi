from __future__ import annotations

import logging

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

log = logging.getLogger(__name__)
DEFAULT_NAME = "dikte-single-instance"
SHOW_MESSAGE = b"show"
TOGGLE_MESSAGE = b"toggle"
_TIMEOUT_MS = 300


def send_command(name: str, message: bytes, timeout_ms: int = _TIMEOUT_MS) -> bool:
    """Çalışan örneğe komut yollar; dinleyen örnek yoksa False döner."""
    sock = QLocalSocket()
    sock.connectToServer(name)
    if not sock.waitForConnected(timeout_ms):
        return False
    sock.write(message)
    sock.waitForBytesWritten(timeout_ms)
    sock.disconnectFromServer()
    return True


class SingleInstance(QObject):
    activated = Signal()
    toggle_requested = Signal()

    def __init__(self, name: str = DEFAULT_NAME, parent=None):
        super().__init__(parent)
        self._name = name
        self._server: QLocalServer | None = None

    @property
    def name(self) -> str:
        return self._name

    def try_acquire(self) -> bool:
        if send_command(self._name, SHOW_MESSAGE):
            return False
        QLocalServer.removeServer(self._name)  # çökmüş önceki örnekten kalan soket
        self._server = QLocalServer(self)
        self._server.newConnection.connect(self._on_connection)
        if not self._server.listen(self._name):
            log.error("QLocalServer dinleyemedi: %s", self._server.errorString())
            return True  # kilit kurulamasa da çalışmaya devam et
        return True

    def _on_connection(self) -> None:
        conn = self._server.nextPendingConnection()
        if conn is None:
            return
        conn.waitForReadyRead(_TIMEOUT_MS)
        payload = conn.readAll().data()
        if payload.startswith(TOGGLE_MESSAGE):
            self.toggle_requested.emit()
        elif payload.startswith(SHOW_MESSAGE):
            self.activated.emit()
        else:
            log.warning("bilinmeyen IPC komutu: %r", payload[:32])
        conn.disconnectFromServer()
