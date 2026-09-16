# Dikte — QOL · Performans · Yeni Özellik Raporu (v2)

**Tarih:** 2026-09-16 · **Temel:** `main` @ `65ec30b` (356 test) · **Durum:** inceleme, kod değişikliği yok.

İlk iyileştirme planı (T1–T9) tamamlandı: iptal, yapıştırma, geçmiş, sekmeli ayarlar, altı
sağlayıcı, VAD/halüsinasyon filtresi ve ölçülmüş varsayılan LLM (gemma4 9,02/10). Bu rapor
**bir sonraki turu** önerir. Her madde kodda dayandığı yeri, kullanıcıya faydasını ve efor
tahminini (S < 2 sa · M ½–1 gün · L 1–3 gün) içerir.

## 0. Özet — önce bunlar

| # | Öneri | Tür | Etki | Efor |
|---|---|---|---|---|
| 1 | **Bas-konuş (push-to-talk) + tıkla-aç melez kısayol** | Özellik | Çok yüksek | M |
| 2 | **Özel sözlük**: Whisper `hotwords` + LLM sözlüğü + kullanıcı düzeltmelerinden öğrenme | Özellik | Çok yüksek | M |
| 3 | **Mod kısayolları**: ikinci kısayol = "çevir ve yapıştır" / "agent prompt'u yapıştır" | Özellik | Yüksek | M |
| 4 | **`changes` listesini LLM'den değil difflib'den üret** → daha az çıktı token'ı, daha güvenilir liste | Perf | Yüksek | S |
| 5 | **Ayar değişikliğinde yeniden başlatma şartını kaldır** (15 STT alanından yalnızca 2'si model yüklemesi ister) | QOL | Yüksek | S–M |
| 6 | **Overlay'de hata durumu + ses geri bildirimi** (balon 4 sn'de kaybolmasın) | QOL | Yüksek | S |
| 7 | **Sessizlikte otomatik durdurma** (eller serbest akış) | QOL | Orta | S |
| 8 | **Kayıt sırasında parça parça çözümleme** (uzun diktede bekleme ~sabit) | Perf | Yüksek | L |
| 9 | **Panoyu koru** (yapıştırma sonrası eski pano içeriği geri gelsin) | QOL | Orta | S |
| 10 | **Ses dosyası çözümleme** (sürükle-bırak toplantı kaydı) | Özellik | Orta | M |

---

## 1. QOL — kullanıcı akışı ve arayüz

### 1.1 Hatalar kullanıcının baktığı yerde görünmüyor
- **Bugün:** hata tepsi balonunda 4 sn (`ui/tray.py:79`), durum çubuğunda 8 sn
  (`ui/result_window.py:270`). Pencere gizliyken yalnızca balon kalır; "Konuşma algılanmadı"
  gibi sık hatalar kaçar.
- **Öneri:** overlay'e kırmızı bir **hata durumu** ekle (`ui/overlay.py:98 on_state` yanına
  `show_error(text)`; 2,5 sn sonra gizle). Kullanıcı zaten overlay'e bakıyor.
- Ek: **başlat/durdur/hata sesleri** (kısa WAV, `QSoundEffect`; ayarlarla kapatılabilir).
  Tam ekran uygulamada overlay görünmezken tek geri bildirim budur.
- Efor: S (≈ 1,5 sa + testler).

### 1.2 "Yeniden başlatınca etkin olur" gereksiz yere geniş
- **Bugün:** `app.py:244` — `stt` veya `audio` bloğundaki **her** alan değişince restart uyarısı.
  Oysa VAD eşikleri, beam_size, initial_prompt, batch ayarları `engine.py:220`'de her
  çözümlemede `self._settings`'ten okunuyor; mikrofon `recorder.py:51`'de her başlatmada.
- **Öneri:** `FasterWhisperEngine.update_settings()` ve `AudioRecorder.update_settings()`
  ekle; yalnızca `model` / `compute_type` değişince arka planda yeniden yükle
  (`controller.warm_up()` zaten var; `ready_changed(False)` → tray "Model yükleniyor…").
- Efor: S–M.

### 1.3 Sonuç penceresi: üçüncü sütun boş, değişiklikler ayrı listede
- **Bugün:** üç sabit panel (`result_window.py:64-67`); çeviri/prompt paneli çoğu zaman boş.
  Değişiklikler ayrı `QListWidget`'ta (`:45`), metinle bağlantısız.
