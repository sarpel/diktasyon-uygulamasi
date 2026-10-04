"""Tek örnek kilidi ve yerel IPC (QLocalServer/QLocalSocket).

İkinci başlatma çalışan örneği öne getirir; `dikte --toggle/--start/--stop` komutları
çalışan örneğe buradan iletilir. Soket/pipe adı kullanıcıya özgüdür.

Ad tahmin edilebilir olduğundan (başka bir yerel kullanıcı önceden kapabilir) var olan
bir sunucuya güvenmeden önce karşı taraf doğrulanır: Linux'ta SO_PEERCRED ile sunucu
sürecinin uid'si, diğer Unix'lerde soket dosyasının sahibi, Windows'ta
GetNamedPipeServerProcessId ile bulunan sürecin kullanıcı SID'i. Doğrulanamayan sunucuya
komut/“göster” isteği yazılmaz. Unix'te soket yalnızca kullanıcıya ait 0700 bir dizinde
açılır.
"""

from __future__ import annotations

import enum
import getpass
import hashlib
import logging
import os
import socket
import stat
import struct
import sys
import tempfile
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, Protocol

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
# sockaddr_un.sun_path sınırı 108 bayt (Linux); güvenli pay bırakılır.
_MAX_SOCKET_PATH = 100

# (soket tanıtıcısı, sunucu adı) → True: aynı kullanıcı, False: başka kullanıcı,
# None: doğrulanamadı (güvenilmez sayılır).
PeerVerifier = Callable[[int, str], "bool | None"]


class IpcStatus(enum.Enum):
    """`SingleInstance.try_acquire` sonrası IPC durumu."""

    NOT_STARTED = "not_started"
    LISTENING = "listening"  # bu süreç tek örnek, komutları dinliyor
    ALREADY_RUNNING = "already_running"  # doğrulanmış başka örnek var, ona "göster" iletildi
    BUSY = "busy"  # doğrulanmış örnek var ama yanıt vermiyor
    UNAVAILABLE = "unavailable"  # dinleme başlatılamadı; uygulama IPC'siz çalışır
    UNTRUSTED = "untrusted"  # ad doğrulanamayan bir süreçte; ona bağlanılmadı, IPC'siz çalışır


_STATUS_MESSAGES: dict[IpcStatus, str] = {
    IpcStatus.UNAVAILABLE: (
        "Dikte'nin komut kanalı açılamadı; `dikte --toggle` gibi komutlar ve ikinci "
        "başlatmanın engellenmesi bu oturumda çalışmayacak. Sorun sürerse Dikte'yi yeniden "
        "başlatın."
    ),
    IpcStatus.UNTRUSTED: (
        "Dikte'nin komut kanalı başka bir kullanıcıya ait ya da doğrulanamayan bir süreç "
        "tarafından tutuluyor; güvenlik için ona bağlanılmadı. `dikte --toggle` gibi "
        "komutlar bu oturumda çalışmayacak."
    ),
}


def _current_user() -> str:
    if hasattr(os, "getuid"):
        return f"uid{os.getuid()}"
    return getpass.getuser()


def _current_uid() -> int:
    return os.getuid()


def _lstat_owner(path: Path) -> int:
    return os.lstat(path).st_uid


def _ensure_private_dir(
    path: Path, uid: int, owner_probe: Callable[[Path], int], *, create: bool
) -> bool:
    """`path` yalnızca `uid`'ye ait, sembolik bağ olmayan ve 0700 bir dizin mi (gerekirse
    oluşturur). Başkasına aitse ya da herkese açıksa kullanılmaz."""
    try:
        if create:
            path.mkdir(mode=0o700, parents=True, exist_ok=True)
        st = os.lstat(path)
        if not stat.S_ISDIR(st.st_mode):
            log.warning("IPC dizini bir dizin değil (sembolik bağ?), kullanılmıyor: %s", path)
            return False
        if owner_probe(path) != uid:
            log.warning("IPC dizini başka bir kullanıcıya ait, kullanılmıyor: %s", path)
            return False
        if stat.S_IMODE(st.st_mode) & 0o077:
            if not create:
                log.warning("IPC dizini başkalarına açık (0700 değil), kullanılmıyor: %s", path)
                return False
            path.chmod(0o700)  # kendi dizinimiz: izinleri daralt
    except OSError:
        log.exception("IPC dizini hazırlanamadı: %s", path)
        return False
    return True


