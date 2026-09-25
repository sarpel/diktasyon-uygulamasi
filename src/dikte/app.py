from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from PySide6.QtCore import QCoreApplication, QMimeData, QObject, QThreadPool, QTimer
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox, QSystemTrayIcon

from dikte import APP_NAME, __version__, paths
from dikte.audio.recorder import AudioRecorder
from dikte.config import (
    AppProfile,
    DictionaryEntry,
    Settings,
    SettingsError,
    load_settings_with_issues,
    save_settings,
)
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
from dikte.core.workers import run_in_pool
from dikte.llm import LlmError, make_provider
from dikte.logging_setup import setup_logging
from dikte.platform.autostart import AutostartError, set_autostart
from dikte.platform.clipboard import build_mime, restore_delay_ms, should_restore
from dikte.platform.foreground import foreground_process_name
from dikte.platform.gpu_info import LOW_VRAM_MB, query_vram
from dikte.platform.hold_detect import HoldDetector
from dikte.platform.hotkey import HOTKEY_ID, GlobalHotkey
from dikte.platform.hotkey_parse import HotkeyParseError, parse_hotkey
from dikte.platform.media import MediaPauser
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
# check_health'in LLM kontrolü ağ isteği yapar; SDK varsayılan yeniden deneme + zaman
# aşımıyla en kötü durumda dakikalarca sürebilir. Senkron çağrı GUI iş parçacığını
# (ve bu iş parçacığında dönen IPC sunucusunu — bkz. single_instance.py) bloke ederdi.
_background_jobs: list = []
# Çıkışta kuyruktaki medya pause() çağrısı için en fazla bekleme (MediaPauser zaman aşımı ~1,5 sn).
MEDIA_QUIT_WAIT_MS = 2000  # run_in_pool sinyalleri iş bitene kadar canlı tutulmalı


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
    media: MediaPauser | None = None  # pause_media açıkken ilk kayıtta kurulur
    media_paused: bool = False
    # Medya çağrıları 1,5 sn'ye kadar sürebilir; tek iş parçacıklı havuz sırayı korur
    # (resume, kendi pause'undan önce çalışamaz).
    media_pool: QThreadPool | None = None
    hotkey_paste_last: GlobalHotkey | None = None  # isteğe bağlı: son sonucu yeniden yapıştırır


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
    for field_name in ("hotkey_translate", "hotkey_prompt", "hotkey_paste_last"):
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
        failed_audio_path=paths.failed_audio_path(),
    )
    hotkey = GlobalHotkey()
    cancel_hotkey = GlobalHotkey(hotkey_id=HOTKEY_ID + 1)  # iptal için ikinci kayıt
    hotkey_translate = GlobalHotkey(hotkey_id=HOTKEY_ID + 2)
    hotkey_prompt = GlobalHotkey(hotkey_id=HOTKEY_ID + 3)
    tray = TrayIcon(parse_hotkey(settings.hotkey).label)
    overlay = RecordingOverlay()
    window = ResultWindow()
    history = _make_history(settings)
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
    ctx.hotkey_paste_last = GlobalHotkey(hotkey_id=HOTKEY_ID + 4)
    overlay.set_position(settings.overlay_position, settings.overlay_xy)
    _wire(ctx)
    return ctx


def _prune_history(ctx: AppContext) -> None:
    ctx.history.prune()


