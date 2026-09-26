"""Tek örnek kilidi ve yerel IPC (QLocalServer/QLocalSocket).

İkinci başlatma çalışan örneği öne getirir; `dikte --toggle/--start/--stop` komutları
çalışan örneğe buradan iletilir. Soket/pipe adı kullanıcıya özgüdür.
"""

from __future__ import annotations

import getpass
import hashlib
import logging
import os
import sys
from collections.abc import Callable, Mapping
from pathlib import Path

from PySide6.QtCore import QEventLoop, QObject, QTimer, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

log = logging.getLogger(__name__)
_BASE_NAME = "dikte-single-instance"
SHOW_MESSAGE = b"show"
TOGGLE_MESSAGE = b"toggle"
START_MESSAGE = b"start"
STOP_MESSAGE = b"stop"
ACK = b"ok"
_TIMEOUT_MS = 2000


def _current_user() -> str:
    if hasattr(os, "getuid"):
        return f"uid{os.getuid()}"
    return getpass.getuser()


def default_server_name(
    *,
    platform: str = sys.platform,
    env: Mapping[str, str] | None = None,
    user_probe: Callable[[], str] = _current_user,
) -> str:
    """Kullanıcıya özgü IPC adı. İstemci (`--toggle`) ve sunucu aynı işlevi çağırır.

    Sabit bir ad tüm kullanıcılar için ortaktı: Linux'ta soket herkesin yazabildiği
    /tmp altında açılır, ikinci kullanıcı dinleyemez (IPC ölür) ve başka bir kullanıcı
    adı önceden kapıp komutları çalabilirdi. Linux'ta yalnızca kullanıcının erişebildiği
    `$XDG_RUNTIME_DIR` (0700) tercih edilir; yoksa ve Windows'ta (named pipe'lar makine
    genelinde ortak ad alanındadır) ada kullanıcı adının kısa bir özeti eklenir."""
    env = os.environ if env is None else env
    if not platform.startswith("win"):
        runtime_dir = env.get("XDG_RUNTIME_DIR", "")
        if runtime_dir and Path(runtime_dir).is_dir():
            return str(Path(runtime_dir) / _BASE_NAME)
    try:
        user = user_probe()
    except Exception:  # getpass.getuser: OSError/KeyError/ImportError olabilir
        log.exception("kullanıcı adı alınamadı; IPC adı ortam değişkeninden türetiliyor")
        user = env.get("USERNAME") or env.get("USER") or "bilinmeyen"
    digest = hashlib.sha256(user.encode("utf-8")).hexdigest()[:12]
    return f"{_BASE_NAME}-{digest}"


DEFAULT_NAME = default_server_name()


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


def _server_socket_exists(name: str, timeout_ms: int = 500) -> bool:
    """Bir soket bağlantısı kabul ediliyor mu (sunucu canlı) — ACK beklemeden, yalnızca
    bağlantı aşaması. `send_command`'ın SHOW isteği zaman aşımına uğraması iki farklı
    durumdan olabilir: sunucu hiç yok (eski/çökmüş örnekten kalan soket dosyası — silmek
    güvenli) ya da sunucu canlı ama meşgul (GUI iş parçacığı bloke — soketi silip ikinci
    bir örnek başlatmak veri kaybına/duplicate örneğe yol açar). Bu ayrımı yapar."""
    sock = QLocalSocket()
    loop = QEventLoop()
    result = {"connected": False, "done": False}

    def finish(connected: bool) -> None:
        if result["done"]:
            return
        result["connected"], result["done"] = connected, True
        loop.quit()

    sock.connected.connect(lambda: finish(True))
    sock.errorOccurred.connect(lambda _err: finish(False))

    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(lambda: finish(False))
    timer.start(timeout_ms)

    sock.connectToServer(name)
    if not result["done"]:
        loop.exec()
    timer.stop()
    sock.abort()
    return result["connected"]


class SingleInstance(QObject):
    """Tek örnek sunucusu; gelen IPC komutlarını sinyallere çevirir ve her birine ACK yollar.

    Sinyaller: `activated` (show), `toggle_requested(mod)`, `start_requested(mod)`,
    `stop_requested`. Mod her zaman "correct" | "translate" | "prompt"tan biridir.
    """

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
        """Bu süreç tek örnek olacaksa True (sunucu dinlemeye başlar); False = başka örnek var.

        Çalışan örneğe önce "show" gönderilir (öne gelsin diye). Sunucu canlı ama yanıtsızsa
        da False döner. Sunucu dinleyemezse hata günlüğe yazılır, yine True döner."""
        if send_command(self._name, SHOW_MESSAGE):
            return False
        if _server_socket_exists(self._name):
            # Sunucu canlı (bağlantı kabul edildi) ama SHOW isteğine zamanında ACK
            # dönmedi — örn. GUI iş parçacığı meşgul. Soketi silip ikinci bir örnek
            # başlatmak yerine yalnızca başlatmayı reddet.
            log.warning("çalışan örnek meşgul görünüyor, ikinci başlatma reddedildi")
            return False
        QLocalServer.removeServer(self._name)  # çökmüş önceki örnekten kalan soket
        self._server = QLocalServer(self)
        # Yalnızca aynı kullanıcı bağlanabilsin (Unix: soket 0700; Windows: pipe DACL'i).
        self._server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
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


_VALID_MODES = ("correct", "translate", "prompt")


def _parse_mode(payload: bytes, prefix: bytes) -> str:
    """`b"toggle:translate"` → "translate"; salt `b"toggle"` → varsayılan "correct".

    Soket `UserAccessOption` ile açılır ve adı kullanıcıya özgüdür (bkz.
    `default_server_name`), yani yalnızca aynı kullanıcının yerel süreçleri bağlanabilir
    (sertleştirme notu, F054). Yine de o süreçlerden gelen doğrulanmamış bir dize
    denetleyiciye `mode` olarak ulaşmasın diye tanınmayan değerler "correct"a düşürülür."""
    rest = payload[len(prefix) :]
    if not rest.startswith(b":"):
        return "correct"
    mode = rest[1:].decode("ascii", errors="replace")
    return mode if mode in _VALID_MODES else "correct"