def _private_unix_dir(
    env: Mapping[str, str],
    uid: int,
    tempdir: str,
    home: Path,
    owner_probe: Callable[[Path], int],
) -> Path | None:
    runtime_dir = env.get("XDG_RUNTIME_DIR", "")
    if (
        runtime_dir
        and Path(runtime_dir).is_dir()
        and _ensure_private_dir(Path(runtime_dir), uid, owner_probe, create=False)
    ):
        return Path(runtime_dir)
    for candidate in (Path(tempdir) / f"dikte-{uid}", home / ".cache" / "dikte"):
        if len(str(candidate / _BASE_NAME)) > _MAX_SOCKET_PATH:
            continue
        if _ensure_private_dir(candidate, uid, owner_probe, create=True):
            return candidate
    return None


def default_server_name(
    *,
    platform: str = sys.platform,
    env: Mapping[str, str] | None = None,
    user_probe: Callable[[], str] = _current_user,
    uid_probe: Callable[[], int] | None = None,
    tempdir: str | None = None,
    home: Path | None = None,
    owner_probe: Callable[[Path], int] = _lstat_owner,
) -> str:
    """Kullanıcıya özgü IPC adı. İstemci (`--toggle`) ve sunucu aynı işlevi çağırır.

    Unix'te soket yalnızca kullanıcıya ait 0700 bir dizinde açılır: önce
    `$XDG_RUNTIME_DIR` (sahibi ve izinleri doğrulanır), yoksa geçici dizinde
    `dikte-<uid>`, o da başka bir kullanıcı tarafından önceden kapılmışsa
    `~/.cache/dikte`. Windows'ta (named pipe'lar makine genelinde ortak ad alanındadır)
    ada kullanıcı adının kısa bir özeti eklenir; sunucu bağlanırken ayrıca doğrulanır."""
    env = os.environ if env is None else env
    if not platform.startswith("win"):
        if uid_probe is None and hasattr(os, "getuid"):
            uid_probe = _current_uid
        if uid_probe is not None:
            private = _private_unix_dir(
                env,
                uid_probe(),
                tempfile.gettempdir() if tempdir is None else tempdir,
                Path.home() if home is None else home,
                owner_probe,
            )
            if private is not None:
                return str(private / _BASE_NAME)
            log.error("kullanıcıya özel IPC dizini bulunamadı; tahmin edilebilir ad kullanılıyor")
    try:
        user = user_probe()
    except Exception:  # getpass.getuser: OSError/KeyError/ImportError olabilir
        log.exception("kullanıcı adı alınamadı; IPC adı ortam değişkeninden türetiliyor")
        user = env.get("USERNAME") or env.get("USER") or "bilinmeyen"
    digest = hashlib.sha256(user.encode("utf-8")).hexdigest()[:12]
    return f"{_BASE_NAME}-{digest}"


DEFAULT_NAME = default_server_name()


# --- Karşı taraf (sunucu) doğrulaması ---------------------------------------------------


