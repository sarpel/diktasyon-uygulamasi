# Dikte — İyileştirme Planı (UI/UX · QOL · Performans · Doğruluk)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Tarih:** 2026-09-14 · **Sürüm:** 0.1.0 (commit `1c6e3c7`) · **Durum (2026-09-15):** T1–T8 uygulandı ve commit edildi (`feat/improvement-plan` dalı, 313 test, %91 kapsam). T9'un kodu, veri seti ve testleri hazır; **ölçüm bekliyor** (bu ortamda Ollama erişilemiyor + aday model listesi kullanıcı onayı bekliyor).

**Goal:** Dikte'yi "kısayola bas → konuş → metin imlecin olduğu yere düşsün" akışına getirmek; iptal, geçmiş, sınırsız kayıt, ısınma, çoklu uzak LLM sağlayıcı, halüsinasyona dayanıklı VAD ve ölçülmüş bir varsayılan LLM ile.

**Architecture:** Mevcut PySide6 tepsi uygulaması korunur. `DictationController` durum makinesi `cancel()` ve `result_ready` sinyaliyle genişler; platform katmanına `paste.py` eklenir; `LlmProvider` protokolü değişmeden yeni sağlayıcılar birer dosya olarak gelir; STT motoru VAD ön-kontrolü ve halüsinasyon filtresi kazanır; ayarlar diyaloğu `QTabWidget`'a taşınır.

**Tech Stack:** Python 3.11/3.12, PySide6 6.11, faster-whisper 1.2.1 (dahili Silero VAD), ctranslate2, ollama, pydantic v2, pytest + pytest-qt, ruff.

**Spec:** Bu dosyanın §1–§3'ü (inceleme bulguları ve kullanıcı kararları). Ayrı spec yok.

## Global Constraints

- Yanıt/yorum/commit dili Türkçe, tam diakritikli. Kod tanımlayıcıları İngilizce.
- TDD zorunlu: önce başarısız test, sonra en küçük uygulama, sonra commit. Conventional Commits (`feat:`, `fix:`, `test:`, `docs:`, `chore:`).
- Kapsam ≥ %80 (bugün %88, 134 test). Her görev sonunda: `.venv/bin/python -m pytest -q` yeşil, `.venv/bin/ruff check src tests` temiz, `.venv/bin/ruff format --check src tests` temiz.
- Proje venv'i: `.venv/bin/python`. Sistem python'u kullanılmaz.
- Gizli bilgi kaynak koda ve `config.json`'a yazılmaz. API anahtarları **yalnızca** ortam değişkeninden okunur; UI sadece ✓/✗ gösterir; loglara asla yazılmaz.
- CPU geri dönüşü yok; GPU zorunlu (kullanıcı kararı). Tüm GPU/CUDA/ağ erişimleri enjekte edilebilir (`*_factory`, `*_probe`) olmalı ki testler GPU'suz CI'da geçsin.
- Pydantic modelleri `frozen=True`; değişiklik `model_copy(update=...)` ile. Hiçbir yerde yerinde mutasyon yok.
- UI metinleri Türkçe. Hata mesajları kullanıcıya ne yapacağını söyler ("Ayarlar'dan … açın").
- Yeni bağımlılıklar `pyproject.toml`'da **isteğe bağlı extra** olur (`[openai]`, `[gemini]`); çekirdek kurulum büyümez.
- Kullanıcı kararı: kayıt süresi **sınırsız**; iptal **Esc + Vazgeç düğmesi**; sonuç **panoda kalır + aktif pencereye yapıştırılır + geçmişe yazılır**.

---

## 1. Kısa cevap: GUI mi, terminal mi?

**GUI.** PySide6 ile yazıldı: tepsi simgesi + menü (`ui/tray.py`), 1100×620 sonuç penceresi (`ui/result_window.py`), 374×446 ayar diyaloğu (`ui/settings_dialog.py`, tek düz form, 14 satır, **sekme yok**), kayıt overlay'i (`ui/overlay.py`), toast. Terminal yalnızca `dikte --toggle` ve `--version` için.

---

## 2. İnceleme bulguları

Ölçek: 🔴 akışı bozuyor · 🟠 belirgin sürtünme · 🟡 cilalama · ✅ = bu planda görevi var

### 2.1 UX akışı

| # | Bulgu | Önem | Nerede | Görev |
|---|---|---|---|---|
| U1 | Sonuç aktif uygulamaya yapıştırılmıyor; pencereye gidip kopyalamak gerekiyor. | 🔴 | `result_window.py:107` | ✅ T4 |
| U2 | Geçmiş `history.jsonl`'a yazılıyor ama arayüzde yok. | 🔴 | `core/history.py` | ✅ T5 |
| U3 | 600 sn'de kayıt **sessizce** kesiliyor (`if room <= 0: return`). | 🔴 | `audio/recorder.py:597` | ✅ T1 |
| U4 | İptal yok; TRANSCRIBING/CORRECTING'de toggle yok sayılıyor. | 🟠 | `controller.py:289` | ✅ T2 |
| U5 | Her sonuçta pencere öne fırlıyor, odağı çalıyor. | 🟠 | `result_window.py:108` | ✅ T4 |
| U6 | İlk çalıştırmada 1,6 GB model ilerleme göstermeden iniyor. | 🟠 | `stt/engine.py` | sonraya |
| U7 | Hatalar 4 sn'lik tepsi balonunda kayboluyor. | 🟠 | `app.py:97` | ✅ T6 (durum çubuğu) |
| U8 | Kısayol serbest metin; tuşa basarak yakalama yok. | 🟡 | `settings_dialog.py:44` | ✅ T6 |

### 2.2 Sonuç penceresi

| # | Bulgu | Önem | Görev |
|---|---|---|---|
| R1 | Değişiklik listesinde `x → x` özdeş çiftler gösteriliyor. | 🟠 | ✅ T5 |
| R2 | Üçüncü sütun (çeviri/prompt) çoğu zaman boş; ekranın 1/3'ü israf. | 🟠 | sonraya |
| R3 | Araç çubuğu yok; Kaydet/Geçmiş/Ayarlar yalnızca tepsiden. | 🟠 | ✅ T5 |
| R4 | Süre, kelime sayısı, model/hassasiyet, LLM bilgisi yok. | 🟡 | ✅ T5 |
| R5 | Tek kısayol (Ctrl+Shift+C); Esc pencereyi gizlemiyor. | 🟡 | ✅ T2 |
| R6 | Sistem koyu temasını takip etmiyor. | 🟡 | sonraya |

### 2.3 Ayarlar

| # | Bulgu | Önem | Görev |
|---|---|---|---|
| S1 | Sekme/gruplama yok. | 🟠 | ✅ T6 |
| S2 | 10 ayar arayüzde yok (`beam_size`, `vad_filter`, `initial_prompt`, `num_ctx`, `top_p`, `top_k`, `timeout_s`, `think`, `anthropic_model`, `max_seconds`). | 🟠 | ✅ T6 |
| S3 | Sağlayıcıya göre alanlar gizlenmiyor. | 🟡 | ✅ T6/T7 |
| S4 | Test düğmeleri yok (mikrofon seviyesi, LLM bağlantı testi, GPU bilgisi). | 🟡 | ✅ T6 |
| S5 | Yeniden başlatma gerektiren alan işaretli değil. | 🟡 | ✅ T6 |

### 2.4 Performans

| # | Bulgu | Görev |
|---|---|---|
| P1 | İlk düzeltme Ollama model yüklemesini bekliyor (+2–5 sn). | ✅ T3 |
| P2 | STT ilk çözümleme cuDNN/JIT yüzünden yavaş (+0,5–2 sn). | ✅ T3 |
| P3 | Çeviri/prompt akışsız (`stream=False`). | sonraya |
| P4 | `beam_size=5`; turbo için 1–2 yeterli, ayarda yok. | ✅ T6 (alan) |
| P5 | `without_timestamps` verilmiyor. | ✅ T8 |

### 2.5 Doğruluk

| # | Bulgu | Görev |
|---|---|---|
| Q1 | Whisper sessiz/çok kısa parçalarda "Altyazı M.K.", "İzlediğiniz için teşekkürler" gibi halüsinasyon üretiyor. **VAD zaten var** (faster-whisper `vad_filter=True` = dahili Silero VAD); eksik olan: tamamen sessiz kaydın hiç çözümlenmemesi, `no_speech_threshold`/`hallucination_silence_threshold` kullanımı, bilinen halüsinasyon kara listesi ve VAD eşiklerinin ayarlanabilirliği. | ✅ T8 |
| Q2 | Uzak sağlayıcı yalnızca Anthropic; OpenAI-uyumlu, Gemini ve **özel (custom) uç nokta** yok. Anthropic'te JSON şeması prompt'a gömülüp `{…}` ile ayıklanıyor. | ✅ T7 |
| Q3 | Varsayılan LLM (`qwen3.5:4b`) ölçülmeden seçildi; `scripts/eval_llm.py` puanlamıyor, sadece çıktı basıyor. | ✅ T9 |
| Q4 | Özel sözlük (hotwords) yok. | sonraya |

### 2.6 Bulunan hatalar

| # | Hata | Görev |
|---|---|---|
| B1 | `config.json`'da geçersiz kısayol → `build_app` içinde `parse_hotkey` yakalanmıyor → açılışta çökme. | ✅ T6 |
| B2 | = U3 (sessiz kesme). | ✅ T1 |
| B3 | Overlay her zaman birincil ekranda; imlecin ekranında değil. | ✅ T2 |
| B4 | = R1. | ✅ T5 |

---

## 3. Kullanıcı kararları (2026-09-14)

1. Sonuç aktif pencereye yapıştırılır **ve** panoda kalır **ve** geçmişe yazılır.
2. Geçmiş kaydedilir; pencerede **Geçmiş düğmesi** ile görülür.
3. Süre sınırı kalkar: **sınırsız kayıt**. Sessiz kesme hatası düzeltilir.
4. İptal: **Esc tuşu + Vazgeç düğmesi**.
5. Gerekli ısınmalar yapılır (STT + LLM).
6. Sağlayıcılar: Ollama, OpenAI, Anthropic, Gemini **+ Custom** (base URL + model + anahtar env adı + **format seçimi: OpenAI-uyumlu / Anthropic-uyumlu**).
7. Sessizlik/halüsinasyon: Silero VAD tabanlı ön-kontrol + halüsinasyon filtresi, eşikler ayarlanabilir.
8. Bu bilgisayarda (RTX 3060 Ti, 8 GB) Türkçeye özgü **bilerek yerleştirilmiş hatalar + bağlam** benchmark'ı; 10 üzerinden en yüksek puanlı **güncel** model varsayılan olur.

---

## 4. Görev sırası ve süreler

| Görev | Başlık | Süre | Bağımlılık |
|---|---|---|---|
| T1 | Sınırsız kayıt + sessiz kesme hatası | 1,5 sa | — |
| T2 | İptal: `cancel()`, Esc, Vazgeç düğmesi, imleç ekranı | 3 sa | — |
| T3 | Isınma: STT + Ollama | 1,5 sa | — |
| T4 | Pano + aktif pencereye yapıştırma + "öne getirme" ayarı | 4 sa | — |
| T5 | Geçmiş paneli + araç çubuğu + durum çubuğu + özdeş değişiklik filtresi | 5 sa | — |
| T6 | Sekmeli ayarlar + eksik alanlar + kısayol yakalama + B1 | 5 sa | T1–T5 alanları |
| T7 | Sağlayıcılar: OpenAI-uyumlu, Gemini, Custom (format seçimli) | 5 sa | T6 |
| T8 | VAD ön-kontrolü + halüsinasyon filtresi + eşik ayarları | 3 sa | T6 |
| T9 | Türkçe LLM benchmark'ı + varsayılan model seçimi | 4 sa + model indirme | T7 (isteğe bağlı) |

