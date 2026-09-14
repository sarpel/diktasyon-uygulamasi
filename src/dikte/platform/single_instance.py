from __future__ import annotations

import logging

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

log = logging.getLogger(__name__)
SHOW_MESSAGE = b"show"


class SingleInstance(QObject):
    activated = Signal()

    def __init__(self, name: str = "dikte-single-instance", parent=None):
        super().__init__(parent)
        self._name = name
        self._server: QLocalServer | None = None

    def try_acquire(self) -> bool:
        sock = QLocalSocket()
        sock.connectToServer(self._name)
        if sock.waitForConnected(300):
            sock.write(SHOW_MESSAGE)
            sock.waitForBytesWritten(300)
            sock.disconnectFromServer()
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
        conn.waitForReadyRead(300)
        if conn.readAll().data().startswith(SHOW_MESSAGE):
            self.activated.emit()
        conn.disconnectFromServer()