def unix_peer_uid(descriptor: int, name: str) -> int | None:
    """Bağlı Unix soketinin karşı tarafının uid'si; bilinemiyorsa None.

    Linux'ta SO_PEERCRED (sunucu sürecinin kimliği, çekirdekten); diğer Unix'lerde soket
    dosyasının sahibi (yalnızca tam yol adlarında)."""
    so_peercred = getattr(socket, "SO_PEERCRED", None)
    if so_peercred is not None and descriptor >= 0:
        with socket.fromfd(descriptor, socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            creds = sock.getsockopt(socket.SOL_SOCKET, so_peercred, struct.calcsize("3i"))
        _pid, uid, _gid = struct.unpack("3i", creds)
        return uid
    if Path(name).is_absolute():
        return Path(name).stat().st_uid
    return None


def unix_peer_is_current_user(
    descriptor: int, name: str, *, uid_probe: Callable[[], int] = _current_uid
) -> bool | None:
    """Sunucu bu kullanıcıya mı ait? None: doğrulanamadı."""
    uid = unix_peer_uid(descriptor, name)
    return None if uid is None else uid == uid_probe()


class WindowsSecurityApi(Protocol):
    """Windows güvenlik çağrıları (testlerde sahtesi verilir)."""

    def server_pid(self, handle: int) -> int | None: ...

    def process_user_sid(self, pid: int) -> str | None: ...

    def current_user_sid(self) -> str | None: ...


class _CtypesWindowsSecurityApi:
    """kernel32/advapi32 üzerinden: GetNamedPipeServerProcessId + süreç belirtecinin
    kullanıcı SID'i (TokenUser). Başarısız her çağrı None döndürür."""

    _PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    _TOKEN_QUERY = 0x0008
    _TOKEN_USER = 1

    def __init__(self) -> None:
        import ctypes
        from ctypes import wintypes

        self._ctypes = ctypes
        self._wintypes = wintypes
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        adv = ctypes.WinDLL("advapi32", use_last_error=True)
        k32.GetNamedPipeServerProcessId.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.ULONG)]
        k32.GetNamedPipeServerProcessId.restype = wintypes.BOOL
        k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        k32.OpenProcess.restype = wintypes.HANDLE
        k32.GetCurrentProcess.restype = wintypes.HANDLE
        k32.CloseHandle.argtypes = [wintypes.HANDLE]
        k32.LocalFree.argtypes = [wintypes.HLOCAL]
        adv.OpenProcessToken.argtypes = [
            wintypes.HANDLE,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.HANDLE),
        ]
        adv.OpenProcessToken.restype = wintypes.BOOL
        adv.GetTokenInformation.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
        ]
        adv.GetTokenInformation.restype = wintypes.BOOL
        adv.ConvertSidToStringSidW.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.LPWSTR)]
        adv.ConvertSidToStringSidW.restype = wintypes.BOOL
        self._k32, self._adv = k32, adv

    def server_pid(self, handle: int) -> int | None:
        pid = self._wintypes.ULONG()
        ok = self._k32.GetNamedPipeServerProcessId(handle, self._ctypes.byref(pid))
        return int(pid.value) if ok else None

    def _token_user_sid(self, process: Any) -> str | None:
        ctypes, wintypes = self._ctypes, self._wintypes
        token = wintypes.HANDLE()
        if not self._adv.OpenProcessToken(process, self._TOKEN_QUERY, ctypes.byref(token)):
            return None
        try:
            size = wintypes.DWORD()
            self._adv.GetTokenInformation(token, self._TOKEN_USER, None, 0, ctypes.byref(size))
            if not size.value:
                return None
            buf = ctypes.create_string_buffer(size.value)
            if not self._adv.GetTokenInformation(
                token, self._TOKEN_USER, buf, size, ctypes.byref(size)
            ):
                return None
            # TOKEN_USER { SID_AND_ATTRIBUTES User { PSID Sid; DWORD Attributes; } }
            psid = ctypes.cast(buf, ctypes.POINTER(ctypes.c_void_p))[0]
            text = wintypes.LPWSTR()
            if not self._adv.ConvertSidToStringSidW(psid, ctypes.byref(text)):
                return None
            try:
                return text.value
            finally:
                self._k32.LocalFree(text)
        finally:
            self._k32.CloseHandle(token)

    def process_user_sid(self, pid: int) -> str | None:
        process = self._k32.OpenProcess(self._PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not process:
            return None
        try:
            return self._token_user_sid(process)
        finally:
            self._k32.CloseHandle(process)

    def current_user_sid(self) -> str | None:
        return self._token_user_sid(self._k32.GetCurrentProcess())


def windows_peer_is_current_user(
    handle: int, *, api: WindowsSecurityApi | None = None
) -> bool | None:
    """Named pipe sunucusunu çalıştıran süreç bu kullanıcıya mı ait? None: doğrulanamadı
    (ör. başka kullanıcının sürecine erişim reddedildi)."""
    api = _CtypesWindowsSecurityApi() if api is None else api
    pid = api.server_pid(handle)
    if pid is None:
        return None
    theirs, mine = api.process_user_sid(pid), api.current_user_sid()
    if theirs is None or mine is None:
        return None
    return theirs == mine


def default_peer_verifier(descriptor: int, name: str) -> bool | None:
    """Platforma göre sunucu doğrulaması (bkz. modül belgesi)."""
    if sys.platform == "win32":
        return windows_peer_is_current_user(descriptor)
    return unix_peer_is_current_user(descriptor, name)


_SEND_OK, _SEND_FAILED, _SEND_UNTRUSTED = "ok", "failed", "untrusted"


def _verify_peer(verifier: PeerVerifier, sock: QLocalSocket, name: str) -> bool:
    try:
        trusted = verifier(int(sock.socketDescriptor()), name)
    except Exception:
        log.exception("IPC sunucusu doğrulanırken hata; güvenilmez sayılıyor")
        trusted = None
    if trusted is True:
        return True
    if trusted is None:
        log.warning("IPC sunucusunun sahibi doğrulanamadı; bağlanılmıyor: %s", name)
    else:
        log.warning("IPC sunucusu başka bir kullanıcıya ait; bağlanılmıyor: %s", name)
    return False


def _send(name: str, message: bytes, timeout_ms: int, verifier: PeerVerifier) -> str:
    sock = QLocalSocket()
    loop = QEventLoop()
    result = {"status": _SEND_FAILED, "done": False}

    def finish(status: str) -> None:
        if result["done"]:
            return
        result["status"], result["done"] = status, True
        loop.quit()

    def on_connected() -> None:
        if not _verify_peer(verifier, sock, name):
            finish(_SEND_UNTRUSTED)
            return
        sock.write(message)
        sock.flush()

    def on_ready_read() -> None:
        ok = bytes(sock.readAll().data()).startswith(ACK)
        finish(_SEND_OK if ok else _SEND_FAILED)

    sock.connected.connect(on_connected)
    sock.readyRead.connect(on_ready_read)
    sock.errorOccurred.connect(lambda _err: finish(_SEND_FAILED))
    sock.disconnected.connect(lambda: finish(_SEND_FAILED))

    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(lambda: finish(_SEND_FAILED))
    timer.start(timeout_ms)

    sock.connectToServer(name)
    if not result["done"]:
        loop.exec()
    timer.stop()
    sock.abort()
    return str(result["status"])


def send_command(
    name: str,
    message: bytes,
    timeout_ms: int = _TIMEOUT_MS,
    *,
    peer_verifier: PeerVerifier = default_peer_verifier,
) -> bool:
    """Çalışan örneğe komut yollar ve okunduğuna dair onay bekler.

    Windows'ta named pipe, yazan taraf kapattığında okunmamış veriyi düşürebilir;
    bu yüzden gönderim ancak sunucu ACK yolladığında başarılı sayılır. Bekleme
    iç içe bir olay döngüsüyle yapılır, böylece sunucu aynı süreçte olsa bile
    (testler) ilerleyebilir. Sunucu bu kullanıcıya ait olduğu doğrulanamazsa hiçbir
    şey yazılmaz ve False döner.
    """
    return _send(name, message, timeout_ms, peer_verifier) == _SEND_OK


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

    def __init__(
        self,
        name: str = DEFAULT_NAME,
        parent=None,
        *,
        peer_verifier: PeerVerifier = default_peer_verifier,
    ):
        super().__init__(parent)
        self._name = name
        self._server: QLocalServer | None = None
        self._peer_verifier = peer_verifier
        self._status = IpcStatus.NOT_STARTED

    @property
    def name(self) -> str:
        return self._name

    @property
    def status(self) -> IpcStatus:
        """Son `try_acquire` çağrısının sonucu."""
        return self._status

    @property
    def warning_message(self) -> str | None:
        """Uygulama IPC'siz çalışıyorsa kullanıcıya gösterilecek Türkçe uyarı; yoksa None."""
        return _STATUS_MESSAGES.get(self._status)

    def try_acquire(self) -> bool:
        """Bu süreç tek örnek olacaksa True (sunucu dinlemeye başlar); False = başka örnek var.

        Çalışan örneğe önce "show" gönderilir (öne gelsin diye). Sunucu canlı ama yanıtsızsa
        da False döner. Ad doğrulanamayan (başka kullanıcıya ait olabilecek) bir sunucudaysa
        ya da dinleme başlatılamazsa uygulama IPC'siz sürer: True döner, `status` /
        `warning_message` kullanıcıya gösterilecek uyarıyı verir."""
        sent = _send(self._name, SHOW_MESSAGE, _TIMEOUT_MS, self._peer_verifier)
        if sent == _SEND_OK:
            self._status = IpcStatus.ALREADY_RUNNING
            return False
        if sent == _SEND_UNTRUSTED:
            # Ad başkasının elinde: "zaten çalışıyor" deyip çıkmak (eski davranış) ona
            # Dikte'yi kapatma gücü verirdi; soketini silmek de onun işi değil.
            self._status = IpcStatus.UNTRUSTED
            return True
        if _server_socket_exists(self._name):
            # Sunucu canlı (bağlantı kabul edildi) ama SHOW isteğine zamanında ACK
            # dönmedi — örn. GUI iş parçacığı meşgul. Soketi silip ikinci bir örnek
            # başlatmak yerine yalnızca başlatmayı reddet.
            log.warning("çalışan örnek meşgul görünüyor, ikinci başlatma reddedildi")
            self._status = IpcStatus.BUSY
            return False
        QLocalServer.removeServer(self._name)  # çökmüş önceki örnekten kalan soket
        self._server = QLocalServer(self)
        # Yalnızca aynı kullanıcı bağlanabilsin (Unix: soket 0700; Windows: pipe DACL'i).
        self._server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        self._server.newConnection.connect(self._on_connection)
        if not self._server.listen(self._name):
            log.error("QLocalServer dinleyemedi: %s", self._server.errorString())
            self._status = IpcStatus.UNAVAILABLE
            return True  # kilit kurulamasa da çalışmaya devam et (uyarı: warning_message)
        self._status = IpcStatus.LISTENING
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
