from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QThreadPool, QTimer
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox, QSystemTrayIcon

from dikte import APP_NAME, __version__, paths
from dikte.audio.recorder import AudioRecorder
from dikte.config import AppProfile, DictionaryEntry, Settings, load_settings, save_settings
from dikte.core.controller import DictationController
from dikte.core.health import (
    HealthItem,
    check_health,
    default_cuda_probe,
    default_llm_probe,
    default_model_probe,
)
from dikte.core.history import History, HistoryError
from dikte.core.history_export import to_markdown, to_text
from dikte.core.state import BUSY_STATES, MODES, DictationState
from dikte.llm import LlmError, make_provider
from dikte.logging_setup import setup_logging
from dikte.platform.autostart import set_autostart
from dikte.platform.foreground import foreground_process_name
from dikte.platform.gpu_info import LOW_VRAM_MB, query_vram
from dikte.platform.hold_detect import HoldDetector
from dikte.platform.hotkey import HOTKEY_ID, GlobalHotkey
from dikte.platform.hotkey_parse import HotkeyParseError, parse_hotkey
from dikte.platform.paste import foreground_window_id, paste_active_window, type_unicode_text
from dikte.platform.single_instance import (
    DEFAULT_NAME,
    START_MESSAGE,
    STOP_MESSAGE,
    TOGGLE_MESSAGE,
    SingleInstance,
    send_command,
)
from dikte.stt.download import download_model
from dikte.stt.engine import FasterWhisperEngine
from dikte.text.profiles import match_profile
from dikte.ui.health_dialog import HealthDialog
from dikte.ui.overlay import RecordingOverlay
from dikte.ui.result_window import ResultWindow
from dikte.ui.settings_dialog import SettingsDialog, list_input_devices
from dikte.ui.sounds import SoundPlayer
from dikte.ui.tray import TrayIcon

log = logging.getLogger(__name__)
# Windows dışında global kısayol yoktur; masaüstü ortamı bu komuta bir tuş bağlar.
CLI_TOGGLE_HINT = "dikte --toggle"
# Yapıştırma işletim sisteminde işlenip aktif pencereye ulaşana kadarki bekleme süresi.
RESTORE_CLIPBOARD_DELAY_MS = 300


@dataclass
class AppContext:
    settings: Settings
    controller: DictationController
    tray: TrayIcon
    overlay: RecordingOverlay
    window: ResultWindow
    hotkey: GlobalHotkey
    cancel_hotkey: GlobalHotkey
    hotkey_translate: GlobalHotkey
    hotkey_prompt: GlobalHotkey
    history: History
    stt: FasterWhisperEngine
    recorder: AudioRecorder
    sounds: SoundPlayer
    hold: HoldDetector
    hold_mode: str = "correct"  # hold'un hangi kısayol için silahlandığını taşır
    health_dialog: HealthDialog | None = None  # ilk çalıştırmada/STT hatasında gösterilir
    active_profile: AppProfile | None = None  # son kısayolda ön plandaki uygulamayla eşleşen profil


class _NullLlm:
    name = "none"

    def complete(self, *a, **k):
        raise LlmError("LLM sağlayıcı yapılandırılamadı; Ayarlar'dan kontrol edin")


def _make_llm(settings: Settings):
    if not settings.llm.enabled:
        log.info("LLM düzeltmesi kapalı; sağlayıcı oluşturulmadı")
        return _NullLlm()
    try:
        return make_provider(settings.llm)
    except LlmError as exc:
        log.error("LLM sağlayıcı oluşturulamadı: %s", exc)
        return _NullLlm()


def _safe_hotkey(settings: Settings) -> Settings:
    """config.json'daki kısayol(lar) bozuksa açılışta çökmek yerine varsayılana/kapalıya döner."""
    try:
        parse_hotkey(settings.hotkey)
    except HotkeyParseError as exc:
        fallback = Settings().hotkey
        log.error(
            "config'teki kısayol geçersiz (%s): %s; '%s' kullanılıyor",
            settings.hotkey,
            exc,
            fallback,
        )
        settings = settings.model_copy(update={"hotkey": fallback})
    for field_name in ("hotkey_translate", "hotkey_prompt"):
        spec = getattr(settings, field_name)
        if not spec:
            continue
        try:
            parse_hotkey(spec)
        except HotkeyParseError as exc:
            log.error("config'teki %s geçersiz (%s): %s; kapatılıyor", field_name, spec, exc)
            settings = settings.model_copy(update={field_name: ""})
    return settings


