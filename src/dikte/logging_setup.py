"""Dönen dosya günlüğü (`dikte.log`) ve yakalanmamış istisnaların günlüğe yazılması."""

import logging
import logging.handlers
import sys
import threading

from dikte import paths

log = logging.getLogger(__name__)

# Hata ayıklamada bile ayrıntısı işe yaramayan, günlüğü dolduran kütüphaneler.
_NOISY = ("httpcore", "httpx", "urllib3", "huggingface_hub", "filelock", "PIL", "asyncio")


def _log_qt_message(mode, context, message: str) -> None:
    """Qt'nin kendi uyarılarını (stil, OpenGL, ekran…) günlüğe yönlendirir."""
    from PySide6.QtCore import QtMsgType

    level = {
        QtMsgType.QtDebugMsg: logging.DEBUG,
        QtMsgType.QtInfoMsg: logging.INFO,
        QtMsgType.QtWarningMsg: logging.WARNING,
    }.get(mode, logging.ERROR)
    logging.getLogger("qt").log(level, "%s (%s:%s)", message, context.file, context.line)


def set_debug(enabled: bool) -> None:
    """Hata ayıklama günlüğü: açıkken her şey (DEBUG) ve Qt'nin kendi uyarıları da yazılır;
    kapalıyken INFO. Gürültülü kütüphaneler hep INFO'da tutulur. Çalışırken değiştirilebilir."""
    logging.getLogger().setLevel(logging.DEBUG if enabled else logging.INFO)
    for name in _NOISY:
        logging.getLogger(name).setLevel(logging.INFO)
    log.info("hata ayıklama günlüğü %s", "açık" if enabled else "kapalı")


def _log_uncaught(exc_type, exc_value, exc_tb) -> None:
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_tb)
        return
    log.critical("yakalanmamış istisna", exc_info=(exc_type, exc_value, exc_tb))


def _log_uncaught_thread(args) -> None:
    log.critical(
        "yakalanmamış istisna (iş parçacığı: %s)",
        args.thread.name if args.thread else "?",
        exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
    )


def setup_logging(level: str = "INFO") -> None:
    """Kök günlükçüye dönen dosya (2 MB × 3) ve varsa stderr işleyicisi ekler.

    İşleyiciler yalnızca kökte hiç yoksa eklenir (tekrar çağrı çoğaltmaz); yakalanmamış
    istisnalar için `sys.excepthook` ve `threading.excepthook` her çağrıda kurulur."""
    fmt = "%(asctime)s %(levelname)s %(name)s: %(message)s"
    root = logging.getLogger()
    root.setLevel(level)
    if not root.handlers:
        fh = logging.handlers.RotatingFileHandler(
            paths.log_path(), maxBytes=2_000_000, backupCount=3, encoding="utf-8"
        )
        fh.setFormatter(logging.Formatter(fmt))
        root.addHandler(fh)
        if sys.stderr:
            sh = logging.StreamHandler(sys.stderr)
            sh.setFormatter(logging.Formatter(fmt))
            root.addHandler(sh)
    # Paketlenmiş derlemede console=False: yakalanmamış bir istisna hiçbir iz bırakmadan
    # kaybolurdu (görünür konsol yok). Ana iş parçacığı ve worker iş parçacıkları (Qt
    # slot'ları hariç — onlar zaten kendi try/except'leriyle sarılı) için loglanır.
    sys.excepthook = _log_uncaught
    threading.excepthook = _log_uncaught_thread
    from PySide6.QtCore import qInstallMessageHandler

    qInstallMessageHandler(_log_qt_message)