Toplam ≈ 4 iş günü. Her görev bağımsız commit; T1–T5 paralel çalıştırılabilir (farklı dosyalar), T6 onları birleştirir.

---

## 5. Görevler

### T1: Sınırsız kayıt ve sessiz kesme hatasının düzeltilmesi

**Amaç:** `max_seconds` 0 = sınırsız (yeni varsayılan). Sınır konulursa dolunca ses atılmaz; `limit_reached` sinyali çıkar, denetleyici kaydı **kendisi durdurup çözümler**.

**Files:**
- Modify: `src/dikte/config.py` (`AudioSettings.max_seconds`)
- Modify: `src/dikte/audio/recorder.py` (`_on_audio`, yeni sinyal)
- Modify: `src/dikte/core/controller.py` (`__init__` bağlama)
- Modify: `src/dikte/ui/settings_dialog.py` (alan; T6'da sekmeye taşınır)
- Test: `tests/test_recorder.py`, `tests/test_config.py`, `tests/test_controller.py`

**Interfaces:**
- Produces: `AudioSettings.max_seconds: int = Field(default=0, ge=0)` (0 = sınırsız)
- Produces: `AudioRecorder.limit_reached = Signal()` — sınır dolduğunda **bir kez** yayılır
- Consumes (T2): `DictationController._stop_and_transcribe()`

- [ ] **Adım 1: Başarısız testleri yaz**

`tests/test_recorder.py` içine ekle (mevcut `FakeStream`/`make_recorder` yardımcılarını kullan; yoksa dosyadaki mevcut örüntüyü takip et):

```python
def test_unlimited_recording_keeps_all_audio(recorder_factory):
    rec = recorder_factory(max_seconds=0)
    rec.start()
    for _ in range(50):  # 50 × 1600 = 80 000 örnek = 5 sn
        rec._on_audio(np.ones((1600, 1), dtype=np.float32), 1600, None, None)
    assert rec.stop().shape[0] == 80_000


def test_limit_emits_signal_once_and_keeps_everything_up_to_limit(recorder_factory, qtbot):
    rec = recorder_factory(max_seconds=1)  # 16 000 örnek
    fired = []
    rec.limit_reached.connect(lambda: fired.append(True))
    rec.start()
    for _ in range(12):  # 19 200 örnek
        rec._on_audio(np.ones((1600, 1), dtype=np.float32), 1600, None, None)
    assert fired == [True]
    assert rec.stop().shape[0] == 16_000
```

`tests/test_config.py`:

```python
def test_default_recording_is_unlimited():
    assert AudioSettings().max_seconds == 0


def test_negative_max_seconds_rejected():
    with pytest.raises(ValidationError):
        AudioSettings(max_seconds=-1)
```

`tests/test_controller.py` (mevcut `FakeRecorder`'a `limit_reached = Signal()` ekle):

```python
def test_limit_reached_stops_and_transcribes(ctrl, fake_recorder):
    ctrl.toggle()
    assert ctrl.state is DictationState.RECORDING
    fake_recorder.limit_reached.emit()
    assert ctrl.state is DictationState.TRANSCRIBING
```

- [ ] **Adım 2: Çalıştır, başarısız olduğunu gör**

```bash
.venv/bin/python -m pytest -q tests/test_recorder.py tests/test_config.py tests/test_controller.py
```
Beklenen: `limit_reached` AttributeError, `max_seconds` varsayılan 600.

- [ ] **Adım 3: Uygula**

`config.py`:
```python
class AudioSettings(BaseModel):
    model_config = ConfigDict(frozen=True)
    device_index: int | None = None
    sample_rate: int = 16000
    max_seconds: int = Field(default=0, ge=0)  # 0 = sınırsız
```

`recorder.py`:
```python
class AudioRecorder(QObject):
    level_changed = Signal(float)
    buckets_changed = Signal(object)
    limit_reached = Signal()
    error = Signal(str)
    ...
    def start(self) -> None:
        ...
        self._chunks, self._total, self._limit_hit = [], 0, False

    def _on_audio(self, indata, frames, time_info, status) -> None:
        if status:
            log.warning("audio status: %s", status)
        frame = np.asarray(indata, dtype=np.float32).reshape(-1)
        limit = self._settings.max_seconds * self._settings.sample_rate
        with self._lock:
            if limit > 0:
                room = limit - self._total
                if room <= 0:
                    hit, self._limit_hit = self._limit_hit, True
                    if not hit:
                        self.limit_reached.emit()
                    return
                frame = frame[:room].copy()
            self._chunks.append(frame)
            self._total += frame.shape[0]
        self.level_changed.emit(rms(frame))
        self.buckets_changed.emit(bucketize(frame, BUCKETS))
```
(`_limit_hit` `__init__`'te `False`; sinyal kilit dışında yayılmalıysa bayrağı kilit içinde al, `emit`'i `with` bloğundan sonra yap.)

`controller.py` `__init__`: `recorder.limit_reached.connect(self._on_limit_reached)`;
```python
    def _on_limit_reached(self) -> None:
        if self._state is DictationState.RECORDING:
            log.info("kayıt süresi sınırına ulaşıldı, otomatik durduruluyor")
            self._stop_and_transcribe()
```

`settings_dialog.py`: `self.max_seconds_spin = QSpinBox()`; aralık 0–36000; suffix " sn"; `setSpecialValueText("Sınırsız")`; `result_settings` içine `"max_seconds": self.max_seconds_spin.value()`.

- [ ] **Adım 4: Testler yeşil, ruff temiz**
- [ ] **Adım 5: README "Bilinen sınırlar" satırını güncelle (600 sn kaldı → sınırsız; bellek: 16 kHz float32 ≈ 230 MB/saat).**
- [ ] **Adım 6: Commit** — `fix: kayıt süresi sınırsız; sınır dolunca ses atılmak yerine kayıt otomatik durur`

---

### T2: İptal — `cancel()`, Esc, Vazgeç düğmesi, overlay imleç ekranında

**Amaç:** Kayıt sırasında iptal = ses atılır, IDLE. Çözümleme/düzeltme sırasında iptal = çalışan iş sonucu **yok sayılır** (thread öldürülemez), IDLE. Esc: pencere odaktayken `QShortcut`; Windows'ta kayıt/işlem sürerken **global Esc** (ikinci `RegisterHotKey`). Overlay'de "Vazgeç" düğmesi ve tepside "Vazgeç" eylemi.

**Files:**
- Modify: `src/dikte/core/controller.py`
- Modify: `src/dikte/platform/hotkey.py` (birden çok kimlik)
- Modify: `src/dikte/ui/overlay.py`, `src/dikte/ui/tray.py`, `src/dikte/ui/result_window.py`, `src/dikte/app.py`
- Test: `tests/test_controller.py`, `tests/test_tray.py`, `tests/test_app_wiring.py`, yeni `tests/test_overlay.py`

**Interfaces:**
- Produces: `DictationController.cancel()` slot; `DictationController.cancelled = Signal()`
- Produces: `GlobalHotkey(hotkey_id: int = HOTKEY_ID)` — her örnek kendi kimliğiyle kaydolur
- Produces: `RecordingOverlay.cancel_requested = Signal()`; `TrayIcon.cancel_requested = Signal()`
- Produces: `RecordingOverlay._place()` imlecin bulunduğu ekranı kullanır

- [ ] **Adım 1: Başarısız testler**

`tests/test_controller.py`:
```python
def test_cancel_while_recording_discards_audio_and_goes_idle(ctrl, fake_recorder):
    ctrl.toggle()
    ctrl.cancel()
    assert ctrl.state is DictationState.IDLE
    assert fake_recorder.stopped  # stop() çağrıldı
    assert ctrl.session.raw_text == ""


def test_cancel_while_transcribing_ignores_late_result(ctrl, fake_stt, qtbot):
    ctrl.toggle(); ctrl.toggle()  # RECORDING -> TRANSCRIBING
    ctrl.cancel()
    assert ctrl.state is DictationState.IDLE
    fake_stt.release()  # bekleyen işi bitir
    qtbot.wait(50)
    assert ctrl.state is DictationState.IDLE  # RESULT'a geçmedi
    assert ctrl.session.raw_text == ""


def test_cancel_in_idle_is_noop(ctrl):
    fired = []
    ctrl.cancelled.connect(lambda: fired.append(1))
    ctrl.cancel()
    assert fired == [] and ctrl.state is DictationState.IDLE
```
(`fake_stt.release()` için mevcut sahte STT'ye `threading.Event` ekle: `transcribe` event'i bekler.)

`tests/test_overlay.py` (yeni):
```python
def test_cancel_button_emits_signal(qtbot):
    o = RecordingOverlay(); qtbot.addWidget(o)
    fired = []
    o.cancel_requested.connect(lambda: fired.append(1))
    o.show_recording()
    qtbot.mouseClick(o.cancel_btn, Qt.LeftButton)
    assert fired == [1]


def test_overlay_uses_screen_under_cursor(qtbot, monkeypatch):
    o = RecordingOverlay(); qtbot.addWidget(o)
    called = {}
    monkeypatch.setattr(overlay_mod.QGuiApplication, "screenAt",
                        staticmethod(lambda pos: called.setdefault("pos", pos) or None))
    o.show_recording()
    assert "pos" in called  # screenAt sorgulandı; None dönünce primaryScreen'e düşer
```

`tests/test_tray.py`: `cancel_requested` eylemi yalnızca RECORDING/TRANSCRIBING/CORRECTING'de etkin.

`tests/test_app_wiring.py`:
```python
def test_escape_shortcut_cancels(ctx, qtbot):
    ctx.controller.toggle()
    ctx.window.show()
    qtbot.keyClick(ctx.window, Qt.Key_Escape)
    assert ctx.controller.state is DictationState.IDLE


def test_cancel_hotkey_registered_only_while_busy(ctx, monkeypatch):
    calls = []
    ctx.cancel_hotkey.register = lambda spec: calls.append(("reg", spec)) or True
    ctx.cancel_hotkey.unregister = lambda: calls.append(("unreg", None))
    ctx.controller.state_changed.emit(DictationState.RECORDING)
    ctx.controller.state_changed.emit(DictationState.IDLE)
    assert calls == [("reg", "escape"), ("unreg", None)]
```

- [ ] **Adım 2: Çalıştır, başarısız gör**
- [ ] **Adım 3: Uygula**

`controller.py`:
```python
    cancelled = Signal()

    def __init__(...):
        ...
        self._gen = 0  # iptal sonrası gelen sonuçları ayırt etmek için

    @Slot()
    def cancel(self) -> None:
        if self._state is DictationState.IDLE or self._state is DictationState.RESULT:
            return
        self._gen += 1
        if self._state is DictationState.RECORDING:
            self._recorder.stop()  # ses atılır
        self._session = Session()
        self.session_updated.emit(self._session)
        self._set_state(DictationState.IDLE)
        self.cancelled.emit()

    def _spawn(self, fn, on_result, on_error) -> None:
        gen = self._gen
        def guarded_result(r):
            if gen == self._gen:
                on_result(r)
            else:
                log.debug("iptal edilmiş işin sonucu yok sayıldı")
        def guarded_error(e):
            if gen == self._gen:
                on_error(e)
        sig = run_in_pool(fn, guarded_result, guarded_error, self._pool)
        self._jobs.append(sig)
        self._jobs = self._jobs[-16:]
```
`warm_up` bu koruma dışında kalmalı (iptal ısınmayı bozmasın): `warm_up` içinde `self._spawn` yerine doğrudan `run_in_pool` kullan ve `_jobs`'a ekle.

`hotkey.py`: `GlobalHotkey.__init__(self, hotkey_id: int = HOTKEY_ID, parent=None)`; `self._id` kullan; `_Filter` `hotkey_id` alır. `parse_hotkey("escape")` desteklenmiyorsa `hotkey_parse.py`'ye `escape`/`esc` → `VK_ESCAPE = 0x1B`, modifiers 0 ekle (test: `tests/test_hotkey_parse.py`).

`overlay.py`: panele `self.cancel_btn = QPushButton("Vazgeç")` (düz stil, `QPushButton{color:white;background:rgba(255,255,255,30);border-radius:6px;padding:4px 10px;}`), `clicked → cancel_requested`. `_place`:
```python
        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        geo = screen.availableGeometry()
```

`tray.py`: `cancel_requested = Signal()`, `QAction("Vazgeç")`; `set_state` içinde `setEnabled(state in (RECORDING, TRANSCRIBING, CORRECTING))`.

`result_window.py`: `QShortcut(QKeySequence(Qt.Key_Escape), self, activated=self._on_escape)`; `_on_escape`: denetleyici meşgulse `cancel()`, değilse `hide()`.

`app.py`: `AppContext.cancel_hotkey: GlobalHotkey`; `build_app`'te `GlobalHotkey(hotkey_id=HOTKEY_ID + 1)`; `_wire`:
```python
    c.cancelled.connect(lambda: ctx.tray.notify(APP_NAME, "İptal edildi"))
    ctx.overlay.cancel_requested.connect(c.cancel)
    ctx.tray.cancel_requested.connect(c.cancel)
    ctx.cancel_hotkey.activated.connect(c.cancel)
    c.state_changed.connect(lambda s: _sync_cancel_hotkey(ctx, s))
```
```python
def _sync_cancel_hotkey(ctx: AppContext, state: DictationState) -> None:
    busy = state in (DictationState.RECORDING, DictationState.TRANSCRIBING, DictationState.CORRECTING)
    if busy:
        if not ctx.cancel_hotkey.register("escape"):
            log.info("global Esc kaydedilemedi; pencere/overlay ile iptal edilebilir")
    else:
        ctx.cancel_hotkey.unregister()
```
Not: Windows'ta kayıt sürerken Esc **global** yakalanır (başka uygulamalara gitmez). Bu bilinçli; README'ye yaz. Linux'ta `register` False döner, overlay/pencere/tepsi ile iptal edilir.

- [ ] **Adım 4: Testler + ruff**
- [ ] **Adım 5: `docs/manual_test_checklist.md`'ye "İptal" bölümü (4 madde: kayıt sırasında Esc, çözümleme sırasında Vazgeç, tepsiden Vazgeç, Linux'ta overlay düğmesi).**
- [ ] **Adım 6: Commit** — `feat: kayıt ve çözümleme iptali (Esc, Vazgeç düğmesi, tepsi); overlay imleç ekranında`

---

### T3: Isınma — STT ve LLM

**Amaç:** Model yüklendikten sonra 1 sn sentetik sesle `transcribe` çağrılır (cuDNN/JIT ısınır). LLM açıksa ve sağlayıcı Ollama ise, Whisper yüklenirken **paralel** boş bir istekle model VRAM'e alınır (`keep_alive` uygulanır). İkisi de ayarla kapatılabilir.

**Files:**
- Modify: `src/dikte/config.py` (`SttSettings.warm_up: bool = True`, `LlmSettings.prewarm: bool = True`)
- Modify: `src/dikte/stt/engine.py` (`warm_up()`)
- Modify: `src/dikte/llm/provider.py` (protokole isteğe bağlı `warm_up`), `src/dikte/llm/ollama_provider.py`
- Modify: `src/dikte/core/controller.py` (`warm_up` iki iş başlatır)
- Test: `tests/test_stt_engine.py`, `tests/test_ollama_provider.py`, `tests/test_controller.py`

**Interfaces:**
- Produces: `FasterWhisperEngine.warm_up() -> None` (yüklü değilse `load()` çağırır; hata loglanır, yükseltilmez)
- Produces: `OllamaProvider.warm_up() -> None` (`client.chat(model=..., messages=[], keep_alive=...)`); diğer sağlayıcılarda yok → `getattr(llm, "warm_up", None)`
- Produces: `DictationController.warm_up()` — STT ısınmasından sonra `ready_changed(True)`; LLM ısınması bağımsız, sonucu beklenmez

- [ ] **Adım 1: Başarısız testler**

`tests/test_stt_engine.py`:
```python
def test_warm_up_runs_one_dummy_transcribe(engine_with_fake_model):
    eng, fake = engine_with_fake_model
    eng.warm_up()
    assert fake.calls == 1
    audio = fake.last_audio
    assert audio.dtype == np.float32 and audio.shape[0] == 16_000


def test_warm_up_swallows_transcribe_errors(engine_with_failing_model, caplog):
    eng = engine_with_failing_model
    eng.warm_up()  # yükseltmez
    assert "ısınma" in caplog.text.lower()


def test_warm_up_skipped_when_disabled(engine_factory):
    eng, fake = engine_factory(warm_up=False)
    eng.warm_up()
    assert fake.calls == 0
```

`tests/test_ollama_provider.py`:
```python
def test_warm_up_sends_empty_chat_with_keep_alive(fake_client):
    p = OllamaProvider(LlmSettings(model="m", keep_alive="30m"), client_factory=lambda h, t: fake_client)
    p.warm_up()
    call = fake_client.chat_calls[-1]
    assert call["model"] == "m" and call["messages"] == [] and call["keep_alive"] == "30m"


def test_warm_up_error_is_logged_not_raised(failing_client, caplog):
    p = OllamaProvider(LlmSettings(), client_factory=lambda h, t: failing_client)
    p.warm_up()
    assert "ısındırma" in caplog.text.lower()
```

`tests/test_controller.py`:
```python
def test_warm_up_calls_stt_and_llm_warm_up(ctrl, fake_stt, fake_llm, qtbot):
    ready = []
    ctrl.ready_changed.connect(ready.append)
    ctrl.warm_up()
    qtbot.waitUntil(lambda: ready == [True])
    assert fake_stt.warmed and fake_llm.warmed


def test_warm_up_skips_llm_when_disabled(ctrl_llm_disabled, fake_llm, qtbot):
    ctrl_llm_disabled.warm_up()
    qtbot.wait(50)
    assert not fake_llm.warmed
```

- [ ] **Adım 2: Çalıştır, başarısız gör**
- [ ] **Adım 3: Uygula**

`engine.py`:
```python
WARM_UP_SECONDS = 1.0

    def warm_up(self) -> None:
        """Modeli yükler ve ilk gerçek isteğin yavaş olmaması için kısa bir çözümleme yapar."""
        if not self.is_loaded:
            self.load()
        if not self._settings.warm_up:
            return
        rng = np.random.default_rng(0)
        audio = (rng.standard_normal(int(SAMPLE_RATE * WARM_UP_SECONDS)) * 0.01).astype(np.float32)
        try:
            with self._lock:
                seg_iter, _ = self._model.transcribe(
                    audio, language=self._settings.language, beam_size=1, vad_filter=False
                )
                list(seg_iter)
        except Exception as exc:  # noqa: BLE001 - ısınma hatası uygulamayı durdurmamalı
            log.warning("STT ısınma çözümlemesi başarısız: %s", exc)
```

`ollama_provider.py`:
```python
    def warm_up(self) -> None:
        try:
            self._client.chat(model=self._settings.model, messages=[], keep_alive=self._settings.keep_alive)
            log.info("Ollama modeli ısındırıldı: %s", self._settings.model)
        except Exception as exc:  # noqa: BLE001 - ısındırma isteğe bağlı
            log.warning("Ollama ısındırma başarısız: %s", exc)
```

`controller.py`:
```python
    @Slot()
    def warm_up(self) -> None:
        self._jobs.append(run_in_pool(
            self._stt.warm_up,
            lambda _: self.ready_changed.emit(True),
            lambda e: self.error.emit(f"STT modeli yüklenemedi: {e}"),
            self._pool))
        warm = getattr(self._llm, "warm_up", None)
        if self._settings.llm.enabled and self._settings.llm.prewarm and warm is not None:
            self._jobs.append(run_in_pool(warm, lambda _: None,
                                          lambda e: log.warning("LLM ısındırma: %s", e), self._pool))
```
`set_llm` sonrası (ayar değişince) yeni sağlayıcı da ısındırılır: `_open_settings` içinde `ctx.controller.prewarm_llm()` (aynı gövdenin ikinci yarısı, ayrı metot).

- [ ] **Adım 4: Testler + ruff**
- [ ] **Adım 5: Commit** — `perf: STT ve Ollama ısınması (ilk diktede gecikme kalkar)`

---

### T4: Panoya kopyala + aktif pencereye yapıştır + öne getirme ayarı

**Amaç:** RESULT'a geçince düzeltilmiş metin **her zaman panoya** yazılır (ayar, varsayılan açık). Ayar açıksa ve ön plandaki pencere Dikte değilse, panodaki metin **Ctrl+V** ile aktif pencereye yapıştırılır. Pencerenin öne gelmesi ayrı ayar (varsayılan **kapalı** — dikte akışını bozmasın). Geçmiş kaydı zaten yapılıyor (kullanıcının "log" isteği = geçmiş, T5).

**Files:**
- Create: `src/dikte/platform/paste.py`
- Modify: `src/dikte/config.py` (`auto_copy`, `auto_paste`, `raise_window_on_result`)
- Modify: `src/dikte/core/controller.py` (`result_ready = Signal(str)`)
- Modify: `src/dikte/app.py` (`_on_result_ready`), `src/dikte/ui/result_window.py` (`on_state` öne getirme koşulu)
- Test: yeni `tests/test_paste.py`, `tests/test_app_wiring.py`, `tests/test_ui_result_window.py`

**Interfaces:**
- Produces: `paste.py`
  ```python
  def foreground_window_id() -> int | None   # Windows: GetForegroundWindow; Linux: None
  def send_paste_keystroke(sender: Callable[[], None] | None = None) -> bool  # True = gönderildi
  def paste_active_window(own_win_ids: set[int], sender=None) -> bool  # kendi penceresiyse False
  ```
  Windows: `ctypes.windll.user32.GetForegroundWindow()`, `keybd_event(VK_CONTROL)`, `keybd_event(0x56)`.
  Linux: `shutil.which("xdotool")` → `xdotool key --clearmodifiers ctrl+v`; yoksa `wtype -M ctrl v -m ctrl`; ikisi de yoksa False + bir kez log.
- Produces: `DictationController.result_ready = Signal(str)` — `_set_state(RESULT)` **sonrasında** düzeltilmiş metinle yayılır (LLM kapalıyken ham metin)
- Produces: `Settings.auto_copy: bool = True`, `Settings.auto_paste: bool = True`, `Settings.raise_window_on_result: bool = False`

- [ ] **Adım 1: Başarısız testler**

`tests/test_paste.py`:
```python
from dikte.platform import paste

def test_paste_skips_when_foreground_is_own_window(monkeypatch):
    monkeypatch.setattr(paste, "foreground_window_id", lambda: 42)
    sent = []
    assert paste.paste_active_window({42}, sender=lambda: sent.append(1)) is False
    assert sent == []

def test_paste_sends_keystroke_when_foreground_is_other_window(monkeypatch):
    monkeypatch.setattr(paste, "foreground_window_id", lambda: 7)
    sent = []
    assert paste.paste_active_window({42}, sender=lambda: sent.append(1)) is True
    assert sent == [1]

def test_linux_sender_prefers_xdotool(monkeypatch):
    monkeypatch.setattr(paste.sys, "platform", "linux")
    monkeypatch.setattr(paste.shutil, "which", lambda n: "/usr/bin/xdotool" if n == "xdotool" else None)
    ran = []
    monkeypatch.setattr(paste.subprocess, "run", lambda cmd, **k: ran.append(cmd))
    paste.send_paste_keystroke()
    assert ran and ran[0][0] == "/usr/bin/xdotool"

def test_linux_without_tools_returns_false(monkeypatch, caplog):
    monkeypatch.setattr(paste.sys, "platform", "linux")
    monkeypatch.setattr(paste.shutil, "which", lambda n: None)
    assert paste.send_paste_keystroke() is False
    assert "xdotool" in caplog.text
```

`tests/test_app_wiring.py`:
```python
def test_result_ready_copies_to_clipboard_and_pastes(ctx, monkeypatch, qtbot):
    pasted = []
    monkeypatch.setattr(app_mod, "paste_active_window", lambda ids, **k: pasted.append(ids) or True)
    ctx.controller._update_session(raw_text="a", corrected_text="Merhaba.")
    ctx.controller.state_changed.emit(DictationState.RESULT)
    ctx.controller.result_ready.emit("Merhaba.")
    assert QApplication.clipboard().text() == "Merhaba."
    assert len(pasted) == 1

def test_result_ready_respects_auto_paste_off(ctx, monkeypatch):
    ctx.settings = ctx.settings.model_copy(update={"auto_paste": False})
    pasted = []
    monkeypatch.setattr(app_mod, "paste_active_window", lambda *a, **k: pasted.append(1))
    ctx.controller.result_ready.emit("x")
    assert pasted == []
```

`tests/test_ui_result_window.py`:
```python
def test_window_not_raised_on_result_by_default(qtbot, window_with_fake_controller):
    w = window_with_fake_controller
    w.hide()
    w.on_state(DictationState.RESULT)
    assert not w.isVisible()

def test_window_raised_when_setting_enabled(qtbot, window_with_fake_controller):
    w = window_with_fake_controller
    w.raise_on_result = True
    w.hide()
    w.on_state(DictationState.RESULT)
    assert w.isVisible()
```

`tests/test_controller.py`:
```python
def test_result_ready_emitted_after_result_state(ctrl_llm_disabled, fake_stt, qtbot):
    order = []
    ctrl_llm_disabled.state_changed.connect(lambda s: order.append(("state", s)))
    ctrl_llm_disabled.result_ready.connect(lambda t: order.append(("text", t)))
    ctrl_llm_disabled.toggle(); ctrl_llm_disabled.toggle()
    qtbot.waitUntil(lambda: ("text", "merhaba dünya") in order)
    assert order.index(("state", DictationState.RESULT)) < order.index(("text", "merhaba dünya"))
```

- [ ] **Adım 2: Çalıştır, başarısız gör**
- [ ] **Adım 3: Uygula**

`platform/paste.py`:
```python
from __future__ import annotations
import logging, shutil, subprocess, sys
from collections.abc import Callable

log = logging.getLogger(__name__)
VK_CONTROL, VK_V, KEYEVENTF_KEYUP = 0x11, 0x56, 0x0002
_warned = {"tools": False}

def foreground_window_id() -> int | None:
    if sys.platform == "win32":
        import ctypes
        return int(ctypes.windll.user32.GetForegroundWindow())
    return None  # Linux'ta güvenilir ve taşınabilir bir yol yok; kendi penceremiz odaktaysa Qt üzerinden bakılır

def _send_windows() -> bool:
    import ctypes
    u = ctypes.windll.user32
    u.keybd_event(VK_CONTROL, 0, 0, 0); u.keybd_event(VK_V, 0, 0, 0)
    u.keybd_event(VK_V, 0, KEYEVENTF_KEYUP, 0); u.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)
    return True

def _send_linux() -> bool:
    if (x := shutil.which("xdotool")):
        subprocess.run([x, "key", "--clearmodifiers", "ctrl+v"], check=False, timeout=3); return True
    if (w := shutil.which("wtype")):
        subprocess.run([w, "-M", "ctrl", "v", "-m", "ctrl"], check=False, timeout=3); return True
    if not _warned["tools"]:
        log.warning("otomatik yapıştırma için xdotool (X11) veya wtype (Wayland) gerekli; metin panoda")
        _warned["tools"] = True
    return False

def send_paste_keystroke(sender: Callable[[], bool] | None = None) -> bool:
    if sender is not None:
        sender(); return True
    try:
        return _send_windows() if sys.platform == "win32" else _send_linux()
    except (OSError, subprocess.SubprocessError) as exc:
        log.error("yapıştırma tuşu gönderilemedi: %s", exc); return False

def paste_active_window(own_win_ids: set[int], sender=None) -> bool:
    fg = foreground_window_id()
    if fg is not None and fg in own_win_ids:
        return False
    return send_paste_keystroke(sender)
```

`controller.py`: `result_ready = Signal(str)`; `_on_corrected` ve LLM-kapalı dalında `_set_state(RESULT)` **sonrasında** `self.result_ready.emit(self._session.corrected_text)`; `_on_llm_error` dalında da (ham metin).

`app.py`:
```python
def _on_result_ready(ctx: AppContext, text: str) -> None:
    if not text or not ctx.settings.auto_copy:
        return
    QApplication.clipboard().setText(text)
    if ctx.settings.auto_paste and not ctx.window.isActiveWindow():
        own = {int(ctx.window.winId()), int(ctx.overlay.winId())}
        if not paste_active_window(own):
            log.info("yapıştırma atlandı; metin panoda")
```
`_wire`: `c.result_ready.connect(lambda t: _on_result_ready(ctx, t))`. `_open_settings`: `ctx.window.raise_on_result = new.raise_window_on_result`.

`result_window.py`: `self.raise_on_result = False`; `on_state` RESULT dalı `if self.raise_on_result:` ile sarılır; `bind(..., raise_on_result=False)`.

`settings_dialog.py`: üç `QCheckBox` (T6'da "Genel" sekmesine gider): "Sonucu panoya kopyala", "Sonucu aktif pencereye yapıştır (Ctrl+V)", "Sonuçta pencereyi öne getir".

- [ ] **Adım 4: Testler + ruff**
- [ ] **Adım 5: README "Nasıl çalışır" bölümü: pano + yapıştırma; Linux için `xdotool`/`wtype` kurulum satırı `packaging/linux/install.sh`'a ipucu olarak (paket kurmadan, sadece uyarı).**
- [ ] **Adım 6: Commit** — `feat: sonuç panoya kopyalanır ve aktif pencereye yapıştırılır; pencere öne getirme ayarı`

---

### T5: Geçmiş paneli, araç çubuğu, durum çubuğu, özdeş değişiklik filtresi

**Amaç:** Ana pencereye araç çubuğu (Kaydet/Durdur, Vazgeç, Geçmiş, Ayarlar) ve sağda kapanabilir **Geçmiş** dock'u. Geçmişte arama, tıkla-yükle, kopyala, sil, tümünü temizle. Durum çubuğunda model/hassasiyet/LLM/süre/kelime. `x → x` değişiklikler gizlenir.

**Files:**
- Create: `src/dikte/ui/history_panel.py`
- Modify: `src/dikte/core/history.py` (`delete`, `clear`, `changed` bildirimi için `QObject` değil — panel yeniden `load()` eder)
- Modify: `src/dikte/ui/result_window.py`, `src/dikte/app.py`
- Test: yeni `tests/test_history_panel.py`, `tests/test_history.py`, `tests/test_ui_result_window.py`, `tests/test_app_wiring.py`

**Interfaces:**
- Produces: `History.delete(session_id: str) -> None`, `History.clear() -> None`
- Produces: `HistoryPanel(QDockWidget)`: `set_sessions(tuple[Session, ...])`, `session_selected = Signal(object)`, `delete_requested = Signal(str)`, `clear_requested = Signal()`, `search_edit: QLineEdit`, `list_widget: QListWidget`
- Produces: `ResultWindow.history_panel`, `ResultWindow.toolbar` eylemleri: `record_action`, `cancel_action`, `history_action` (checkable), `settings_action`; sinyaller `record_requested`, `cancel_requested`, `settings_requested`
- Produces: `ResultWindow.set_status_info(model: str, compute: str, llm: str)`; `on_session` süre/kelime sayısını durum çubuğuna yazar
- Produces: `ResultWindow.load_session(s: Session)` (geçmişten yükleme; `_pending` sıfırlanır)

- [ ] **Adım 1: Başarısız testler**

`tests/test_history.py`:
```python
def test_delete_removes_only_that_session(tmp_path):
    h = History(tmp_path / "h.jsonl", 10)
    a, b = Session(raw_text="a"), Session(raw_text="b")
    h.append(a); h.append(b)
    h.delete(a.id)
    assert [s.id for s in h.load()] == [b.id]

def test_clear_empties_file(tmp_path):
    h = History(tmp_path / "h.jsonl", 10)
    h.append(Session(raw_text="a")); h.clear()
    assert h.load() == ()
```

`tests/test_history_panel.py`:
```python
def test_panel_lists_sessions_newest_first(qtbot):
    p = HistoryPanel(); qtbot.addWidget(p)
    old = Session(raw_text="eski", corrected_text="Eski.")
    new = Session(raw_text="yeni", corrected_text="Yeni.")
    p.set_sessions((old, new))
    assert p.list_widget.item(0).text().endswith("Yeni.")

def test_search_filters_by_text(qtbot):
    p = HistoryPanel(); qtbot.addWidget(p)
    p.set_sessions((Session(corrected_text="Docker port çakışması"), Session(corrected_text="Toplantı 15:00")))
    p.search_edit.setText("docker")
    visible = [p.list_widget.item(i) for i in range(p.list_widget.count()) if not p.list_widget.item(i).isHidden()]
    assert len(visible) == 1

def test_clicking_item_emits_session(qtbot):
    p = HistoryPanel(); qtbot.addWidget(p)
    s = Session(corrected_text="X"); p.set_sessions((s,))
    got = []; p.session_selected.connect(got.append)
    p.list_widget.setCurrentRow(0); p.list_widget.itemActivated.emit(p.list_widget.item(0))
    assert got == [s]

def test_delete_emits_id(qtbot):
    p = HistoryPanel(); qtbot.addWidget(p)
    s = Session(corrected_text="X"); p.set_sessions((s,))
    got = []; p.delete_requested.connect(got.append)
    p.list_widget.setCurrentRow(0); p.delete_btn.click()
    assert got == [s.id]
```

`tests/test_ui_result_window.py`:
```python
def test_identical_changes_are_hidden(qtbot, window):
    window.on_session(Session(changes=(Change("a", "a", "noktalama"), Change("promt", "prompt", "yazım"))))
    assert window.changes_list.count() == 1

def test_status_bar_shows_duration_and_word_count(qtbot, window):
    window.on_session(Session(corrected_text="bir iki üç", duration_s=12.4))
    assert "12 sn" in window.statusBar().currentMessage() and "3 kelime" in window.statusBar().currentMessage()

def test_history_action_toggles_dock(qtbot, window):
    window.history_action.trigger()
    assert window.history_panel.isVisible()

def test_load_session_fills_panes_and_clears_pending(qtbot, window):
    window._pending = "translation"
    window.load_session(Session(raw_text="h", corrected_text="D", translation="T"))
    assert window.corrected_pane.text() == "D" and window.output_pane.text() == "T" and window._pending is None
```

`tests/test_app_wiring.py`:
```python
def test_history_panel_refreshes_on_result(ctx):
    ctx.controller._update_session(raw_text="a", corrected_text="A.")
    ctx.controller.state_changed.emit(DictationState.RESULT)
    assert ctx.window.history_panel.list_widget.count() == 1

def test_history_delete_flows_to_storage(ctx):
    ctx.controller._update_session(corrected_text="A.")
    ctx.controller.state_changed.emit(DictationState.RESULT)
    sid = ctx.history.load()[0].id
    ctx.window.history_panel.delete_requested.emit(sid)
    assert ctx.history.load() == ()

def test_status_info_set_when_ready(ctx):
    ctx.stt._compute_type = "float16"
    ctx.controller.ready_changed.emit(True)
    assert "float16" in ctx.window.statusBar().currentMessage() or "float16" in ctx.window._status_info.text()
```

- [ ] **Adım 2: Çalıştır, başarısız gör**
- [ ] **Adım 3: Uygula**

`history.py`:
```python
    def delete(self, session_id: str) -> None:
        kept = tuple(s for s in self.load() if s.id != session_id)
        self._write(kept)

    def clear(self) -> None:
        self._write(())

    def _write(self, sessions: tuple[Session, ...]) -> None:
        content = "".join(_to_json(s) + "\n" for s in sessions)
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(content, encoding="utf-8")
        tmp.replace(self._path)
```
(`append` de `_write` kullanacak şekilde sadeleştirilir.)

`ui/history_panel.py` (iskelet):
```python
class HistoryPanel(QDockWidget):
    session_selected = Signal(object)
    delete_requested = Signal(str)
    clear_requested = Signal()

    def __init__(self, parent=None):
        super().__init__("Geçmiş", parent)
        self._sessions: tuple[Session, ...] = ()
        self.search_edit = QLineEdit(); self.search_edit.setPlaceholderText("Ara…")
        self.list_widget = QListWidget()
        self.copy_btn, self.delete_btn, self.clear_btn = QPushButton("Kopyala"), QPushButton("Sil"), QPushButton("Tümünü temizle")
        ...  # dikey yerleşim: arama, liste, düğme satırı
        self.search_edit.textChanged.connect(self._filter)
        self.list_widget.itemActivated.connect(lambda it: self.session_selected.emit(it.data(Qt.UserRole)))
        self.list_widget.itemClicked.connect(lambda it: self.session_selected.emit(it.data(Qt.UserRole)))
        self.delete_btn.clicked.connect(self._delete_current)
        self.copy_btn.clicked.connect(self._copy_current)
        self.clear_btn.clicked.connect(self._confirm_clear)

    def set_sessions(self, sessions: tuple[Session, ...]) -> None:
        self._sessions = tuple(reversed(sessions))  # en yeni üstte
        self.list_widget.clear()
        for s in self._sessions:
            preview = (s.corrected_text or s.raw_text).replace("\n", " ")[:80]
            it = QListWidgetItem(f"{s.created_at:%d.%m %H:%M}  {preview}")
            it.setData(Qt.UserRole, s); it.setToolTip(s.corrected_text)
            self.list_widget.addItem(it)
        self._filter(self.search_edit.text())

    def _filter(self, needle: str) -> None:
        n = needle.casefold()
        for i in range(self.list_widget.count()):
            it = self.list_widget.item(i); s = it.data(Qt.UserRole)
            it.setHidden(bool(n) and n not in (s.corrected_text + s.raw_text).casefold())
```
`_confirm_clear`: `QMessageBox.question` "Tüm geçmiş silinsin mi?" → `clear_requested`.

`result_window.py`: `QToolBar("Ana")` ile `record_action` (metni duruma göre "Kaydet"/"Durdur"), `cancel_action`, `history_action` (checkable, dock görünürlüğüne bağlı), `settings_action`. `self.history_panel = HistoryPanel(self)`; `addDockWidget(Qt.RightDockWidgetArea, ...)`; başlangıçta gizli. Durum çubuğu: sağa kalıcı `self._status_info = QLabel()` (`set_status_info` yazar), sol mesaj `f"{int(round(s.duration_s))} sn · {len(s.corrected_text.split())} kelime"`. `on_session` içinde `if c.original.strip() == c.replacement.strip(): continue`.

`app.py` `_wire`:
```python
    c.state_changed.connect(lambda s: s is DictationState.RESULT and _refresh_history(ctx))
    ctx.window.history_panel.session_selected.connect(ctx.window.load_session)
    ctx.window.history_panel.delete_requested.connect(lambda sid: (ctx.history.delete(sid), _refresh_history(ctx)))
    ctx.window.history_panel.clear_requested.connect(lambda: (ctx.history.clear(), _refresh_history(ctx)))
    ctx.window.record_requested.connect(c.toggle); ctx.window.cancel_requested.connect(c.cancel)
    ctx.window.settings_requested.connect(lambda: _open_settings(ctx))
    c.state_changed.connect(ctx.window.on_state)  # araç çubuğu metni
    c.ready_changed.connect(lambda r: r and ctx.window.set_status_info(
        ctx.settings.stt.model, ctx.stt.compute_type,
        ctx.settings.llm.model if ctx.settings.llm.enabled else "LLM kapalı"))
```
`_refresh_history(ctx)`: `ctx.window.history_panel.set_sessions(ctx.history.load())`; `build_app` sonunda bir kez çağrılır.

- [ ] **Adım 4: Testler + ruff**
- [ ] **Adım 5: `docs/manual_test_checklist.md` "Geçmiş" bölümü (arama, yükle, sil, temizle, 200 sınırı).**
- [ ] **Adım 6: Commit** — `feat: geçmiş paneli, araç çubuğu ve durum çubuğu; özdeş değişiklikler gizlenir`

---

### T6: Sekmeli ayarlar, eksik alanlar, kısayol yakalama, B1

**Amaç:** `SettingsDialog` → `QTabWidget`, sekmeler ayrı dosyalarda: **Genel · Ses · Konuşma Tanıma · Metin Düzeltme · Gelişmiş · Hakkında**. Tüm ayar alanları arayüzde. `QKeySequenceEdit` ile kısayol. Yeniden başlatma isteyen alanların yanında ⓘ. Geçersiz kısayolla açılış çökmesi (B1) giderilir.

**Files:**
- Create: `src/dikte/ui/settings/__init__.py`, `general_tab.py`, `audio_tab.py`, `stt_tab.py`, `llm_tab.py`, `advanced_tab.py`, `about_tab.py`
- Modify: `src/dikte/ui/settings_dialog.py` (kabuk: sekmeler + doğrulama + `result_settings`), `src/dikte/app.py` (B1), `src/dikte/platform/hotkey_parse.py` (`QKeySequence` ↔ spec dönüşümü)
- Test: `tests/test_settings_dialog.py` (mevcut testler **korunur**; widget adları aynı kalır: `hotkey_edit`, `device_combo`, `stt_model_edit`, `compute_combo`, `llm_enabled_check`, `provider_combo`, `llm_model_edit`, `ollama_host_edit`, `keep_alive_edit`, `batch_check`, `batch_threshold_spin`, `autostart_check`, `close_after_copy_check`, `history_spin`, `error_label` — sekme nesnelerinden diyaloğa **özellik olarak** yansıtılır), yeni `tests/test_settings_tabs.py`, `tests/test_app_wiring.py`, `tests/test_hotkey_parse.py`

**Interfaces:**
- Produces: her sekme `class XTab(QWidget)` ile `def __init__(self, settings: Settings, ...)`, `def validate(self) -> str | None` (hata metni), `def apply(self, s: Settings) -> Settings` (yeni kopya döner)
- Produces: `SettingsDialog.tabs: QTabWidget`; `result_settings()` = `reduce(lambda s, t: t.apply(s), tabs, self._settings)`
- Produces: `hotkey_parse.to_key_sequence(spec) -> QKeySequence`, `from_key_sequence(seq) -> str`
- Produces: `app.py: _safe_hotkey(settings) -> Settings` — geçersizse varsayılana düşer, `log.error` + tepsi bildirimi

- [ ] **Adım 1: Başarısız testler** — `tests/test_settings_tabs.py`:
```python
def test_dialog_has_six_tabs(qtbot):
    d = SettingsDialog(Settings(), ()); qtbot.addWidget(d)
    assert [d.tabs.tabText(i) for i in range(d.tabs.count())] == [
        "Genel", "Ses", "Konuşma Tanıma", "Metin Düzeltme", "Gelişmiş", "Hakkında"]

def test_advanced_fields_round_trip(qtbot):
    d = SettingsDialog(Settings(), ()); qtbot.addWidget(d)
    d.beam_spin.setValue(2); d.vad_check.setChecked(False); d.initial_prompt_edit.setPlainText("X")
    d.num_ctx_spin.setValue(4096); d.top_p_spin.setValue(0.9); d.top_k_spin.setValue(40)
    d.timeout_spin.setValue(60); d.think_check.setChecked(True)
    s = d.result_settings()
    assert (s.stt.beam_size, s.stt.vad_filter, s.stt.initial_prompt) == (2, False, "X")
    assert (s.llm.num_ctx, s.llm.top_p, s.llm.top_k, s.llm.timeout_s, s.llm.think) == (4096, 0.9, 40, 60.0, True)

def test_hotkey_capture_writes_spec(qtbot):
    d = SettingsDialog(Settings(), ()); qtbot.addWidget(d)
    d.hotkey_edit.setKeySequence(QKeySequence("Ctrl+Shift+D"))
    assert d.result_settings().hotkey == "ctrl+shift+d"

def test_provider_groups_follow_selection(qtbot):
    d = SettingsDialog(Settings(), ()); qtbot.addWidget(d)
    d.provider_combo.setCurrentText("anthropic")
    assert not d.ollama_group.isVisibleTo(d) and d.anthropic_group.isVisibleTo(d)

def test_restart_hint_present_on_stt_model(qtbot):
    d = SettingsDialog(Settings(), ()); qtbot.addWidget(d)
    assert "yeniden başlat" in d.stt_model_edit.toolTip().lower()

def test_max_seconds_special_text(qtbot):
    d = SettingsDialog(Settings(), ()); qtbot.addWidget(d)
    assert d.max_seconds_spin.specialValueText() == "Sınırsız"
```
`tests/test_hotkey_parse.py`: `to_key_sequence("ctrl+alt+space").toString() == "Ctrl+Alt+Space"`, `from_key_sequence(QKeySequence("Ctrl+Shift+D")) == "ctrl+shift+d"`, `from_key_sequence(QKeySequence("Meta+X"))` → `HotkeyParseError` (Win tuşu desteklenmiyorsa) veya `win+x` (parse destekliyorsa; mevcut `parse_hotkey`'e bak).
`tests/test_app_wiring.py`:
```python
def test_invalid_hotkey_in_config_falls_back(monkeypatch, qtbot, tmp_path):
    monkeypatch.setattr(app_mod.paths, "history_path", lambda: tmp_path / "h.jsonl")
    bad = Settings(hotkey="ctrl+")
    ctx = app_mod.build_app(bad)
    assert ctx.settings.hotkey == Settings().hotkey
```
Mevcut `tests/test_settings_dialog.py` testleri **değişmeden** geçmeli (widget adları korunur). `hotkey_edit` artık `QKeySequenceEdit`; mevcut testte `hotkey_edit.setText(...)` varsa `setKeySequence` ile güncellenir — bu tek istisna.

- [ ] **Adım 2: Çalıştır, başarısız gör**
- [ ] **Adım 3: Uygula** — her sekme kendi `QFormLayout`'u; `SettingsDialog.__init__` sekmeleri kurar, eski widget adlarını `self.hotkey_edit = self.general.hotkey_edit` şeklinde yansıtır. `accept()` her sekmenin `validate()`'ini sırayla çağırır; ilk hata `error_label`'a yazılır ve o sekmeye geçilir (`tabs.setCurrentWidget`). `apply` zinciri `model_copy(update=...)` ile. `hotkey_parse.py`:
```python
_QT_MODS = {"ctrl": Qt.ControlModifier, "alt": Qt.AltModifier, "shift": Qt.ShiftModifier}
def to_key_sequence(spec: str) -> QKeySequence: ...  # parse_hotkey ile doğrula, "Ctrl+Alt+Space" üret
def from_key_sequence(seq: QKeySequence) -> str:
    text = seq.toString(QKeySequence.PortableText).lower()  # "ctrl+shift+d"
    parse_hotkey(text)  # geçersizse HotkeyParseError
    return text
```
`app.py`:
```python
def _safe_hotkey(settings: Settings) -> Settings:
    try:
        parse_hotkey(settings.hotkey); return settings
    except HotkeyParseError as exc:
        log.error("config'teki kısayol geçersiz (%s): %s; varsayılana dönülüyor", settings.hotkey, exc)
        return settings.model_copy(update={"hotkey": Settings().hotkey})
```
`build_app` başında `settings = _safe_hotkey(settings)`; `main` içinde düzeltme olduysa `save_settings` + tepsi bildirimi.
"Hakkında" sekmesi: `APP_NAME`, `__version__`, Python, PySide6, faster-whisper, ctranslate2 sürümleri (`importlib.metadata.version`), GPU adı/desteklenen compute_type'lar (`ctx.stt` üzerinden; GPU'suz testte "bilinmiyor"), "Log dosyasını aç" / "Config klasörünü aç" (`QDesktopServices.openUrl`).
"Ses" sekmesi: mikrofon combo + canlı seviye `QProgressBar` (diyalog açıkken geçici `AudioRecorder` başlatılır, `level_changed` → bar; kapanınca durdurulur; testte `stream_factory` sahte).
"Metin Düzeltme": `ollama_group`, `anthropic_group` (`QGroupBox`), sağlayıcıya göre görünürlük; "Bağlantıyı test et" düğmesi `run_in_pool` ile `provider.complete("Yanıt: OK", "OK")` çağırır, sonucu etikette gösterir. T7 bu sekmeye `openai_group`, `gemini_group`, `custom_group` ekler.

- [ ] **Adım 4: Testler + ruff**
- [ ] **Adım 5: README "Ayarlar" tablosu sekme başlıklarına göre yeniden düzenlenir.**
- [ ] **Adım 6: Commit** — `feat: sekmeli ayarlar, tüm alanlar arayüzde, kısayol yakalama; geçersiz kısayolla açılış çökmesi giderildi`

---

### T7: Sağlayıcılar — OpenAI-uyumlu, Gemini, Custom (format seçimli)

**Amaç:** `provider ∈ {ollama, openai, anthropic, gemini, custom}`. `custom` = kullanıcı uç noktası; `custom_format ∈ {openai, anthropic}` seçimiyle aynı iki istemci sınıfı `base_url` ile kullanılır. Anahtarlar ortam değişkeninden; env **adı** ayarlanabilir (varsayılanlar: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, custom için kullanıcı girer; boş = anahtarsız yerel sunucu).

Doğrulanmış API (Context7, 2026-09-14):
- OpenAI Python SDK: `OpenAI(base_url=..., api_key=...)`; `client.chat.completions.create(model, messages, temperature, response_format={"type": "json_schema", "json_schema": {"name": "correction", "schema": <şema>, "strict": False}})`. Şema desteklemeyen sunucuda `BadRequestError` → `{"type": "json_object"}` + şema promptu ile bir kez yeniden dene.
- Gemini (`google-genai`): `genai.Client(api_key=...)`; `client.models.generate_content(model, contents=user, config=types.GenerateContentConfig(system_instruction=system, temperature=..., response_mime_type="application/json", response_json_schema=<düz JSON şema>))`; `response.text`.
- Anthropic SDK: `Anthropic(api_key=..., base_url=..., timeout=...)` (`base_url` yalnızca custom'da verilir).

**Files:**
- Create: `src/dikte/llm/openai_provider.py`, `src/dikte/llm/gemini_provider.py`, `src/dikte/llm/keys.py`
- Modify: `src/dikte/llm/anthropic_provider.py` (`base_url`, `api_key_env`), `src/dikte/llm/__init__.py` (`make_provider`), `src/dikte/config.py`, `src/dikte/ui/settings/llm_tab.py`, `pyproject.toml` (`openai = ["openai>=2"]`, `gemini = ["google-genai>=1.30"]`), `.github/workflows/ci.yml` (extras ile kurulum: `-e ".[dev,anthropic,openai,gemini]"`)
- Test: yeni `tests/test_openai_provider.py`, `tests/test_gemini_provider.py`, `tests/test_keys.py`; `tests/test_anthropic_provider.py`, `tests/test_config.py`, `tests/test_llm_factory.py` (yeni), `tests/test_settings_tabs.py`

**Interfaces:**
- Produces (`config.py`):
  ```python
  class LlmSettings(BaseModel):
      enabled: bool = True
      prewarm: bool = True
      provider: Literal["ollama", "openai", "anthropic", "gemini", "custom"] = "ollama"
      model: str = "qwen3.5:4b"                      # Ollama modeli (T9 sonucu güncellenir)
      ollama_host: str = "http://127.0.0.1:11434"
      keep_alive: str = "30m"
      openai_model: str = "gpt-5.5"
      openai_api_key_env: str = "OPENAI_API_KEY"
      anthropic_model: str = "claude-sonnet-5"
      anthropic_api_key_env: str = "ANTHROPIC_API_KEY"
      gemini_model: str = "gemini-3.5-flash"
      gemini_api_key_env: str = "GEMINI_API_KEY"
      custom_format: Literal["openai", "anthropic"] = "openai"
      custom_base_url: str = ""
      custom_model: str = ""
      custom_api_key_env: str = ""                   # boş = anahtar gönderilmez (yerel sunucu)
      timeout_s: float = Field(default=120.0, gt=0)
      think: bool = False
      num_ctx: int = Field(default=8192, ge=2048)
      top_p: float = 0.8
      top_k: int = 20
  ```
  Model adı varsayılanları **agent tarafından çalıştırma anında** sağlayıcı dokümanlarından doğrulanır (Context7: `/openai/openai-python`, `/googleapis/python-genai`, Anthropic modelleri: sistem bilgisi `claude-sonnet-5`). Eski config'ler geçerli kalır (tüm yeni alanlar varsayılanlı).
- Produces (`keys.py`): `def read_api_key(env_name: str, *, required: bool) -> str | None` — `required=True` ve boşsa `LlmError(f"{env_name} ortam değişkeni tanımlı değil")`; `def key_status(env_name) -> bool` (UI ✓/✗ için; değeri asla döndürmez/loglamaz).
- Produces: `OpenAiCompatProvider(settings, *, base_url, model, api_key_env, required_key, client_factory=None)`; `name = "openai"` / custom'da `"custom-openai"`; `warm_up` yok.
- Produces: `GeminiProvider(settings, client_factory=None)`; `name = "gemini"`.
- Produces: `AnthropicProvider(settings, *, base_url=None, model=None, api_key_env="ANTHROPIC_API_KEY", client_factory=None)`; `name = "anthropic"` / `"custom-anthropic"`.
- Produces: `make_provider` dalları:
  ```python
  if p == "custom":
      if not settings.custom_base_url or not settings.custom_model:
          raise LlmError("Özel sağlayıcı için base URL ve model adı gerekli")
      if settings.custom_format == "openai":
          return OpenAiCompatProvider(settings, base_url=settings.custom_base_url, model=settings.custom_model,
                                      api_key_env=settings.custom_api_key_env, required_key=False, name="custom-openai")
      return AnthropicProvider(settings, base_url=settings.custom_base_url, model=settings.custom_model,
                               api_key_env=settings.custom_api_key_env, name="custom-anthropic")
  ```

- [ ] **Adım 1: Başarısız testler**

`tests/test_keys.py`:
```python
def test_required_key_missing_raises(monkeypatch):
    monkeypatch.delenv("X_KEY", raising=False)
    with pytest.raises(LlmError, match="X_KEY"):
        read_api_key("X_KEY", required=True)

def test_optional_key_missing_returns_none(monkeypatch):
    monkeypatch.delenv("X_KEY", raising=False)
    assert read_api_key("X_KEY", required=False) is None

def test_empty_env_name_means_no_key():
    assert read_api_key("", required=False) is None

def test_key_status_never_exposes_value(monkeypatch):
    monkeypatch.setenv("X_KEY", "gizli")
    assert key_status("X_KEY") is True
```

`tests/test_openai_provider.py` (sahte istemci `chat.completions.create` çağrılarını kaydeder):
```python
def test_json_schema_passed_as_response_format(fake_openai):
    p = OpenAiCompatProvider(LlmSettings(), base_url="http://x/v1", model="m", api_key_env="", required_key=False,
                             client_factory=lambda **k: fake_openai)
    p.complete("s", "u", json_schema={"type": "object"})
    rf = fake_openai.calls[-1]["response_format"]
    assert rf["type"] == "json_schema" and rf["json_schema"]["schema"] == {"type": "object"}

def test_falls_back_to_json_object_when_schema_rejected(fake_openai_rejecting_schema):
    p = OpenAiCompatProvider(..., client_factory=lambda **k: fake_openai_rejecting_schema)
    out = p.complete("s", "u", json_schema={"type": "object"})
    assert fake_openai_rejecting_schema.calls[-1]["response_format"] == {"type": "json_object"}
    assert out.startswith("{")

def test_missing_required_key_raises(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(LlmError, match="OPENAI_API_KEY"):
        OpenAiCompatProvider(LlmSettings(), base_url="https://api.openai.com/v1", model="m",
                             api_key_env="OPENAI_API_KEY", required_key=True)

def test_base_url_forwarded_to_client(fake_openai_factory):
    OpenAiCompatProvider(..., base_url="http://localhost:1234/v1", client_factory=fake_openai_factory)
    assert fake_openai_factory.kwargs["base_url"] == "http://localhost:1234/v1"

def test_network_error_wrapped(fake_openai_failing):
    with pytest.raises(LlmError, match="OpenAI"):
        OpenAiCompatProvider(..., client_factory=lambda **k: fake_openai_failing).complete("s", "u")
```

`tests/test_gemini_provider.py`:
```python
def test_schema_goes_to_response_json_schema(fake_genai, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    p = GeminiProvider(LlmSettings(gemini_model="g"), client_factory=lambda api_key: fake_genai)
    p.complete("sys", "usr", json_schema={"type": "object"}, temperature=0.1)
    call = fake_genai.calls[-1]
    cfg = call["config"]
    assert call["model"] == "g" and call["contents"] == "usr"
    assert cfg["system_instruction"] == "sys" and cfg["response_mime_type"] == "application/json"
    assert cfg["response_json_schema"] == {"type": "object"} and cfg["temperature"] == 0.1

def test_plain_text_when_no_schema(fake_genai, monkeypatch):
    ...
    assert "response_mime_type" not in fake_genai.calls[-1]["config"]

def test_missing_key_raises(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(LlmError, match="GEMINI_API_KEY"):
        GeminiProvider(LlmSettings())

def test_empty_response_raises(fake_genai_empty, monkeypatch): ...
```
(Gemini sağlayıcısında `config` sahte istemciye **dict** olarak geçilir; gerçek istemcide `types.GenerateContentConfig(**cfg)` ile sarılır — böylece test `google-genai` kurulu olmadan çalışır.)

`tests/test_llm_factory.py`:
```python
@pytest.mark.parametrize("provider,expected", [("ollama", "ollama"), ("openai", "openai"), ("gemini", "gemini")])
def test_factory_builds_named_provider(provider, expected, monkeypatch, stub_sdks): ...

def test_custom_openai_format(monkeypatch, stub_sdks):
    s = LlmSettings(provider="custom", custom_format="openai", custom_base_url="http://h/v1", custom_model="m")
    assert make_provider(s).name == "custom-openai"

def test_custom_anthropic_format(monkeypatch, stub_sdks):
    s = LlmSettings(provider="custom", custom_format="anthropic", custom_base_url="http://h", custom_model="m")
    assert make_provider(s).name == "custom-anthropic"

def test_custom_requires_url_and_model():
    with pytest.raises(LlmError, match="base URL"):
        make_provider(LlmSettings(provider="custom"))

def test_missing_sdk_gives_install_hint(monkeypatch):
    monkeypatch.setitem(sys.modules, "openai", None)
    with pytest.raises(LlmError, match=r"\[openai\]"):
        make_provider(LlmSettings(provider="openai"))
```

`tests/test_settings_tabs.py` ekleri: `provider_combo` 5 seçenek; `custom` seçilince `custom_group` görünür, içinde `custom_format_combo` (openai/anthropic), `custom_base_url_edit`, `custom_model_edit`, `custom_key_env_edit`; her grup için `key_status_label` "✓ tanımlı"/"✗ yok"; uzak sağlayıcı seçilince `privacy_label` görünür ("Dikte metni dış servise gönderilir").

- [ ] **Adım 2: Çalıştır, başarısız gör**
- [ ] **Adım 3: Uygula** — `openai_provider.py`:
```python
def _default_client_factory(*, base_url: str, api_key: str | None, timeout: float):
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise LlmError('OpenAI SDK kurulu değil: uv pip install -e ".[openai]"') from exc
    return OpenAI(base_url=base_url, api_key=api_key or "sk-no-key", timeout=timeout)

class OpenAiCompatProvider:
    def __init__(self, settings, *, base_url, model, api_key_env, required_key, name="openai", client_factory=None):
        self.name = name
        self._settings, self._model = settings, model
        key = read_api_key(api_key_env, required=required_key)
        self._client = (client_factory or _default_client_factory)(base_url=base_url, api_key=key, timeout=settings.timeout_s)

    def complete(self, system, user, *, json_schema=None, temperature=0.2) -> str:
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        try:
            if json_schema is None:
                return self._text(self._create(messages, temperature, None))
            try:
                rf = {"type": "json_schema", "json_schema": {"name": "dikte", "schema": json_schema, "strict": False}}
                return self._text(self._create(messages, temperature, rf))
            except _schema_unsupported_errors() as exc:
                log.info("sunucu json_schema desteklemiyor (%s); json_object ile deneniyor", exc)
                messages[0]["content"] += "\n\nRespond ONLY with a JSON object matching this schema:\n" + json.dumps(json_schema)
                return self._text(self._create(messages, temperature, {"type": "json_object"}))
        except LlmError:
            raise
        except Exception as exc:  # noqa: BLE001 - SDK hata sınıfları isteğe bağlı bağımlılıkta
            log.exception("OpenAI-uyumlu istek başarısız")
            raise LlmError(f"OpenAI-uyumlu API hatası ({self._model}): {exc}") from exc
```
`_schema_unsupported_errors()` → `openai.BadRequestError` varsa onu, yoksa `(ValueError,)` döner (SDK'sız testler için). `_text`: `resp.choices[0].message.content`; boşsa `LlmError`.
`gemini_provider.py` benzer; `config` dict → gerçek fabrikada `types.GenerateContentConfig(**config)`.
`anthropic_provider.py`: `base_url`, `model`, `api_key_env` parametreleri; `read_api_key` kullanır; JSON ayıklama mantığı korunur (Anthropic yapılandırılmış çıktıya geçiş ayrı görev).
`llm_tab.py`: `QGroupBox` ×5, `provider_combo.currentTextChanged → _show_group`; `key_status_label`'lar `key_status(env)` ile; "Bağlantıyı test et" T6'daki mekanizma.
`docs/manual_test_checklist.md`: her sağlayıcı için 1 madde + custom için LM Studio (openai) ve bir Anthropic-uyumlu proxy örneği.

- [ ] **Adım 4: Testler + ruff; CI extras ile kurulum**
- [ ] **Adım 5: README "Uzak sağlayıcılar" bölümü: tablo (sağlayıcı · env adı · extra · örnek base URL) + gizlilik notu.**
- [ ] **Adım 6: Commit** — `feat: OpenAI-uyumlu, Gemini ve özel (openai/anthropic formatlı) LLM sağlayıcıları`

---

### T8: VAD ön-kontrolü, halüsinasyon filtresi, eşik ayarları

**Amaç:** (1) Kayıt tamamen sessizse (Silero VAD konuşma bulamazsa) Whisper **hiç çağrılmaz**; kullanıcıya "Konuşma algılanmadı" denir. (2) Whisper'a `no_speech_threshold`, `log_prob_threshold`, `hallucination_silence_threshold`, `without_timestamps=True` (kelime zamanı kullanılmıyor) geçilir. (3) Bilinen Türkçe halüsinasyon kalıpları segment bazında elenir. (4) VAD eşikleri ayarlanabilir.

Doğrulanmış (kurulu faster-whisper 1.2.1, `inspect.signature`): `VadOptions(threshold=0.5, neg_threshold=None, min_speech_duration_ms=0, max_speech_duration_s=inf, min_silence_duration_ms=2000, speech_pad_ms=400)`; `transcribe(..., vad_filter, vad_parameters, no_speech_threshold, log_prob_threshold, compression_ratio_threshold, hallucination_silence_threshold, without_timestamps, hotwords, ...)`; `faster_whisper.vad.get_speech_timestamps(audio, vad_options)` içe aktarılabilir (Silero ONNX, `onnxruntime` kurulu).

**Files:**
- Create: `src/dikte/stt/hallucinations.py`
- Modify: `src/dikte/config.py` (`SttSettings`), `src/dikte/stt/engine.py`, `src/dikte/stt/result.py` (`Segment.no_speech_prob`, `avg_logprob`), `src/dikte/ui/settings/stt_tab.py`
- Test: yeni `tests/test_hallucinations.py`; `tests/test_stt_engine.py`, `tests/test_config.py`, `tests/test_settings_tabs.py`

**Interfaces:**
- Produces (`config.py`):
  ```python
      vad_filter: bool = True
      vad_threshold: float = Field(default=0.5, ge=0.0, le=1.0)
      vad_min_silence_ms: int = Field(default=1000, ge=0)
      vad_speech_pad_ms: int = Field(default=300, ge=0)
      no_speech_threshold: float = Field(default=0.6, ge=0.0, le=1.0)
      log_prob_threshold: float = -1.0
      hallucination_silence_threshold_s: float = Field(default=2.0, ge=0)
      hallucination_filter: bool = True
  ```
- Produces (`hallucinations.py`):
  ```python
  KNOWN_PHRASES: tuple[str, ...] = ("altyazı m.k.", "altyazı mk", "altyazı", "izlediğiniz için teşekkürler",
      "izlediğiniz için teşekkür ederim", "abone olmayı unutmayın", "beni izlemeye devam edin",
      "bu videoyu beğendiyseniz", "kanalıma abone olun", "altyazı çevirmeni", "çeviri:", "subtitles by")
  def is_hallucination(text: str) -> bool  # normalize (casefold, noktalama sil) → tam eşleşme veya kısa (≤ 6 kelime) metinde kalıp içerme
  def filter_segments(segments: tuple[Segment, ...], *, no_speech_threshold: float) -> tuple[Segment, ...]
  ```
- Produces (`engine.py`): `FasterWhisperEngine(..., speech_probe: Callable[[np.ndarray, SttSettings], bool] | None = None)`; `_has_speech(audio) -> bool`; `transcribe` sessizlikte `SttError("Konuşma algılanmadı; mikrofon ve VAD eşiğini kontrol edin")` yükseltir (denetleyici zaten `error` + IDLE yapıyor).

- [ ] **Adım 1: Başarısız testler**

`tests/test_hallucinations.py`:
```python
@pytest.mark.parametrize("text", ["Altyazı M.K.", "altyazı m.k", "İzlediğiniz için teşekkürler.", "Abone olmayı unutmayın!"])
def test_known_phrases_detected(text):
    assert is_hallucination(text)

@pytest.mark.parametrize("text", ["Bugün toplantıda altyazı ekleme özelliğini konuştuk.", "Teşekkürler, raporu aldım."])
def test_real_sentences_kept(text):
    assert not is_hallucination(text)

def test_filter_drops_high_no_speech_prob():
    segs = (Segment(0, 1, "Merhaba", no_speech_prob=0.1), Segment(1, 2, "Altyazı M.K.", no_speech_prob=0.2),
            Segment(2, 3, "gürültü", no_speech_prob=0.95))
    assert [s.text for s in filter_segments(segs, no_speech_threshold=0.6)] == ["Merhaba"]
```

`tests/test_stt_engine.py`:
```python
def test_silent_audio_raises_without_calling_model(engine_with_fake_model):
    eng, fake = engine_with_fake_model
    eng._speech_probe = lambda audio, s: False
    with pytest.raises(SttError, match="Konuşma algılanmadı"):
        eng.transcribe(np.zeros(16_000, dtype=np.float32))
    assert fake.calls == 0

def test_transcribe_passes_vad_and_hallucination_kwargs(engine_with_fake_model):
    eng, fake = engine_with_fake_model
    eng._speech_probe = lambda audio, s: True
    eng.transcribe(np.ones(16_000, dtype=np.float32) * 0.1)
    kw = fake.last_kwargs
    assert kw["vad_parameters"] == {"threshold": 0.5, "min_silence_duration_ms": 1000, "speech_pad_ms": 300}
    assert kw["no_speech_threshold"] == 0.6 and kw["log_prob_threshold"] == -1.0
    assert kw["hallucination_silence_threshold"] == 2.0 and kw["without_timestamps"] is True

def test_hallucinated_segments_removed(engine_with_fake_model):
    eng, fake = engine_with_fake_model
    eng._speech_probe = lambda audio, s: True
    fake.segments = [FakeSeg(0, 1, "Merhaba dünya", 0.05, -0.3), FakeSeg(1, 2, "Altyazı M.K.", 0.3, -0.9)]
    assert eng.transcribe(np.ones(16_000, dtype=np.float32) * 0.1).text == "Merhaba dünya"

def test_filter_can_be_disabled(engine_factory):
    eng, fake = engine_factory(hallucination_filter=False)
    ...
    assert "Altyazı M.K." in eng.transcribe(...).text

@pytest.mark.gpu
def test_real_silero_probe_rejects_silence_and_accepts_tone():
    from dikte.stt.engine import _default_speech_probe
    s = SttSettings()
    assert _default_speech_probe(np.zeros(32_000, dtype=np.float32), s) is False
    # gerçek konuşma yerine: tests/data/tr_speech_2s.wav (T9'da eklenen kısa Türkçe örnek) → True
```

- [ ] **Adım 2: Çalıştır, başarısız gör**
- [ ] **Adım 3: Uygula** — `engine.py`:
```python
def _default_speech_probe(audio: np.ndarray, settings: SttSettings) -> bool:
    from faster_whisper.vad import VadOptions, get_speech_timestamps
    opts = VadOptions(threshold=settings.vad_threshold, min_silence_duration_ms=settings.vad_min_silence_ms,
                      speech_pad_ms=settings.vad_speech_pad_ms)
    return bool(get_speech_timestamps(audio, opts))

    def transcribe(self, audio, language=None):
        if audio.size == 0:
            raise SttError("Ses kaydı boş")
        if self._settings.vad_filter and not self._speech_probe(audio, self._settings):
            raise SttError("Konuşma algılanmadı; mikrofon ve VAD eşiğini kontrol edin")
        ...
        kwargs = {
            "language": lang, "task": "transcribe", "beam_size": ..., "initial_prompt": ...,
            "vad_filter": s.vad_filter,
            "vad_parameters": {"threshold": s.vad_threshold, "min_silence_duration_ms": s.vad_min_silence_ms,
                               "speech_pad_ms": s.vad_speech_pad_ms},
            "no_speech_threshold": s.no_speech_threshold,
            "log_prob_threshold": s.log_prob_threshold,
            "hallucination_silence_threshold": s.hallucination_silence_threshold_s or None,
            "without_timestamps": True,
        }
        ...
        segments = tuple(Segment(x.start, x.end, x.text.strip(),
                                 no_speech_prob=float(getattr(x, "no_speech_prob", 0.0)),
                                 avg_logprob=float(getattr(x, "avg_logprob", 0.0))) for x in seg_iter)
        if s.hallucination_filter:
            segments = filter_segments(segments, no_speech_threshold=s.no_speech_threshold)
```
`BatchedInferencePipeline.transcribe` `hallucination_silence_threshold` kabul etmiyorsa (imzayı `inspect` ile kontrol et; kabul etmiyorsa pipeline dalında bu anahtarı çıkar) — test: `test_batched_path_omits_unsupported_kwargs`.
`stt_tab.py`: "Sessizlik algılama (VAD)" grubu: `vad_check`, `vad_threshold_spin` (0.05 adım), `vad_min_silence_spin` (ms), `no_speech_spin`, `hallucination_filter_check`; tooltip'lerde "Altyazı M.K." örneği.

- [ ] **Adım 4: Testler + ruff**
- [ ] **Adım 5: README "Halüsinasyon ve sessizlik" bölümü: mekanizma + eşik önerileri (gürültülü ortam: threshold 0.6; yumuşak ses: 0.35).**
- [ ] **Adım 6: Commit** — `feat: Silero VAD ön-kontrolü, halüsinasyon filtresi ve ayarlanabilir eşikler`

---

### T9: Türkçe LLM düzeltme benchmark'ı ve varsayılan model seçimi

**Amaç:** 8 GB VRAM'e sığan **güncel** Ollama modellerini, bilerek yerleştirilmiş Türkçe STT hatalarıyla ve bağlama bağlı düzeltme gerektiren örneklerle 10 üzerinden puanlamak; en yüksek puanlı model `LlmSettings.model` varsayılanı olur. Sonuç `docs/llm_benchmark.md`'ye yazılır. Bu makinede çalışır (RTX 3060 Ti; Whisper ile birlikte yaşayacağı için ≤ ~5 GB model tercih).

**Files:**
- Create: `scripts/eval_data/tr_corrections.json`, `docs/llm_benchmark.md`
- Rewrite: `scripts/eval_llm.py`
- Modify: `src/dikte/config.py` (`LlmSettings.model` varsayılanı — **yalnızca benchmark sonucuna göre**), `README.md`, memory notu (`feedback-latest-local-models.md` güncellenir)
- Test: yeni `tests/test_eval_scoring.py` (puanlama saf fonksiyon; Ollama gerekmez)

**Interfaces:**
- Produces (`scripts/eval_llm.py`, içe aktarılabilir modül):
  ```python
  @dataclass(frozen=True)
  class Case:
      id: str
      category: Literal["yazim", "baglam", "teknik_koru", "noktalama", "anlam_koru", "bos_degisiklik"]
      raw: str
      must_contain: tuple[str, ...]      # düzeltilmiş metinde geçmeli
      must_not_contain: tuple[str, ...]  # geçmemeli (hatalı hâli / uydurma ekleme)
      max_change_ratio: float            # difflib.SequenceMatcher ile 1 - ratio ≤ bu değer (aşırı müdahale cezası)

  @dataclass(frozen=True)
  class CaseScore:
      case_id: str; passed_contains: int; total_contains: int; violations: tuple[str, ...]
      over_edited: bool; valid_json: bool; latency_s: float; score: float  # 0..1

  def score_case(case: Case, result: CorrectionResult | None, latency_s: float) -> CaseScore
  def aggregate(scores: tuple[CaseScore, ...]) -> dict  # {"score_10": float, "by_category": {...}, "avg_latency": ...}
  def run(models: tuple[str, ...], cases: tuple[Case, ...], provider_factory) -> dict[str, dict]
  def render_markdown(results: dict[str, dict]) -> str
  ```
  Puan: `score = 0.6*(passed/total) + 0.25*(1 if not violations else 0) + 0.15*(1 if not over_edited else 0)`; JSON geçersiz/hata → 0. `score_10 = 10 * ortalama(score)`. Gecikme puanı **etkilemez**, tabloda ayrı sütun (eşitlikte hızlı olan kazanır).

- [ ] **Adım 1: Veri seti** — `scripts/eval_data/tr_corrections.json`, **en az 40** örnek, kategori başına ≥ 6:
  - `yazim` (bilerek yerleştirilmiş fonetik hatalar): `"bugün hava çuk güzel"` → must_contain `["çok güzel"]`, must_not `["çuk"]`.
  - `baglam` (bağlam olmadan çözülemeyen): `"toplantıda karar verdik yarın sabah gel cek"` → `["gelecek"]`; `"dosyayı silmeden önce yedek al mayı unutma"` → `["almayı"]`; `"sunumu bitirince ışıkları yak"` (ışık/yak bağlamı, `"yak"` korunmalı, `"yaz"` olmamalı).
  - `teknik_koru`: `"faster whisper modelini large turbo ya güncelle"` → `["faster-whisper", "large-v3-turbo"]` **veya** `["faster whisper", "large turbo"]` — must_contain'de alternatifler `"|"` ile: `"faster-whisper|faster whisper"`; `"docker kompoz"` → `["docker compose|docker-compose"]`, must_not `["kompoz"]`; `"pull rikuest"` → `["pull request"]`.
  - `noktalama`: `"merhaba nasılsın bugün ne yapıyorsun"` → `["?", "Merhaba"]`.
  - `anlam_koru` (değiştirilmemeli): `"Bu fonksiyon null döndürüyor, bakabilir misin?"` → must_contain aynısı, `max_change_ratio: 0.05`.
  - `bos_degisiklik`: tamamen doğru metin → `changes` boş olmalı (violation: `"gereksiz değişiklik"`).
  Her örnek: `{"id": "yazim-01", "category": "yazim", "raw": "...", "must_contain": [...], "must_not_contain": [...], "max_change_ratio": 0.4}`.

- [ ] **Adım 2: Başarısız testler** — `tests/test_eval_scoring.py`:
```python
def test_perfect_result_scores_one():
    c = Case("x", "yazim", "çuk güzel", ("çok güzel",), ("çuk",), 0.5)
    s = score_case(c, CorrectionResult("çok güzel", (Change("çuk", "çok", "yazım"),)), 1.0)
    assert s.score == 1.0

def test_alternatives_in_must_contain():
    c = Case("x", "teknik_koru", "docker kompoz", ("docker compose|docker-compose",), ("kompoz",), 0.5)
    assert score_case(c, CorrectionResult("docker-compose dosyası", ()), 1.0).passed_contains == 1

def test_over_edit_penalised():
    c = Case("x", "anlam_koru", "Bu iyi.", ("Bu iyi.",), (), 0.05)
    s = score_case(c, CorrectionResult("Bu gerçekten çok iyi bir şey.", ()), 1.0)
    assert s.over_edited and s.score < 0.9

def test_none_result_scores_zero():
    assert score_case(Case("x", "yazim", "a", ("a",), (), 0.5), None, 0.0).score == 0.0

def test_aggregate_scale_and_categories():
    ...
    assert 0 <= aggregate(scores)["score_10"] <= 10

def test_render_markdown_has_table_header():
    assert "| Model |" in render_markdown({"m": {"score_10": 8.2, "avg_latency": 1.1, "by_category": {}}})
```

- [ ] **Adım 3: `eval_llm.py` uygula** — CLI: `python scripts/eval_llm.py [--models a b c] [--out docs/llm_benchmark.md] [--runs 1]`. Modeller `ollama list` ile kontrol edilir; yoksa `ollama pull` **kullanıcı onayı** ile (script sadece komutu yazdırır). Her model için: `OllamaProvider(LlmSettings(model=m, keep_alive="0"))` (VRAM boşalsın), `correct()` çağrıları, `score_case`. `render_markdown` → tablo: Model · Puan/10 · yazım · bağlam · teknik · noktalama · anlam · boş · ort. gecikme · VRAM (nvidia-smi `--query-gpu=memory.used` istek sırasında örneklenir).

- [ ] **Adım 4: Aday listesini çalıştırma anında doğrula** — bellek notu: kullanıcı güncel olmayan model seçimlerini reddeder. Agent şunları yapar:
  1. `ollama list` ile kurulu modelleri yaz.
  2. `https://ollama.com/library` (web) üzerinden **son 6 ay** içinde yayınlanmış, 8 GB VRAM'e sığan (≤ 6 GB ağırlık, q4 seviyesi), Türkçe desteği olduğu bilinen aileleri listele. Başlangıç adayları (doğrulanacak): `qwen3.5:4b`, `qwen3.5:8b` (q4, ~5 GB — Whisper ile birlikte sınırda; test edilir), `gemma4:e4b-it-qat`, `gemma4:e2b`, ve kütüphanede yeni çıkmış diğer 4–9B modeller.
  3. Aday listesini `docs/llm_benchmark.md` başında "Adaylar ve neden" bölümü olarak yaz; kullanıcıya göster, **onay al**, sonra `ollama pull`.

- [ ] **Adım 5: Çalıştır** — `.venv/bin/python scripts/eval_llm.py --models <onaylanan liste> --runs 2 --out docs/llm_benchmark.md`. Whisper'ın yükleneceği gerçek koşulu taklit etmek için benchmark öncesi `nvidia-smi` çıktısını ve her modelin tepe VRAM'ini tabloya koy.

- [ ] **Adım 6: Varsayılanı güncelle** — En yüksek `score_10`; eşitlikte (±0,3) daha düşük gecikme, sonra daha düşük VRAM. `LlmSettings.model` ve `scripts/eval_llm.py` varsayılan listesi güncellenir; README "Varsayılan LLM" satırı + `docs/llm_benchmark.md` bağlantısı; bellek notu `feedback-latest-local-models.md` yeni varsayılan ve tarihle güncellenir.

- [ ] **Adım 7: Testler + ruff**
- [ ] **Adım 8: Commit** — `feat: Türkçe LLM düzeltme benchmark'ı; varsayılan model <kazanan> (<puan>/10)`

---

## 6. Sonraya bırakılanlar (bu planda değil)

| İş | Neden sonra |
|---|---|
| Model indirme ilerleme diyaloğu + ilk çalıştırma sihirbazı | T6 sekmeleri bittikten sonra parçaları birleştirmek kolay |
| Çeviri/prompt için akışlı çıktı (`stream=True`) | Sağlayıcı katmanı T7 ile otursun |
| Özel sözlük (`hotwords` + prompt) | T8 VAD ile aynı dosyaya dokunur; çakışmasın |
| Sistem koyu teması | kozmetik |
| Bas-konuş (push-to-talk) | Windows `RegisterHotKey` tuş bırakmayı vermiyor; klavye kancası gerekir |
| Kayıt sırasında canlı çözümleme | en büyük iş; sınırsız kayıt + batching bunu kısmen telafi ediyor |
| Anthropic yapılandırılmış çıktı API'sine geçiş | mevcut ayıklama çalışıyor |
| Geçmiş için SQLite | 1000+ kayıt ve tam metin arama gerekince |

## 7. Ölçülebilir hedefler

| Metrik | Bugün | Hedef |
|---|---|---|
| Kısayol → metin aktif pencerede (10 sn kayıt, 3060 Ti) | ~5 sn + elle kopyala/yapıştır | ~3–4 sn, elle işlem yok |
| İlk diktede ek gecikme | +3–7 sn | +0–1 sn |
| Arayüzden erişilen ayar | 13 / 23 | tümü |
| Sessiz kayıtta halüsinasyon | olur ("Altyazı M.K.") | "Konuşma algılanmadı" |
| Kayıt süresi üst sınırı | 600 sn, sessiz kesme | sınırsız |
| Varsayılan LLM seçimi | ölçülmemiş | benchmark ≥ 8/10, belgeli |
| Test sayısı / kapsam | 134 / %88 | ≥ 210 / ≥ %85 |