def build_app(settings: Settings) -> AppContext:
    settings = _safe_hotkey(settings)
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
    cancel_hotkey = GlobalHotkey(hotkey_id=HOTKEY_ID + 1)  # iptal için ikinci kayıt
    hotkey_translate = GlobalHotkey(hotkey_id=HOTKEY_ID + 2)
    hotkey_prompt = GlobalHotkey(hotkey_id=HOTKEY_ID + 3)
    tray = TrayIcon(parse_hotkey(settings.hotkey).label)
    overlay = RecordingOverlay()
    window = ResultWindow()
    history = History(paths.history_path(), settings.history_limit)
    sounds = SoundPlayer(settings.sounds_enabled)
    hold = HoldDetector()
    ctx = AppContext(
        settings,
        controller,
        tray,
        overlay,
        window,
        hotkey,
        cancel_hotkey,
        hotkey_translate,
        hotkey_prompt,
        history,
        stt,
        recorder,
        sounds,
        hold,
    )
    _wire(ctx)
    return ctx


def _wire(ctx: AppContext) -> None:
    c = ctx.controller
    ctx.window.bind(
        c,
        close_after_copy=ctx.settings.close_after_copy,
        raise_on_result=ctx.settings.raise_window_on_result,
    )
    c.state_changed.connect(ctx.overlay.on_state)
    c.buckets_changed.connect(ctx.overlay.on_buckets)
    c.partial_text.connect(ctx.overlay.show_partial)
    c.state_changed.connect(ctx.tray.set_state)
    c.ready_changed.connect(ctx.tray.set_ready)
    c.ready_changed.connect(lambda ready: _warn_if_downgraded(ctx) if ready else None)
    c.error.connect(lambda m: ctx.tray.notify(APP_NAME, m, critical=True))
    c.error.connect(lambda m: _maybe_show_health_dialog_on_error(ctx, m))
    c.state_changed.connect(ctx.sounds.on_state)
    c.error.connect(ctx.sounds.on_error)
    c.error.connect(ctx.overlay.show_error)
    c.state_changed.connect(lambda s: s is DictationState.RESULT and _store_session(ctx))
    ctx.hotkey.activated.connect(lambda: _on_hotkey(ctx))
    ctx.hotkey_translate.activated.connect(lambda: _on_hotkey(ctx, "translate"))
    ctx.hotkey_prompt.activated.connect(lambda: _on_hotkey(ctx, "prompt"))
    ctx.hold.tapped.connect(lambda: c.toggle(ctx.hold_mode, profile=ctx.active_profile))
    ctx.hold.held.connect(lambda: c.start_recording(ctx.hold_mode, profile=ctx.active_profile))
    ctx.hold.released.connect(c.stop_recording)
    ctx.tray.toggle_requested.connect(c.toggle)
    ctx.tray.show_requested.connect(lambda: _show_window(ctx))
    ctx.tray.settings_requested.connect(lambda: _open_settings(ctx))
    ctx.tray.quit_requested.connect(lambda: _quit(ctx))
    c.cancelled.connect(lambda: ctx.tray.notify(APP_NAME, "İptal edildi"))
    ctx.overlay.cancel_requested.connect(c.cancel)
    ctx.tray.cancel_requested.connect(c.cancel)
    ctx.cancel_hotkey.activated.connect(c.cancel)
    c.state_changed.connect(lambda s: _sync_cancel_hotkey(ctx, s))
    c.result_ready.connect(lambda text: _on_result_ready(ctx, text))
    ctx.window.history_panel.delete_requested.connect(lambda sid: _delete_session(ctx, sid))
    ctx.window.history_panel.clear_requested.connect(lambda: _clear_history(ctx))
    ctx.window.history_panel.export_requested.connect(lambda path: _export_history(ctx, path))
    ctx.tray.copy_requested.connect(lambda text: QApplication.clipboard().setText(text))
    ctx.window.record_requested.connect(c.toggle)
    ctx.window.cancel_requested.connect(c.cancel)
    ctx.window.settings_requested.connect(lambda: _open_settings(ctx))
    ctx.window.file_requested.connect(c.transcribe_file)
    ctx.window.text_edited.connect(c.apply_edit)
    ctx.window.dictionary_add_requested.connect(
        lambda wrong, term: _add_dictionary_entry(ctx, wrong, term)
    )
    ctx.window.repaste_requested.connect(lambda text: _repaste(ctx, text))
    c.session_updated.connect(lambda s: _sync_history_on_edit(ctx, s))
    c.edit_learned.connect(lambda changes: _suggest(ctx, changes))
    c.ready_changed.connect(lambda ready: ready and _refresh_status_info(ctx))
    _refresh_history(ctx)