- **Öneri:**
  1. Değişiklikleri **düzeltilmiş metnin içinde vurgula** (`QTextCharFormat` arka plan;
     üstüne gelince "orijinal → neden" tooltip'i). Liste kalkar, dikey alan kazanılır.
  2. Üçüncü paneli **boşken daralt** (splitter 0) ve yalnızca istek gelince aç.
  3. Kullanıcı düzeltilmiş metni **elle düzenleyip "Yeniden yapıştır" (Ctrl+Enter)**
     diyebilsin; düzenleme geçmişe de yazılsın. Bugün düzenleme hiçbir yere gitmiyor.
- Efor: M.

### 1.4 Pano ve yapıştırma
- **Panoyu koru:** `app.py:185` panoyu ezer. Seçenek: eski içeriği sakla, yapıştırmadan
  ~300 ms sonra geri yükle (yapıştırma asenkron okur). Efor: S.
- **`keybd_event` yerine `SendInput`** (`platform/paste.py:35`): eski API, bazı uygulamalar
  (yükseltilmiş pencereler, oyunlar) görmezden geliyor. Efor: S.
- **Yapıştırma tuşu profile bağlı olsun:** Linux terminalleri Ctrl+Shift+V ister; bkz. §3.4.
- **Yapıştırma başarısızsa yazarak gönder** (`SendInput` Unicode) — pano kilitliyse yedek.
  Efor: S.

### 1.5 Tepsi ve pencere kısayolları
- Tepsi menüsüne **"Son metni kopyala"** ve son 5 diktenin alt menüsü (`ui/tray.py:42`).
- Pencerede `Ctrl+,` ayarlar, `Ctrl+H` geçmiş, `Ctrl+F` geçmişte arama odağı.
- Geçmiş paneli: **dışa aktar** (txt/md), tarihe göre gruplama, sabitleme. Efor: S–M.

### 1.6 İlk çalıştırma ve model indirme
- **Bugün:** ilk açılışta ~1,6 GB model, tray tooltip'inde "Model yükleniyor…" dışında
  gösterge yok (`engine.py:169`). Ollama modeli yoksa ilk dikte "Ollama'ya ulaşılamadı" der.
- **Öneri:** ilk çalıştırma denetimi (GPU var mı · Whisper modeli var mı · Ollama ayakta mı ·
  model çekilmiş mi) + ilerleme çubuklu indirme diyaloğu (`huggingface_hub.snapshot_download`
  `tqdm_class` ile). Efor: M.

### 1.7 Tema
- Qt 6.11'in `windows11` stili sistem koyu temasını büyük olasılıkla zaten izliyor; sorun
  sabit renkler: `color:#888` (`result_window.py:121`, `history_panel.py:57`), toast ve overlay
  sabit koyu. **Palete bağla** (`palette().placeholderText()`), gerçek makinede koyu temada
  bir tur kontrol et. Efor: S.

---

## 2. Performans

### 2.1 `changes` listesini LLM üretmesin (en ucuz kazanç)
- **Bugün:** `llm/prompts.py:11-29` şeması her değişikliği `original/replacement/reason`
  ile istiyor → çıktı token'ı düzeltilmiş metnin **üstüne** yaklaşık %30–60 daha. UI zaten
  özdeş çiftleri eliyor (`result_window.py:236`), yani liste güvenilir değil.
- **Öneri:** şemadan `changes`'i çıkar; ham ↔ düzeltilmiş kelime farkını `difflib` ile
  hesapla (`llm/tasks.py:_parse_correction`). `reason` istenirse yalnızca seçilen değişiklik
  için ikinci, küçük bir istekle sor. Benchmark'ta gecikme düşüşünü ölç
  (`scripts/eval_llm.py` zaten gecikme sütunu veriyor).
- Efor: S. Beklenti: LLM adımı ~%25–40 kısalır.

### 2.2 VAD iki kez çalışıyor
- **Bugün:** `engine.py:222` ön kontrol tüm kaydı Silero'dan geçiriyor; `:231` `vad_filter=True`
  aynı işi faster-whisper içinde tekrarlıyor. Silero CPU'da ~gerçek zamanın %1–3'ü: 5 dk
  kayıtta 3–9 sn ek bekleme.
- **Öneri:** ön kontrolden dönen zaman damgalarını sakla; toplu boru hattına
  `clip_timestamps=` olarak ver (faster-whisper 1.2.1: verilirse `vad_filter` yok sayılır,
  `transcribe.py:343`). 60 sn altı (toplu olmayan) yolda ikinci geçiş ucuz, olduğu gibi kalsın.
- Efor: S.

### 2.3 Kayıt sırasında parça parça çözümleme (en büyük kazanç, en büyük iş)
- **Bugün:** çözümleme durdurulduktan sonra başlıyor; 5 dk dikte → ~10–20 sn bekleme.
- **Öneri:** kayıt sürerken her ~20–30 sn'de VAD'ın bulduğu bir sessizlik sınırında parçayı
  havuza gönder; `initial_prompt`'a önceki parçanın son cümlesini ekle (Whisper'ın bağlam
  hilesi; doğruluğu da artırır). Durdurunca yalnızca kuyruk çözümlenir → bekleme parça
  boyundan bağımsız. Overlay'de **canlı transkript** olarak da gösterilebilir.