def _make_history(settings: Settings) -> History:
    return History(
        paths.history_path(),
        settings.history_limit,
        retention_days=settings.history_retention_days,
    )


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
    c.state_changed.connect(lambda s: _sync_media(ctx, s))
    ctx.overlay.moved.connect(lambda x, y: _save_overlay_position(ctx, x, y))
    ctx.tray.paste_last_requested.connect(lambda: _paste_last(ctx))
    c.warning.connect(ctx.overlay.show_warning)
    c.failed_audio_changed.connect(ctx.tray.set_retry_available)
    ctx.tray.set_retry_available(c.has_failed_audio)
    ctx.tray.retry_failed_requested.connect(c.retry_last_failed)
    c.undo_requested.connect(lambda: _undo_last_paste(ctx))
    if ctx.hotkey_paste_last is not None:
        ctx.hotkey_paste_last.activated.connect(lambda: _paste_last(ctx))
    c.result_ready.connect(lambda text: _on_result_ready(ctx, text))
    ctx.window.history_panel.delete_requested.connect(lambda sid: _delete_session(ctx, sid))
    ctx.window.history_panel.clear_requested.connect(lambda: _clear_history(ctx))
    ctx.window.history_panel.export_requested.connect(lambda path: _export_history(ctx, path))
    ctx.tray.copy_requested.connect(lambda text: QApplication.clipboard().setText(text))
    ctx.window.record_requested.connect(c.toggle)
    ctx.window.cancel_requested.connect(c.cancel)
    ctx.window.settings_requested.connect(lambda: _open_settings(ctx))
    ctx.window.file_requested.connect(c.transcribe_file)
    ctx.window.text_edited.connect(lambda sid, text: _on_text_edited(ctx, sid, text))
    ctx.window.dictionary_add_requested.connect(
        lambda wrong, term: _add_dictionary_entry(ctx, wrong, term)
    )
    ctx.window.repaste_requested.connect(lambda text: _repaste(ctx, text))
    c.session_updated.connect(lambda s: _sync_history_on_edit(ctx, s))
    c.edit_learned.connect(lambda changes: _suggest(ctx, changes))
    c.ready_changed.connect(lambda ready: ready and _refresh_status_info(ctx))
    # Saklama süresi dolmuş dikteler yalnızca listeden gizlenmez, açılışta diskten de silinir.
    _guard_history(ctx, lambda: _prune_history(ctx))
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


def _guard_settings(ctx: AppContext, action: Callable[[], None]) -> bool:
    """Ayarlar yazılamazsa akış sürer; kullanıcı ne yapacağını bildiren bir uyarı alır.
    Başarıysa True döner (çağıranın devam edip etmeyeceğine karar vermesi için)."""
    try:
        action()
        return True
    except SettingsError as exc:
        log.error("ayarlar kaydedilemedi: %s", exc)
        ctx.tray.notify(APP_NAME, str(exc), critical=True)
        return False


def _store_session(ctx: AppContext) -> None:
    _guard_history(ctx, lambda: ctx.history.append(ctx.controller.session))
    _refresh_history(ctx)


def _refresh_history(ctx: AppContext) -> None:
    """Bozuk/okunamayan history.jsonl uygulamanın hiç açılmamasına neden olmasın diye
    korumalı: yükleme başarısız olursa kullanıcı bilgilendirilir, akış boş listeyle sürer."""
    sessions: tuple = ()

    def _load() -> None:
        nonlocal sessions
        sessions = ctx.history.load()

    _guard_history(ctx, _load)
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
    try:
        sessions = ctx.history.load()
    except HistoryError as exc:
        log.exception("dışa aktarım için geçmiş okunamadı")
        ctx.tray.notify(APP_NAME, str(exc), critical=True)
        return
    content = to_markdown(sessions) if path.lower().endswith(".md") else to_text(sessions)
    try:
        Path(path).write_text(content, encoding="utf-8")
    except OSError as exc:
        log.error("geçmiş dışa aktarılamadı: %s", exc)
        ctx.tray.notify(APP_NAME, f"Geçmiş dışa aktarılamadı: {exc}", critical=True)


def _on_text_edited(ctx: AppContext, session_id: str, text: str) -> None:
    """Düzenlenen metnin ait olduğu oturuma göre yönlendirir: canlı oturum ise denetleyiciye
    (öğrenme/geçmiş senkronu tetiklenir), geçmişten görüntülenen eski bir oturum ise doğrudan
    geçmiş kaydına yazılır — en son diktenin ezilmesini engeller."""
    if session_id == ctx.controller.session.id:
        ctx.controller.apply_edit(text)
    else:
        _apply_history_edit(ctx, session_id, text)


