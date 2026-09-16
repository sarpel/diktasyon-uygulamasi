from __future__ import annotations

import logging

from PySide6.QtCore import QEventLoop, QObject, QTimer, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

log = logging.getLogger(__name__)
DEFAULT_NAME = "dikte-single-instance"
SHOW_MESSAGE = b"show"
TOGGLE_MESSAGE = b"toggle"
START_MESSAGE = b"start"
STOP_MESSAGE = b"stop"
ACK = b"ok"
_TIMEOUT_MS = 2000


def send_command(name: str, message: bytes, timeout_ms: int = _TIMEOUT_MS) -> bool:
    """Çalışan örneğe komut yollar ve okunduğuna dair onay bekler.

    Windows'ta named pipe, yazan taraf kapattığında okunmamış veriyi düşürebilir;
    bu yüzden gönderim ancak sunucu ACK yolladığında başarılı sayılır. Bekleme
    iç içe bir olay döngüsüyle yapılır, böylece sunucu aynı süreçte olsa bile
    (testler) ilerleyebilir.
    """
    sock = QLocalSocket()
    loop = QEventLoop()
    result = {"ok": False, "done": False}

    def finish(ok: bool) -> None:
        if result["done"]:
            return
        result["ok"], result["done"] = ok, True
        loop.quit()

    def on_connected() -> None:
        sock.write(message)
        sock.flush()

    sock.connected.connect(on_connected)
    sock.readyRead.connect(lambda: finish(bytes(sock.readAll().data()).startswith(ACK)))
    sock.errorOccurred.connect(lambda _err: finish(False))
    sock.disconnected.connect(lambda: finish(False))

    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(lambda: finish(False))
    timer.start(timeout_ms)

    sock.connectToServer(name)
    if not result["done"]:
        loop.exec()
    timer.stop()
    sock.abort()
    return result["ok"]


class SingleInstance(QObject):
    activated = Signal()
    toggle_requested = Signal(str)  # mod: "correct" | "translate" | "prompt"
    start_requested = Signal(str)
    stop_requested = Signal()

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
        if self._server is None:
            return
        conn = self._server.nextPendingConnection()
        if conn is None:
            return
        conn.readyRead.connect(lambda: self._handle(conn))
        if conn.bytesAvailable():  # veri bağlantıyla birlikte gelmiş olabilir
            self._handle(conn)

    def _handle(self, conn: QLocalSocket) -> None:
        payload = bytes(conn.readAll().data())
        if not payload:
            return
        if payload.startswith(TOGGLE_MESSAGE):
            self.toggle_requested.emit(_parse_mode(payload, TOGGLE_MESSAGE))
        elif payload.startswith(START_MESSAGE):
            self.start_requested.emit(_parse_mode(payload, START_MESSAGE))
        elif payload.startswith(STOP_MESSAGE):
            self.stop_requested.emit()
        elif payload.startswith(SHOW_MESSAGE):
            self.activated.emit()
        else:
            log.warning("bilinmeyen IPC komutu: %r", payload[:32])
        conn.write(ACK)
        conn.flush()
        conn.disconnectFromServer()


def _parse_mode(payload: bytes, prefix: bytes) -> str:
    """`b"toggle:translate"` → "translate"; salt `b"toggle"` → varsayılan "correct"."""
    rest = payload[len(prefix) :]
    if rest.startswith(b":"):
        return rest[1:].decode("ascii", errors="replace")
    return "correct"