def _show_window(ctx: AppContext) -> None:
    ctx.window.showNormal()
    ctx.window.raise_()
    ctx.window.activateWindow()


def _guard_history(ctx: AppContext, action: Callable[[], None]) -> None:
    """Geçmiş yazılamazsa dikte akışı sürer; kullanıcı ne yapacağını bildiren bir uyarı alır."""
    try:
        action()
    except HistoryError as exc:
        log.error("geçmiş işlemi başarısız: %s", exc)
        ctx.tray.notify(APP_NAME, str(exc), critical=True)


def _store_session(ctx: AppContext) -> None:
    _guard_history(ctx, lambda: ctx.history.append(ctx.controller.session))
    _refresh_history(ctx)


def _refresh_history(ctx: AppContext) -> None:
    sessions = ctx.history.load()
    ctx.window.history_panel.set_sessions(sessions)
    ctx.tray.set_recent(sessions)


def _delete_session(ctx: AppContext, session_id: str) -> None:
    _guard_history(ctx, lambda: ctx.history.delete(session_id))
    _refresh_history(ctx)


def _clear_history(ctx: AppContext) -> None:
    _guard_history(ctx, ctx.history.clear)
    _refresh_history(ctx)


def _export_history(ctx: AppContext, path: str) -> None:
    """Geçmişi dosyaya yazar; uzantı `.md` ise Markdown, aksi hâlde düz metin kullanılır."""
    sessions = ctx.history.load()
    content = to_markdown(sessions) if path.lower().endswith(".md") else to_text(sessions)
    try:
        Path(path).write_text(content, encoding="utf-8")
    except OSError as exc:
        log.error("geçmiş dışa aktarılamadı: %s", exc)
        ctx.tray.notify(APP_NAME, f"Geçmiş dışa aktarılamadı: {exc}", critical=True)


def _sync_history_on_edit(ctx: AppContext, session) -> None:
    """Sonuç ekranındayken (elle düzenleme, çeviri vb.) oturum değişirse geçmiş güncellenir."""
    if ctx.controller.state is not DictationState.RESULT:
        return
    _guard_history(ctx, lambda: ctx.history.update(session))
    _refresh_history(ctx)


def _suggest(ctx: AppContext, changes) -> None:
    """Elle düzenlemeden çıkan tek kelimelik değişiklikler için sözlük önerisi gösterir."""
    if not ctx.settings.suggest_dictionary:
        return
    for change in changes:
        if change.reason != "değiştirildi":
            continue
        if " " in change.original or " " in change.replacement:
            continue
        ctx.window.show_suggestion(change.original, change.replacement)
        return


def _add_dictionary_entry(ctx: AppContext, wrong: str, term: str) -> None:
    entries = (*ctx.settings.dictionary.entries, DictionaryEntry(term=term, wrong=(wrong,)))
    new_dictionary = ctx.settings.dictionary.model_copy(update={"entries": entries})
    new_settings = ctx.settings.model_copy(update={"dictionary": new_dictionary})
    save_settings(new_settings)
    ctx.settings = new_settings
    ctx.controller.update_settings(new_settings)


def _repaste(ctx: AppContext, text: str) -> None:
    ctx.window.hide()
    QTimer.singleShot(200, lambda: _on_result_ready(ctx, text))