- Dikkat: `engine._lock` STT'yi seri hâle getiriyor (istenen davranış); LLM düzeltmesi tüm
  metin bittikten sonra tek seferde yapılmalı (parça başına düzeltme tutarsız olur).
- Efor: L.

### 2.4 STT varsayılanlarını ölç
- `beam_size=5` (`config.py:21`) turbo modelde 1–2'ye göre ~1,5–2× yavaş; kalite farkı
  Türkçede ölçülmedi. `condition_on_previous_text=True` (`engine.py:246`) uzun kayıtta
  tekrar döngülerine açık.
- **Öneri:** `scripts/eval_stt.py` — küçük Türkçe klip seti (Common Voice TR alt kümesi veya
  kendi 20 kaydınız) + WER; `beam_size ∈ {1,2,5}` ve `condition_on_previous_text` için tablo.
  LLM benchmark'ında yaptığınız gibi varsayılanı ölçüme bağlayın.
- Efor: M (veri toplama dahil).

### 2.5 VRAM görünürlüğü
- 8 GB kartta Whisper fp16 (~1,6 GB) + gemma4 e4b + CUDA bağlamı sınırda; `keep_alive=30m`.
  Hakkında sekmesine **kullanılan/boş VRAM** (nvidia-smi sorgusu, ek bağımlılık yok) ve boş
  VRAM < model boyutuysa durum çubuğunda uyarı. Efor: S.

### 2.6 Küçük şeyler (gerekmedikçe dokunma)
- Geçmiş: her diktede dosyanın tamamı okunup yazılıyor (`core/history.py:52`); liste her
  seferinde sıfırdan kuruluyor; arama her tuşta tüm oturumları normalize ediyor
  (`history_panel.py:96`). 200 kayıtta fark edilmez; limit 5000'e çıkarsa normalize edilmiş
  metni oturumla birlikte önbelleğe alın.
- Çeviri/prompt için `stream=True`: perceived latency; §3.3 mod kısayolları gelince
  değerlendirin.

---

## 3. Yeni özellikler

### 3.1 Bas-konuş + tıkla-aç melez (kanca gerektirmeden)
- **Neden:** diktede en doğal akış "tuşu basılı tut, konuş, bırak". Plan bunu "klavye kancası
  gerekir" diye ertelemişti.
- **Kancasız yol:** `RegisterHotKey` basışı veriyor (`platform/hotkey.py:28`). Basış gelince
  30 ms'lik `QTimer` ile `GetAsyncKeyState(vk)` yokla: tuş 250 ms'den uzun basılıysa **bas-konuş**
  (bırakınca durdur), kısa basışsa **tıkla-aç** (bugünkü davranış). Hook yok, yönetici hakkı yok.
- Linux: `dikte --toggle` zaten var; `--start` / `--stop` ekleyip masaüstü ortamının
  "basınca/bırakınca" bağlamasına bırak.
- Efor: M (Windows'ta gerçek makinede test şart; `docs/manual_test_checklist.md`'ye madde).

### 3.2 Özel sözlük (doğruluğa en çok katkı)
- **Üç katman, tek liste:**
  1. **Whisper:** `hotwords="…"` parametresi (faster-whisper 1.2.1 destekliyor,
     `transcribe.py:296`) + `initial_prompt`'a terimleri ekle (`engine.py:237`). Özel isimler
     ve teknik terimler için en etkili yöntem.
  2. **LLM:** `CORRECT_SYSTEM`'e "Sözlük: …" bölümü (`llm/prompts.py:1`); kullanıcı
     "Düzeltme talimatına ek" serbest metni de yazabilsin (bugün prompt sabit).
  3. **Kural tabanlı:** `yanlış → doğru` birebir değiştirmeler (LLM kapalıyken de çalışır).
- **Öğrenme döngüsü:** kullanıcı düzeltilmiş metni elle düzenlerse (§1.3) farkı çıkar,
  "sözlüğe ekleyeyim mi?" öner.
- Ayarlar → yeni "Sözlük" sekmesi; `config.json`'da `dictionary: tuple[Entry, ...]`.
- Efor: M.

### 3.3 Mod kısayolları
- **Bugün:** tek akış: kayıt → düzelt → yapıştır. Çeviri ve agent prompt'u pencereden düğmeyle
  (`result_window.py:49-50`); `result_ready` yalnızca `corrected_text` yayar
  (`controller.py:194`).
- **Öneri:** ikinci/üçüncü global kısayol (`GlobalHotkey(hotkey_id=HOTKEY_ID+2)` deseni
  hazır) → `toggle(mode="translate" | "prompt")`; `_on_corrected` sonrası seçilen görevi
  zincirle ve **o çıktıyı** yapıştır. Linux için `dikte --toggle --mode prompt`.