def _apply_history_edit(ctx: AppContext, session_id: str, text: str) -> None:
    sessions: tuple = ()

    def _load() -> None:
        nonlocal sessions
        sessions = ctx.history.load()

    _guard_history(ctx, _load)
    for s in sessions:
        if s.id == session_id:
            edited = s.with_(corrected_text=text)
            _guard_history(ctx, lambda edited=edited: ctx.history.update(edited))
            _refresh_history(ctx)
            return


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
    if not _guard_settings(ctx, lambda: save_settings(new_settings)):
        return
    ctx.settings = new_settings
    ctx.controller.update_settings(new_settings)


def _repaste(ctx: AppContext, text: str) -> None:
    ctx.window.hide()
    QTimer.singleShot(200, lambda: _on_result_ready(ctx, text, force_paste=True))


def _last_result_text(ctx: AppContext) -> str:
    """Son teslim edilen metin: canlı oturum, o yoksa geçmişteki en yeni kayıt."""
    text = ctx.controller.session.output_text
    if text:
        return text
    try:
        sessions = ctx.history.load()
    except HistoryError:
        log.exception("son sonuç için geçmiş okunamadı")
        return ""
    return sessions[-1].output_text if sessions else ""


def _undo_last_paste(ctx: AppContext) -> None:
    """Sesli "geri al" komutu: ön plandaki uygulamaya (kendi pencerelerimize değil) Ctrl+Z."""
    own_ids = {int(ctx.window.winId()), int(ctx.overlay.winId())}
    if not paste_active_window(own_ids, combo="ctrl+z"):
        ctx.tray.notify(APP_NAME, "Geri alma gönderilemedi; hedef uygulamada Ctrl+Z'ye basın.")


def _paste_last(ctx: AppContext) -> None:
    text = _last_result_text(ctx)
    if not text:
        ctx.tray.notify(APP_NAME, "Yapıştırılacak bir sonuç yok; önce bir dikte yapın.")
        return
    _on_result_ready(ctx, text, force_paste=True)


def _save_overlay_position(ctx: AppContext, x: int, y: int) -> None:
    """Overlay sürüklenince yeri hatırlanır ve konum "özel"e geçer."""
    new = ctx.settings.model_copy(update={"overlay_position": "custom", "overlay_xy": (x, y)})
    if _guard_settings(ctx, lambda: save_settings(new)):
        ctx.settings = new


def _refresh_status_info(ctx: AppContext) -> None:
    llm = ctx.settings.llm.active_model if ctx.settings.llm.enabled else "kapalı"
    ctx.window.set_status_info(ctx.stt.active_model, ctx.stt.compute_type, llm)
    _warn_if_low_vram(ctx)


def _warn_if_low_vram(ctx: AppContext) -> None:
    """`nvidia-smi` 3 sn'ye kadar sürebilir; GUI iş parçacığını bloke etmemek için arka planda."""
    job = run_in_pool(
        query_vram,
        lambda info: _show_low_vram_warning(ctx, info),
        lambda e: log.warning("VRAM sorgusu başarısız: %s", e),
        QThreadPool.globalInstance(),
    )
    _keep_job(job)


def _show_low_vram_warning(ctx: AppContext, info) -> None:
    if info is None:
        return
    free_mb = info.total_mb - info.used_mb
    if free_mb < LOW_VRAM_MB:
        free_gb = free_mb / 1024
        ctx.window.statusBar().showMessage(
            # gpu_info.format_vram ile aynı biçim (virgül ondalık ayracı, Türkçe kural).
            f"Boş VRAM düşük ({free_gb:.1f} GB)".replace(".", ",")
            + ": LLM'i kapatmayı veya keep_alive=0 yapmayı düşünün",
            15000,
        )


_TYPED_MIME_FORMATS = (
    "text/plain",
    "text/html",
    "text/uri-list",
    "application/x-qt-image",
    "application/x-color",
)