def _refresh_status_info(ctx: AppContext) -> None:
    llm = ctx.settings.llm.active_model if ctx.settings.llm.enabled else "kapalı"
    ctx.window.set_status_info(ctx.stt.active_model, ctx.stt.compute_type, llm)
    _warn_if_low_vram(ctx)


def _warn_if_low_vram(ctx: AppContext) -> None:
    info = query_vram()
    if info is None:
        return
    free_mb = info.total_mb - info.used_mb
    if free_mb < LOW_VRAM_MB:
        free_gb = free_mb / 1024
        ctx.window.statusBar().showMessage(
            f"Boş VRAM düşük ({free_gb:.1f} GB): LLM'i kapatmayı veya keep_alive=0 yapmayı düşünün",
            15000,
        )


def _on_result_ready(ctx: AppContext, text: str) -> None:
    """Sonucu panoya yazar ve (ayar açıksa) ön plandaki uygulamaya yapıştırır.

    `restore_clipboard` açıksa ve yapıştırma gerçekten gönderildiyse, panodaki eski
    metin kısa bir gecikmeyle geri yazılır (yapıştırma hedef uygulamaya ulaşsın diye).
    """
    if not text or not ctx.settings.auto_copy:
        return
    profile = ctx.active_profile
    if profile and profile.trailing:
        text += profile.trailing
    clipboard = QApplication.clipboard()
    previous = clipboard.text() if ctx.settings.restore_clipboard else ""
    clipboard.setText(text)
    if ctx.controller.session.source_path:
        return  # dosyadan çözümlenen sonuç yalnızca panoya kopyalanır, yapıştırılmaz
    if not ctx.settings.auto_paste or ctx.window.isActiveWindow():
        return
    own_ids = {int(ctx.window.winId()), int(ctx.overlay.winId())}
    foreground = foreground_window_id()
    if foreground is not None and foreground in own_ids:
        return
    if profile and profile.paste == "type":
        pasted = type_unicode_text(text)
    else:
        combo = profile.paste if profile else "ctrl+v"
        pasted = paste_active_window(own_ids, combo=combo)
    if not pasted:
        log.info("yapıştırma atlandı; metin panoda")
        return
    if ctx.settings.restore_clipboard and previous:
        QTimer.singleShot(RESTORE_CLIPBOARD_DELAY_MS, lambda: clipboard.setText(previous))


def _sync_cancel_hotkey(ctx: AppContext, state: DictationState) -> None:
    """İptal için global Esc yalnızca iş sürerken kayıtlı kalır; boştayken serbest bırakılır."""
    if state in BUSY_STATES:
        if not ctx.cancel_hotkey.register("escape", allow_bare=True):
            log.info("global Esc kaydedilemedi; pencere, overlay veya tepsiden iptal edilebilir")
    else:
        ctx.cancel_hotkey.unregister()


def _maybe_show_health_dialog_on_error(ctx: AppContext, message: str) -> None:
    normalized = message.casefold()
    if "model" in normalized and "yüklenemedi" in normalized:
        _show_health_dialog(ctx)


def _show_health_dialog(ctx: AppContext, items: tuple[HealthItem, ...] | None = None) -> None:
    if items is None:
        items = check_health(
            ctx.settings,
            cuda_probe=default_cuda_probe,
            model_probe=default_model_probe,
            llm_probe=default_llm_probe,
        )
    ctx.health_dialog = HealthDialog(
        items,
        on_download=lambda progress: _download_model_for_ctx(ctx, progress),
        parent=ctx.window,
    )
    ctx.health_dialog.setModal(False)
    ctx.health_dialog.show()


def _download_model_for_ctx(ctx: AppContext, progress: Callable[[int, int], None]) -> None:
    download_model(ctx.settings.stt.model, paths.models_dir(), progress)


def _warn_if_downgraded(ctx: AppContext) -> None:
    if not ctx.stt.is_downgraded:
        return
    ctx.tray.notify(
        APP_NAME,
        f"GPU '{ctx.settings.stt.compute_type}' hassasiyetini desteklemiyor; "
        f"'{ctx.stt.compute_type}' kullanılıyor. Daha yavaş çalışabilir.",
    )


def _hotkey_spec(ctx: AppContext, mode: str) -> str:
    return {
        "correct": ctx.settings.hotkey,
        "translate": ctx.settings.hotkey_translate,
        "prompt": ctx.settings.hotkey_prompt,
    }[mode]