- Sizin kullanımınız için (agent prompt'ları) en çok zaman kazandıran madde.
- Efor: M.

### 3.4 Uygulama profilleri
- Ön plandaki `.exe` (Windows: `GetWindowThreadProcessId` + `QueryFullProcessImageName`,
  ek bağımlılık yok) → profil: varsayılan mod, yapıştırma tuşu (Ctrl+V / Ctrl+Shift+V),
  sondaki boşluk/yeni satır, LLM aç/kapa (terminalde ham metin).
- `paste.py:77 paste_active_window` zaten ön plan penceresini alıyor; profil eşlemesi oraya eklenir.
- Efor: M–L. §3.3'ten sonra.

### 3.5 Sessizlikte otomatik durdurma
- `recorder.py:104` her 100 ms RMS veriyor. Konuşma başladıktan sonra N sn (varsayılan 2,5)
  eşik altı → `limit_reached` benzeri `silence_reached` sinyali → `controller` durdurur.
  Ayar: "Sessizlikte durdur (sn), 0 = kapalı". Gürültü tabanı için ilk 300 ms'yi referans al.
- Efor: S.

### 3.6 Ses dosyası çözümleme
- Pencereye sürükle-bırak veya araç çubuğu "Dosya aç…" → `faster_whisper.decode_audio(path)`
  (PyAV zaten bağımlılık) → mevcut `_stop_and_transcribe` yoluna ver. Uzun dosyada toplu
  boru hattı devreye girer. Toplantı kayıtları için ilk adım.
- Efor: M.

### 3.7 Sesli komutlar (temkinli)
- "yeni satır" / "yeni paragraf" güvenli. "nokta", "virgül" gibi kelimeler Türkçede gerçek
  sözcük ("bu nokta önemli") → yalnızca cümle sonunda ve ayarla açık olsun. "Son cümleyi sil"
  ham metin üzerinde deterministik. LLM'e bırakılmamalı (tutarsız).
- Efor: S–M.

### 3.8 Daha sonra
- Kullanıcı tanımlı LLM görevleri (kendi sistem prompt'u + kısayol) → §3.3'ün genellemesi;
  `Session.translation/enhanced_prompt` sabit alanları `outputs: dict` olmalı.
- Otomatik dil algılama modu (`language=None`) / İngilizce dikte modu.
- Geçmiş için SQLite + FTS5 (1000+ kayıt olunca).
- Anthropic yapılandırılmış çıktı API'si (mevcut ayıklama çalışıyor).

---

## 4. Doğruluk notları (LLM benchmark'ından)

- `baglam` kategorisi 7,0 ile en zayıf (`docs/llm_benchmark.md:73`). Sözlük ve kullanıcı
  talimatı (§3.2) bu kategoriyi doğrudan besler. Few-shot örnek eklenecekse benchmark
  setinden **olmayan** örnekler kullanın; yoksa puan şişer.
- `changes` listesi güvenilir değil (§2.1); model "değişiklik yaptım" deyip yapmayabiliyor.
- `hallucinations.py` kara listesi iyi tasarlanmış (tek başına segment kuralı). Yeni kalıp
  çıktıkça kullanıcı listeye ekleyebilsin (ayarlarda serbest metin var mı kontrol edin;
  `_PROXIED`'da `hallucination_filter_check` var, liste düzenleme görünmüyor).

---

## 5. Önerilen sıra

| Faz | İçerik | Süre |
|---|---|---|
| **A — hızlı kazançlar** | §2.1 difflib · §1.1 overlay hata + ses · §1.4 panoyu koru + SendInput · §3.5 sessizlikte durdur · §2.2 tek VAD | 1,5 gün |
| **B — akış** | §3.1 bas-konuş · §3.3 mod kısayolları · §1.2 restart'sız ayar | 2 gün |
| **C — doğruluk** | §3.2 sözlük (+ öğrenme) · §1.3 satır içi vurgu + elle düzenleme · §2.4 STT ölçümü | 2,5 gün |
| **D — büyük** | §2.3 parça parça çözümleme / canlı transkript · §3.4 profiller · §3.6 dosya · §1.6 ilk çalıştırma | 4–5 gün |

Her madde mevcut sözleşmelere uyar: enjekte edilebilir dış dünya (`*_probe`/`*_factory`),
`frozen` pydantic + `model_copy`, yeni ayar alanlarına varsayılan değer, TDD.

## 6. Kapsam dışı bırakılanlar

- CPU geri dönüşü (ürün kararı).
- Bulut senkronizasyonu, çok kullanıcılı geçmiş.
- Otomatik güncelleme (kişisel kullanım; GitHub release kontrolü istenirse S efor).