def _clone_mime(src: QMimeData) -> QMimeData:
    """`QClipboard.mimeData()` çağıranın sahip olmadığı bir nesne döndürür; panoyu
    değiştirmeden önce içeriğini korumak için bağımsız bir kopya çıkarır. Resim gibi
    bazı türler ("application/x-qt-image") ham bayt verisi değil bir QVariant olarak
    taşınır — yalnızca genel `data()/setData()` kullanmak bunları sessizce kaybederdi;
    tipe özel erişimciler (`imageData` vb.) de kullanılır."""
    clone = QMimeData()
    if src.hasText():
        clone.setText(src.text())
    if src.hasHtml():
        clone.setHtml(src.html())
    if src.hasUrls():
        clone.setUrls(src.urls())
    if src.hasImage():
        clone.setImageData(src.imageData())
    if src.hasColor():
        clone.setColorData(src.colorData())
    for fmt in src.formats():
        if fmt not in _TYPED_MIME_FORMATS:
            clone.setData(fmt, src.data(fmt))
    return clone


def _on_result_ready(ctx: AppContext, text: str, *, force_paste: bool = False) -> None:
    """Sonucu panoya yazar ve (ayar açıksa) ön plandaki uygulamaya yapıştırır.

    `restore_clipboard` açıksa ve yapıştırma gerçekten gönderildiyse, panodaki eski
    metin kısa bir gecikmeyle geri yazılır (yapıştırma hedef uygulamaya ulaşsın diye).
    `force_paste=True` (yalnızca "Yeniden yapıştır" eylemi): dosyadan çözümlenen bir
    oturumda bile kullanıcı açıkça yapıştırmayı istedi, otomatik-teslim kısıtlaması
    (aşağıdaki source_path kontrolü) burada atlanır.
    """
    if not text or not ctx.settings.auto_copy:
        return
    # ctx.active_profile yalnızca en son global kısayolu izler; tepsi/pencere düğmesi/IPC
    # ile başlatılan bir dikte hiç ondan geçmez, o zaman yanlış (eski) profil uygulanırdı.
    # controller.active_profile bu SONUCU üreten oturuma ait gerçek profildir.
    profile = ctx.controller.active_profile
    if profile and profile.trailing:
        text += profile.trailing
    clipboard = QApplication.clipboard()
    # Yalnızca clipboard.text() değil tüm QMimeData (resim/dosya de dahil) korunur; aksi
    # hâlde panoda bir resim varken dikte sonrası geri yükleme onu sessizce kaybederdi.
    # mimeData() clipboard'a ait olduğundan, clipboard değişmeden önce kopyalanmalı.
    previous_mime = _clone_mime(clipboard.mimeData()) if ctx.settings.restore_clipboard else None
    clipboard.setMimeData(build_mime(text, exclude_history=ctx.settings.clipboard_exclude_history))
    if ctx.controller.session.source_path and not force_paste:
        return  # dosyadan çözümlenen sonuç otomatik olarak yalnızca panoya kopyalanır
    if not ctx.settings.auto_paste or ctx.window.isActiveWindow():
        return
    own_ids = {int(ctx.window.winId()), int(ctx.overlay.winId())}
    foreground = foreground_window_id()
    if foreground is not None and foreground in own_ids:
        return
    paste_mode = profile.paste if profile else "ctrl+v"
    if paste_mode == "type":
        pasted = type_unicode_text(text)
    else:
        pasted = paste_active_window(own_ids, combo=paste_mode)
    if not pasted:
        log.info("yapıştırma atlandı; metin panoda")
        return
    if ctx.settings.restore_clipboard and previous_mime is not None and previous_mime.formats():
        QTimer.singleShot(
            restore_delay_ms(text), lambda: _restore_clipboard(clipboard, previous_mime, text)
        )


def _restore_clipboard(clipboard, previous_mime: QMimeData, pasted_text: str) -> None:
    """Kullanıcı bu arada yeni bir şey kopyaladıysa onu ezmez."""
    if should_restore(clipboard.text(), pasted_text):
        clipboard.setMimeData(previous_mime)
    else:
        log.info("pano geri yüklenmedi: bu arada yeni içerik kopyalanmış")