def _on_hotkey(ctx: AppContext, mode: str = "correct") -> None:
    """Kısayola basılınca çağrılır: bas-konuş yalnızca Windows'ta anlamlıdır."""
    # Profil tanımlı değilse ön plan sürecini hiç sorgulama (win32 API'sini gereksiz çağırmaz).
    exe = foreground_process_name() if ctx.settings.profiles else ""
    ctx.active_profile = match_profile(ctx.settings.profiles, exe)
    if not ctx.settings.push_to_talk or sys.platform != "win32":
        ctx.controller.toggle(mode, profile=ctx.active_profile)
        return
    ctx.hold_mode = mode
    ctx.hold.arm(parse_hotkey(_hotkey_spec(ctx, mode)).vk)


def _mode_hotkeys(ctx: AppContext) -> tuple[tuple[GlobalHotkey, str, str], ...]:
    return (
        (ctx.hotkey_translate, ctx.settings.hotkey_translate, "translate"),
        (ctx.hotkey_prompt, ctx.settings.hotkey_prompt, "prompt"),
    )


def _apply_hotkey(ctx: AppContext) -> None:
    if ctx.hotkey.register(ctx.settings.hotkey):
        ctx.tray.set_hotkey_label(ctx.hotkey.label or ctx.settings.hotkey)
    elif sys.platform == "win32":
        ctx.tray.notify(
            APP_NAME,
            f"Kısayol kaydedilemedi: {ctx.settings.hotkey}. "
            "Başka bir uygulama kullanıyor olabilir.",
            critical=True,
        )
        ctx.tray.set_hotkey_label(ctx.settings.hotkey)
    else:
        log.info("global kısayol bu platformda yok; '%s' komutuna tuş bağlayın", CLI_TOGGLE_HINT)
        ctx.tray.set_hotkey_label(CLI_TOGGLE_HINT)
    _apply_mode_hotkeys(ctx)


def _apply_mode_hotkeys(ctx: AppContext) -> None:
    """Çeviri/prompt kısayolları isteğe bağlıdır; boşsa kapalı kalır, kaydedilemezse
    yalnızca günlüğe düşer (ana kısayol gibi kritik değildir, tepsiyi meşgul etmez)."""
    mode_labels = {"translate": "", "prompt": ""}
    for hk, spec, name in _mode_hotkeys(ctx):
        hk.unregister()
        if not spec or sys.platform != "win32":
            continue
        if hk.register(spec):
            mode_labels[name] = hk.label
        else:
            log.warning("%s kısayolu kaydedilemedi: %s", name, spec)
    ctx.tray.set_mode_labels(mode_labels["translate"], mode_labels["prompt"])


def _run_command(message: bytes) -> int:
    """Çalışan örneğe verilen komutu gönderir (Linux'ta bas-konuş simülasyonu için)."""
    _app = QCoreApplication.instance() or QCoreApplication(sys.argv)
    if not send_command(DEFAULT_NAME, message):
        print(f"{APP_NAME} çalışmıyor; önce uygulamayı başlatın.", file=sys.stderr)
        return 1
    return 0


def _with_mode(base: bytes, mode: str) -> bytes:
    return base if mode == "correct" else base + b":" + mode.encode("ascii")


def _run_toggle(mode: str = "correct") -> int:
    """Çalışan örneğe kayıt başlat/durdur komutu gönderir."""
    return _run_command(_with_mode(TOGGLE_MESSAGE, mode))


