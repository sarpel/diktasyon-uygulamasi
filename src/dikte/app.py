from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass

from PySide6.QtCore import QCoreApplication, QThreadPool
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox, QSystemTrayIcon

from dikte import APP_NAME, __version__, paths
from dikte.audio.recorder import AudioRecorder
from dikte.config import Settings, load_settings, save_settings
from dikte.core.controller import DictationController
from dikte.core.history import History
from dikte.core.state import DictationState
from dikte.llm import LlmError, make_provider
from dikte.logging_setup import setup_logging
from dikte.platform.autostart import set_autostart
from dikte.platform.hotkey import GlobalHotkey
from dikte.platform.hotkey_parse import parse_hotkey
from dikte.platform.single_instance import (
    DEFAULT_NAME,
    TOGGLE_MESSAGE,
    SingleInstance,
    send_command,
)
from dikte.stt.engine import FasterWhisperEngine
from dikte.ui.overlay import RecordingOverlay
from dikte.ui.result_window import ResultWindow
from dikte.ui.settings_dialog import SettingsDialog, list_input_devices
from dikte.ui.tray import TrayIcon

log = logging.getLogger(__name__)
# Windows dışında global kısayol yoktur; masaüstü ortamı bu komuta bir tuş bağlar.
CLI_TOGGLE_HINT = "dikte --toggle"


@dataclass
class AppContext:
    settings: Settings
    controller: DictationController
    tray: TrayIcon
    overlay: RecordingOverlay
    window: ResultWindow
    hotkey: GlobalHotkey
    history: History


class _NullLlm:
    name = "none"

    def complete(self, *a, **k):
        raise LlmError("LLM sağlayıcı yapılandırılamadı; Ayarlar'dan kontrol edin")


def _make_llm(settings: Settings):
    try:
        return make_provider(settings.llm)
    except LlmError as exc:
        log.error("LLM sağlayıcı oluşturulamadı: %s", exc)
        return _NullLlm()


def build_app(settings: Settings) -> AppContext:
    recorder = AudioRecorder(settings.audio)
    stt = FasterWhisperEngine(settings.stt)
    controller = DictationController(
        settings,
        recorder=recorder,
        stt=stt,
        llm=_make_llm(settings),
        pool=QThreadPool.globalInstance(),
    )
    hotkey = GlobalHotkey()
    tray = TrayIcon(parse_hotkey(settings.hotkey).label)
    overlay = RecordingOverlay()
    window = ResultWindow()
    history = History(paths.history_path(), settings.history_limit)
    ctx = AppContext(settings, controller, tray, overlay, window, hotkey, history)
    _wire(ctx)
    return ctx


def _wire(ctx: AppContext) -> None:
    c = ctx.controller
    ctx.window.bind(c, close_after_copy=ctx.settings.close_after_copy)
    c.state_changed.connect(ctx.overlay.on_state)
    c.buckets_changed.connect(ctx.overlay.on_buckets)
    c.state_changed.connect(ctx.tray.set_state)
    c.ready_changed.connect(ctx.tray.set_ready)
    c.error.connect(lambda m: ctx.tray.notify(APP_NAME, m, critical=True))
    c.state_changed.connect(lambda s: s is DictationState.RESULT and ctx.history.append(c.session))
    ctx.hotkey.activated.connect(c.toggle)
    ctx.tray.toggle_requested.connect(c.toggle)
    ctx.tray.show_requested.connect(
        lambda: (ctx.window.showNormal(), ctx.window.raise_(), ctx.window.activateWindow())
    )
    ctx.tray.settings_requested.connect(lambda: _open_settings(ctx))
    ctx.tray.quit_requested.connect(lambda: _quit(ctx))


def _apply_hotkey(ctx: AppContext) -> None:
    if ctx.hotkey.register(ctx.settings.hotkey):
        ctx.tray.set_hotkey_label(ctx.hotkey.label or ctx.settings.hotkey)
        return
    if sys.platform == "win32":
        ctx.tray.notify(
            APP_NAME,
            f"Kısayol kaydedilemedi: {ctx.settings.hotkey}. "
            "Başka bir uygulama kullanıyor olabilir.",
            critical=True,
        )
        ctx.tray.set_hotkey_label(ctx.settings.hotkey)
        return
    log.info("global kısayol bu platformda yok; '%s' komutuna tuş bağlayın", CLI_TOGGLE_HINT)
    ctx.tray.set_hotkey_label(CLI_TOGGLE_HINT)


def _run_toggle() -> int:
    """Çalışan örneğe kayıt başlat/durdur komutu gönderir."""
    _app = QCoreApplication.instance() or QCoreApplication(sys.argv)
    if not send_command(DEFAULT_NAME, TOGGLE_MESSAGE):
        print(f"{APP_NAME} çalışmıyor; önce uygulamayı başlatın.", file=sys.stderr)
        return 1
    return 0


def _open_settings(ctx: AppContext) -> None:
    dlg = SettingsDialog(ctx.settings, list_input_devices(), ctx.window)
    if dlg.exec() != QDialog.DialogCode.Accepted:
        return
    new = dlg.result_settings()
    save_settings(new)
    needs_restart = (
        new.stt != ctx.settings.stt
        or new.audio != ctx.settings.audio
        or new.llm != ctx.settings.llm
    )
    ctx.settings = new
    set_autostart(new.autostart)
    ctx.controller.update_settings(new)
    ctx.window.close_after_copy = new.close_after_copy
    _apply_hotkey(ctx)
    if needs_restart:
        QMessageBox.information(
            ctx.window,
            APP_NAME,
            "Model / ses / LLM ayarları uygulamayı yeniden başlatınca etkin olur.",
        )


def _quit(ctx: AppContext) -> None:
    ctx.hotkey.unregister()
    ctx.tray.hide()
    QApplication.instance().quit()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="dikte")
    parser.add_argument("--minimized", action="store_true", help="pencere açmadan tray'de başla")
    parser.add_argument(
        "--toggle",
        action="store_true",
        help="çalışan örnekte kaydı başlat/durdur (Linux kısayolu için)",
    )
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {__version__}")
    args = parser.parse_args(argv)
    if args.toggle:
        return _run_toggle()

    setup_logging()
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setQuitOnLastWindowClosed(False)

    single = SingleInstance()
    if not single.try_acquire():
        log.info("zaten çalışıyor, mevcut örneğe sinyal gönderildi")
        return 0
    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.critical(None, APP_NAME, "Sistem tepsisi bulunamadı.")
        return 1

    settings = load_settings()
    ctx = build_app(settings)
    single.activated.connect(ctx.tray.show_requested)
    single.toggle_requested.connect(ctx.controller.toggle)
    ctx.tray.show()
    _apply_hotkey(ctx)
    set_autostart(settings.autostart)
    ctx.controller.warm_up()
    if not args.minimized:
        ctx.window.show()
    log.info("%s %s başladı", APP_NAME, __version__)
    return app.exec()