def _sync_media(ctx: AppContext, state: DictationState) -> None:
    """Kayıt başlarken çalan medyayı duraklatır, kayıt bitince yalnızca onları sürdürür."""
    recording = state is DictationState.RECORDING
    if recording == ctx.media_paused:
        return
    if recording and not ctx.settings.pause_media:
        return
    if ctx.media is None:
        ctx.media = MediaPauser()
    if ctx.media_pool is None:
        ctx.media_pool = QThreadPool()
        ctx.media_pool.setMaxThreadCount(1)
    ctx.media_paused = recording
    action = ctx.media.pause if recording else ctx.media.resume
    job = run_in_pool(
        action,
        lambda _r: None,
        lambda e: log.warning("medya denetimi başarısız: %s", e),
        ctx.media_pool,
    )
    _keep_job(job)


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


def _check_health_async(ctx: AppContext, on_done: Callable[[tuple[HealthItem, ...]], None]) -> None:
    """`check_health`'i arka planda çalıştırır (LLM kontrolü ağ isteği yapar, GUI iş
    parçacığını bloke etmemeli). `on_done` sonuçla GUI iş parçacığında çağrılır."""
    job = run_in_pool(
        lambda: check_health(
            ctx.settings,
            cuda_probe=default_cuda_probe,
            model_probe=default_model_probe,
            llm_probe=default_llm_probe,
        ),
        lambda result: on_done(cast("tuple[HealthItem, ...]", result)),
        lambda e: log.error("durum kontrolü başarısız: %s", e),
        QThreadPool.globalInstance(),
    )
    _keep_job(job)


def _keep_job(job) -> None:
    """run_in_pool sinyallerini iş bitene kadar canlı tutar; biten işler listeden düşer."""
    _background_jobs.append(job)
    for signal_name in ("result", "error"):
        signal = getattr(job, signal_name, None)
        if signal is not None:
            signal.connect(
                lambda *_a, job=job: job in _background_jobs and _background_jobs.remove(job)
            )


def _show_health_dialog(ctx: AppContext, items: tuple[HealthItem, ...] | None = None) -> None:
    if items is None:
        _check_health_async(ctx, lambda result: _show_health_dialog(ctx, result))
        return
    if ctx.health_dialog is not None:
        # Tekrarlayan model yükleme hataları (ör. her başarısız dikte denemesi) her
        # seferinde yeni bir pencere açardı; eskisi kapatılmadan referans üzerine
        # yazılınca kapanmamış pencereler birikirdi.
        ctx.health_dialog.close()
    llm = ctx.settings.llm
    dialog = HealthDialog(
        items,
        on_download=lambda progress: _download_model_for_ctx(ctx, progress),
        ollama_model=llm.model if llm.enabled and llm.provider == "ollama" else None,
        ollama_host=llm.ollama_host,
        health_probe=lambda: check_health(
            ctx.settings,
            cuda_probe=default_cuda_probe,
            model_probe=default_model_probe,
            llm_probe=default_llm_probe,
        ),
        parent=ctx.window,
    )
    # Pencere kapanınca kendini siler (WA_DeleteOnClose); silinmiş nesneye erişilmesin.
    dialog.destroyed.connect(lambda *_a: _forget_health_dialog(ctx, dialog))
    dialog.model_downloaded.connect(lambda: _on_model_downloaded(ctx))
    ctx.health_dialog = dialog
    dialog.setModal(False)
    dialog.show()


def _forget_health_dialog(ctx: AppContext, dialog: HealthDialog) -> None:
    if ctx.health_dialog is dialog:
        ctx.health_dialog = None


def _on_model_downloaded(ctx: AppContext) -> None:
    """İndirilen modelle yükleme yeniden denenir; tepsi "Model yükleniyor…"da takılmaz."""
    if ctx.controller.state in BUSY_STATES:
        _warm_up_when_idle(ctx)
    else:
        _reload_model(ctx)


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