def _open_settings(ctx: AppContext) -> None:
    dlg = SettingsDialog(ctx.settings, list_input_devices(), ctx.window)
    if dlg.exec() != QDialog.DialogCode.Accepted:
        return
    new = dlg.result_settings()
    save_settings(new)
    needs_reload = ctx.stt.update_settings(new.stt)
    ctx.recorder.update_settings(new.audio)
    llm_changed = new.llm != ctx.settings.llm
    ctx.settings = new
    set_autostart(new.autostart)
    ctx.controller.update_settings(new)
    if llm_changed:  # sağlayıcı yeniden kurulur, yeniden başlatma gerekmez
        ctx.controller.set_llm(_make_llm(new))
        ctx.controller.prewarm_llm()
    ctx.window.set_llm_enabled(new.llm.enabled)
    ctx.window.close_after_copy = new.close_after_copy
    ctx.window.raise_on_result = new.raise_window_on_result
    ctx.sounds.set_enabled(new.sounds_enabled)
    ctx.history = History(paths.history_path(), new.history_limit)
    _refresh_history(ctx)
    _refresh_status_info(ctx)
    _apply_hotkey(ctx)
    if needs_reload:
        if ctx.controller.state in BUSY_STATES:
            QMessageBox.information(
                ctx.window,
                APP_NAME,
                "Model değişikliği süren iş bittikten sonra "
                "Ayarlar'ı yeniden kaydedince uygulanır.",
            )
        else:
            ctx.controller.ready_changed.emit(False)
            ctx.controller.warm_up()


def _quit(ctx: AppContext) -> None:
    ctx.hotkey.unregister()
    ctx.cancel_hotkey.unregister()
    ctx.hotkey_translate.unregister()
    ctx.hotkey_prompt.unregister()
    ctx.tray.hide()
    app = QApplication.instance()
    if app is not None:
        app.quit()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="dikte")
    parser.add_argument("--minimized", action="store_true", help="pencere açmadan tray'de başla")
    parser.add_argument(
        "--toggle",
        action="store_true",
        help="çalışan örnekte kaydı başlat/durdur (Linux kısayolu için)",
    )
    parser.add_argument(
        "--start",
        action="store_true",
        help="çalışan örnekte kaydı başlatır (Linux'ta bas-konuş simülasyonu: tuşa basınca)",
    )
    parser.add_argument(
        "--stop",
        action="store_true",
        help="çalışan örnekte kaydı durdurur (Linux'ta bas-konuş simülasyonu: tuş bırakılınca)",
    )
    parser.add_argument(
        "--mode",
        choices=MODES,
        default="correct",
        help="--toggle/--start ile birlikte: sonucu doğrudan bu modda üretir (varsayılan: correct)",
    )
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {__version__}")
    args = parser.parse_args(argv)
    if args.toggle:
        return _run_toggle(args.mode)
    if args.start:
        return _run_command(_with_mode(START_MESSAGE, args.mode))
    if args.stop:
        return _run_command(STOP_MESSAGE)

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

    first_run = not paths.config_path().exists()
    settings = load_settings()
    ctx = build_app(settings)
    hotkeys_sanitized = (
        ctx.settings.hotkey != settings.hotkey
        or ctx.settings.hotkey_translate != settings.hotkey_translate
        or ctx.settings.hotkey_prompt != settings.hotkey_prompt
    )
    if hotkeys_sanitized:  # bozuk kısayol(lar) düzeltildi, kalıcı hâle getir
        save_settings(ctx.settings)
    single.activated.connect(ctx.tray.show_requested)
    single.toggle_requested.connect(ctx.controller.toggle)
    single.start_requested.connect(ctx.controller.start_recording)
    single.stop_requested.connect(ctx.controller.stop_recording)
    ctx.tray.show()
    if ctx.settings.hotkey != settings.hotkey:
        ctx.tray.notify(
            APP_NAME,
            f"Ayarlardaki kısayol geçersizdi; '{ctx.settings.hotkey}' kullanılıyor.",
        )
    if ctx.settings.hotkey_translate != settings.hotkey_translate or (
        ctx.settings.hotkey_prompt != settings.hotkey_prompt
    ):
        ctx.tray.notify(
            APP_NAME,
            "Ayarlardaki çeviri/prompt kısayollarından biri geçersizdi; kapatıldı.",
        )
    _apply_hotkey(ctx)
    set_autostart(settings.autostart)
    ctx.controller.warm_up()
    items = check_health(
        ctx.settings,
        cuda_probe=default_cuda_probe,
        model_probe=default_model_probe,
        llm_probe=default_llm_probe,
    )
    if first_run or any(not i.ok for i in items):
        _show_health_dialog(ctx, items)
    if not args.minimized:
        ctx.window.show()
    log.info("%s %s başladı", APP_NAME, __version__)
    return app.exec()