def _resolve_profile(ctx: AppContext) -> AppProfile | None:
    """Ön plandaki uygulamaya uyan profili bulur ve `ctx.active_profile`'a yazar."""
    # Profil tanımlı değilse ön plan sürecini hiç sorgulama (win32 API'sini gereksiz çağırmaz).
    exe = foreground_process_name() if ctx.settings.profiles else ""
    ctx.active_profile = match_profile(ctx.settings.profiles, exe)
    return ctx.active_profile


def _on_ipc_toggle(ctx: AppContext, mode: str) -> None:
    """Linux'ta tek tetikleyici IPC'dir (`dikte --toggle`); profiller burada da uygulanır."""
    ctx.controller.toggle(mode, profile=_resolve_profile(ctx))


def _on_ipc_start(ctx: AppContext, mode: str) -> None:
    ctx.controller.start_recording(mode, profile=_resolve_profile(ctx))


def _on_hotkey(ctx: AppContext, mode: str = "correct") -> None:
    """Kısayola basılınca çağrılır: bas-konuş yalnızca Windows'ta anlamlıdır."""
    _resolve_profile(ctx)
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
        # Yeni kısayol kaydedilemezse GlobalHotkey eskisini geri kaydeder; etiket onu gösterir.
        ctx.tray.set_hotkey_label(ctx.hotkey.label or ctx.settings.hotkey)
    else:
        log.info("global kısayol bu platformda yok; '%s' komutuna tuş bağlayın", CLI_TOGGLE_HINT)
        ctx.tray.set_hotkey_label(CLI_TOGGLE_HINT)
    _apply_mode_hotkeys(ctx)
    _apply_paste_last_hotkey(ctx)


def _apply_paste_last_hotkey(ctx: AppContext) -> None:
    hk = ctx.hotkey_paste_last
    if hk is None:
        return
    hk.unregister()
    spec = ctx.settings.hotkey_paste_last
    if not spec or sys.platform != "win32":
        return
    if not hk.register(spec):
        ctx.tray.notify(
            APP_NAME,
            f"Son sonucu yapıştırma kısayolu kaydedilemedi: {spec}. "
            "Başka bir uygulama kullanıyor olabilir; Ayarlar'dan değiştirin.",
        )


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
    try:
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        new = dlg.result_settings()
    finally:
        # Her açılışta 8 sekmeli yeni bir pencere kurulur; silinmezse bellekte birikir.
        if isinstance(dlg, QObject):
            dlg.deleteLater()
    if not _guard_settings(ctx, lambda: save_settings(new)):
        return
    needs_reload = ctx.stt.update_settings(new.stt)
    ctx.recorder.update_settings(new.audio)
    llm_changed = new.llm != ctx.settings.llm
    ctx.settings = new
    _apply_autostart(ctx, new.autostart)
    ctx.controller.update_settings(new)
    if llm_changed:  # sağlayıcı yeniden kurulur, yeniden başlatma gerekmez
        ctx.controller.set_llm(_make_llm(new))
        ctx.controller.prewarm_llm()
    ctx.window.set_llm_enabled(new.llm.enabled)
    ctx.window.close_after_copy = new.close_after_copy
    ctx.window.raise_on_result = new.raise_window_on_result
    ctx.sounds.set_enabled(new.sounds_enabled)
    ctx.overlay.set_position(new.overlay_position, new.overlay_xy)
    ctx.history = _make_history(new)
    # Sınır/saklama süresi düşürüldüyse (ör. 0 = geçmiş kapalı) eski dikteler diskte kalmasın.
    _guard_history(ctx, lambda: _prune_history(ctx))
    _refresh_history(ctx)
    _refresh_status_info(ctx)
    _apply_hotkey(ctx)
    if needs_reload:
        if ctx.controller.state in BUSY_STATES:
            QMessageBox.information(
                ctx.window,
                APP_NAME,
                "Model değişikliği süren iş bittiğinde otomatik olarak uygulanacak.",
            )
            _warm_up_when_idle(ctx)
        else:
            _reload_model(ctx)


def _reload_model(ctx: AppContext) -> None:
    ctx.controller.ready_changed.emit(False)
    ctx.controller.warm_up()


def _warm_up_when_idle(ctx: AppContext) -> None:
    """Süren iş bitince (motor modeli zaten düşürdü) yeni modeli bir kez yükler."""

    def _on_state(state: DictationState) -> None:
        if state in BUSY_STATES:
            return
        ctx.controller.state_changed.disconnect(_on_state)
        _reload_model(ctx)

    ctx.controller.state_changed.connect(_on_state)


def _apply_autostart(ctx: AppContext, enabled: bool) -> None:
    try:
        set_autostart(enabled)
    except AutostartError as exc:
        ctx.tray.notify(APP_NAME, str(exc), critical=True)


def _quit(ctx: AppContext) -> None:
    if ctx.media is not None and ctx.media_paused:
        # Kayıt sürerken çıkılırsa duraklatılan medya askıda kalmasın. pause() medya
        # havuzunda hâlâ sürüyor olabilir; önce onu beklemezsek resume() boşa gider ve
        # ardından biten pause() medyayı duraklatılmış bırakır.
        if ctx.media_pool is not None:
            ctx.media_pool.waitForDone(MEDIA_QUIT_WAIT_MS)
        ctx.media.resume()
    ctx.hotkey.unregister()
    ctx.cancel_hotkey.unregister()
    ctx.hotkey_translate.unregister()
    ctx.hotkey_prompt.unregister()
    if ctx.hotkey_paste_last is not None:
        ctx.hotkey_paste_last.unregister()
    ctx.tray.hide()
    app = QApplication.instance()
    if app is not None:
        app.quit()


def _notify_config_issues(ctx: AppContext, issues: tuple[str, ...]) -> None:
    backup = paths.config_path().with_suffix(".json.bak")
    if issues == ("*",):
        detail = "Ayar dosyası okunamadı; varsayılanlar kullanılıyor."
    else:
        detail = "Geçersiz ayarlar varsayılana döndü: " + ", ".join(issues) + "."
    ctx.tray.notify(APP_NAME, f"{detail} Eski dosyanın yedeği: {backup}", critical=True)


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

    try:
        first_run = not paths.config_path().exists()
        settings, config_issues = load_settings_with_issues()
        ctx = build_app(settings)
    except OSError as exc:
        # Veri klasörü (paths.app_data_dir()) oluşturulamadı/yazılamadı — paketlenmiş
        # derlemede (console=False) hiçbir iz bırakmadan sessizce kapanmak yerine kullanıcıya
        # nedeni gösterilir.
        log.exception("veri klasörü hazırlanamadı")
        QMessageBox.critical(
            None,
            APP_NAME,
            f"Veri klasörü hazırlanamadı: {exc}\nYazma izinlerini kontrol edin.",
        )
        return 1
    hotkeys_sanitized = (
        ctx.settings.hotkey != settings.hotkey
        or ctx.settings.hotkey_translate != settings.hotkey_translate
        or ctx.settings.hotkey_prompt != settings.hotkey_prompt
    )
    if hotkeys_sanitized:  # bozuk kısayol(lar) düzeltildi, kalıcı hâle getir
        try:
            save_settings(ctx.settings)
        except SettingsError:
            log.exception("düzeltilmiş kısayol ayarları kaydedilemedi")
    single.activated.connect(ctx.tray.show_requested)
    single.toggle_requested.connect(lambda mode: _on_ipc_toggle(ctx, mode))
    single.start_requested.connect(lambda mode: _on_ipc_start(ctx, mode))
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
    if config_issues:
        _notify_config_issues(ctx, config_issues)
    _apply_hotkey(ctx)
    _apply_autostart(ctx, settings.autostart)
    ctx.controller.warm_up()

    def _after_startup_health_check(items: tuple[HealthItem, ...]) -> None:
        if first_run or any(not i.ok for i in items):
            _show_health_dialog(ctx, items)

    _check_health_async(ctx, _after_startup_health_check)
    if not args.minimized:
        ctx.window.show()
    log.info("%s %s başladı", APP_NAME, __version__)
    return app.exec()
