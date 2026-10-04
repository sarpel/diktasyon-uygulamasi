# Değişiklik günlüğü

Bu projedeki önemli değişiklikler bu dosyada tutulur. Biçim
[Keep a Changelog](https://keepachangelog.com/tr-TR/1.1.0/) esas alınarak hazırlanmıştır ve proje
[Semantic Versioning](https://semver.org/lang/tr/) kullanır.

## [Yayımlanmamış]

### Eklendi

- Lisans (MIT), İngilizce README özeti, kurulum ve kullanım kılavuzları, katkı rehberi, güvenlik
  politikası, davranış kuralları, üçüncü taraf lisans bildirimleri, issue/PR şablonları.
- "Son sonucu yapıştır" (tray menüsü ve isteğe bağlı kısayol).
- "Geri al" sesli komutu (ön plandaki uygulamaya `Ctrl+Z` gönderir) ve "son kelimeyi sil".
- Başarısız veya boş dönen kaydın sesini saklama ve tray'den yeniden deneme.
- Sessiz mikrofon uyarısı; kayıtlı mikrofon yoksa varsayılana dönüp bildirme.
- Mikrofonun adıyla saklanması; Windows'ta WASAPI cihazları (16 kHz'e otomatik dönüştürme).
- Kayıt sırasında çalan medyayı duraklatma (Linux: `playerctl`, Windows: `.[media]` extra'sı).
- Windows'ta dikte metninin pano geçmişine ve bulut panosuna girmemesi; pano geri yüklemesinin
  yalnızca araya yeni bir kopya girmediyse yapılması.
- Overlay'i sürükleyip taşıma ve konumunun hatırlanması; overlay'de uyarı satırı.
- Geçmiş için saklama süresi (gün); süresi dolan kayıtlar açılışta ve ayar değişince silinir.
- Geçmişte `Ctrl+F` ile arama.
- Durum kontrolünde tek tıkla "Ollama'yı başlat" ve onaylı "Modeli indir (ollama pull)".
- LLM düzeltme sağlamlık kontrolü: model düzeltmek yerine cevap verir/özetlerse ham metne dönülür.
- Ayar sekmelerinde "Varsayılanlara döndür" düğmeleri.
- Paketlenmiş exe için `--version` duman testi (release iş akışı).

### Değişti

- Bozuk `config.json`'da yalnızca geçersiz alanlar varsayılana döner; diğer ayarlar korunur ve
  eski dosya yedeklenir.
- Uygulama profili eşleştirmesi: önce tam süreç adı, sonra en uzun alt dize kazanır.
- Linux'ta tek örnek/IPC soketi kullanıcıya özel; `--toggle` başka bir kullanıcının örneğini tetiklemez.
- Linux'ta CUDA kütüphaneleri başlatıcı olmadan da açılışta önceden yüklenir.
- Sözlük kuralları tek geçişte uygulanır (bir düzeltme başka bir kuralı yeniden tetiklemez).
- `anthropic` SDK alt sınırı `>=1.0`.
- Python üst sürüm sınırı kaldırıldı (`>=3.11`); CI Linux ve Windows'ta 3.11–3.14'ü zorunlu
  test eder, 3.15 için PR'ı engellemeyen bir erken uyarı işi vardır (3.15, PySide6/ctranslate2/
  onnxruntime o sürüm için paket yayımlayınca çalışır). macOS desteklenmez (CUDA yok).
- Windows'ta medya duraklatma artık terk edilmiş `winsdk` yerine pywinrt (`winrt-*`) paketlerini
  kullanır; desteklenen tüm Python sürümlerinde çalışır.
- LLM düzeltme sağlamlık kontrolü sıkılaştı: 4 kelimeden kısa diktelerde en fazla 2 kelime
  eklenebilir; ham metnin içerik kelimelerinin en az %40'ı düzeltmede korunmalıdır (dolgu ve sayı
  sözcükleri sayılmaz). Kelime sayısı alt sınırı dolgular çıkarılarak hesaplanır. Çeviri ve prompt
  iyileştirmede boş ya da aşırı uzun yanıtlar reddedilir.
- "Eski pano içeriğini geri yükle": bekleme 2–5 sn'ye çıktı; `Ctrl+Shift+V` profillerinde ve uzak
  masaüstü/sanal makine pencerelerinde (mstsc, Hyper-V, VirtualBox, VMware, Remmina…) geri yükleme
  yapılmaz.
- Wayland'de önce `wtype` kullanılır; sanal klavye desteklemeyen ortamlarda (GNOME) yapıştırma
  "yapılamadı" sayılır ve metin panoda kalır. Wayland'de etkin uygulama bilinemediği için profiller
  uygulanmaz ve bu bir kez bildirilir.
- Qt'nin standart düğme ve menüleri Türkçe (Tamam/İptal/Evet/Hayır).
- Ayarlar → Hakkında → "Durum kontrolü…" uygulamanın durum penceresini açar; oradan indirilen
  model hemen yüklenir ve Ayarlar kapansa da indirme sürer.
- "Sonuçta pencereyi öne getir" otomatik yapıştırmayla birlikteyse pencere, yapıştırma hedefe
  ulaştıktan sonra öne gelir.
- `audio.sample_rate` yalnızca 16000 kabul eder; başka bir değer yalnızca bu alanı varsayılana döndürür.
- "Halüsinasyon sessizlik eşiği" artık gerçekten uygulanır (toplu çözümlemede faster-whisper
  desteklemediği için orada etkisizdir).
- `history.jsonl`, `config.json` ve saklanan kayıtlar baştan yalnızca kullanıcıya okunur (0600)
  oluşturulur ve yerine konmadan önce diske yazılır (fsync).
- Linux'ta IPC soketi kullanıcıya özel 0700 bir dizinde açılır; tek örnek sunucusunun sahibi
  doğrulanır (Windows'ta da). Doğrulanamayan bir süreç adı tutuyorsa Dikte kapanmaz, uyarıyla sürer.
- Linux'ta "tuş tuş yaz" metni komut satırı yerine stdin ile `xdotool`/`wtype`'a verir; dikte
  metni süreç listesinde görünmez.
- OpenAI uyumlu sağlayıcılarda `json_object` ile yeniden deneme yalnızca yanıt biçimi
  reddedildiğinde yapılır.

### Düzeltildi

- Panoda dikte metni varken uygulama kapanınca sürecin çökmesi (Python'da oluşturulan
  `QMimeData` Qt kapanışında geçersiz Python koduna yönleniyordu).
- Windows kurulum paketinde `winsdk` olmadığı için "kayıtta medyayı duraklat" özelliğinin çalışmaması.
- Geçmiş panelindeki, sonuç panellerindeki ve tray'deki kopyalama düğmelerinin "pano geçmişine
  alma" ayarını atlaması.
- Ayarlar → Hakkında'dan açılan durum kontrolünde "Ollama'yı başlat" / "Modeli indir"
  düğmelerinin görünmemesi.
- STT modeli/hassasiyeti değiştirilirken süren bir çözümleme varsa arayüzün o iş bitene kadar donması.
- Geçmiş dışa aktarımında çeviri ve prompt oturumlarının teslim edilen metin yerine düzeltilmiş
  metinle yazılması.
- Geçersiz "son sonucu yapıştır" kısayolunun sessizce silinmesi (artık kaydedilir ve bildirilir).
- Ayar dosyası hiç okunamadığında bildirimin var olmayan bir `.bak` yedeğini göstermesi.
- Anthropic sağlayıcısının boş yanıtı hata saymaması.
- Kayıt durdurulurken henüz çözümlenmemiş canlı parçaların kaybolması ve parçaların sıra dışı birleşmesi.
- Takılı kalan overlay; hata anında eksik parça; sessiz bir kaydın saklanan başarısız kaydı ezmesi.
- Yarıda kesilen LLM yanıtlarının yarım metin olarak yapıştırılması.
- Yazarak yapıştırmada çok satırlı metnin sohbet uygulamalarında mesajı erken göndermesi
  (satır sonları artık `Shift+Enter`) ve Linux'ta uzun metnin kesilmesi.
- Kısayol değiştirilemediğinde eski kısayolun kaybolması; otomatik başlatma yollarındaki tırnaklama.
- Çıkışta medyanın, kuyruktaki duraklatma komutundan önce sürdürülmesi.
- USB mikrofon çıkarıldığında kaydın sessizce sürmesi.
- Sonuç ekranındayken yeni dikte başlatınca geçmişe boş satır yazılması ve aynı oturumun iki kez
  kaydedilmesi; mikrofon açılamazsa önceki sonucun kaybolması.
- Yeniden denemede saklanan sesin LLM düzeltmesi bitmeden silinmesi.
- Yeni dikte sürerken eski metnin çevirisinin/prompt'unun yeni oturuma yazılması; Çeviri/Prompt
  düğmelerinin dikte sürerken, geçmiş görüntülenirken ve Ayarlar kaydedilince yanlışlıkla etkin olması.
- İptal edilen kaydın geç gelen ses parçasının yeni dikteye karışması; işlenemeyen parçanın
  sessizce atlanması (artık "Kaydın bir bölümü işlenemedi" uyarısı gösterilir).
- Beklenmeyen bir iç hatada dikte "çözümleniyor/düzeltiliyor" durumunda kilitli kalması.
- Uygulama kapanırken (Çıkış, oturum kapatma, Windows kapanışı) süren kayıt ve GPU işleri
  durdurulmadığı için çökme/donma riski.
- Otomatik yapıştırma ve "pencereyi öne getir" birlikte açıkken metnin Dikte'nin kendi editörüne
  yapışması.
- Panoya yazılamadığında (başka uygulama panoyu kilitlediyse) yine de `Ctrl+V` gönderilip önceki
  pano içeriğinin yapıştırılması.
- Windows'ta bas-konuş kısayolunun Ctrl/Alt/Shift/Win tuşları hâlâ basılıyken yapıştırmanın başka
  bir kısayola (ör. `Ctrl+Alt+V`) dönüşmesi.
- Wayland'de `xdotool` başarılı dönüp metin hedefe ulaşmadığı hâlde "yapıştırıldı" sayılması.
- "Tuş tuş yaz" modunda uzun metnin arayüzü dondurması; yarıda kesilen yazmanın bildirilmemesi.
- Profilde eşleşme `.exe` ile yazıldığında (ör. `KeePass.exe`) profilin hiç uygulanmaması.
- Bir medya oynatıcısı yanıt vermediğinde duraklatılan diğerlerinin sürdürülmemesi.
- Çeviri/prompt kısayolu kaydedilemediğinde önceki kısayolun kaybolması ve bildirim olmaması.
- Model yeniden yüklemesinin birikip birden çok kez çalışması; biten arka plan işlerinin bellekte kalması.
- Ayarlar kapandıktan sonra biten bağlantı testinin hata vermesi.
- Sonuç penceresindeki kaydedilmemiş düzenlemenin yeni sonuç ya da geçmiş kaydı açılınca kaybolması.

## [0.2.0] - 2026-09-16

### Eklendi

- Bas-konuş (basılı tut) ve tıkla-aç melez kısayol; Linux için `dikte --start` / `--stop`.
- Çeviri ve agent prompt'u için ayrı kısayollar; `--mode` seçeneği.
- Özel sözlük: Whisper hotwords, LLM sözlüğü ve kural tabanlı düzeltme; elle düzeltmelerden sözlük önerisi.
- Sesli komutlar: "yeni satır", "yeni paragraf", "son cümleyi sil".
- Kayıt sırasında parça parça (canlı) çözümleme ve overlay'de canlı transkript.
- Uygulama profilleri: ön plandaki uygulamaya göre mod, yapıştırma tuşu, LLM ve sonek.
- Ses dosyası çözümleme (sürükle-bırak / "Dosya aç…").
- İlk çalıştırmada durum kontrolü ve ilerleme çubuklu model indirme.
- Sessizlikte kaydı otomatik durdurma; başlat/durdur/hata sesleri; overlay'de hata durumu.
- Düzeltilmiş metni elle düzenleme ve yeniden yapıştırma; düzeltmelerin metin içinde vurgulanması.
- Tray'den son dikteleri kopyalama, geçmişi Markdown/düz metin olarak dışa aktarma.
- Hakkında sekmesinde VRAM kullanımı ve düşük VRAM uyarısı.
- Türkçe STT benchmark betiği (WER).

### Değişti

- Ayar değişiklikleri yeniden başlatma gerektirmez; model arka planda yeniden yüklenir.
- Yapıştırma Windows'ta `SendInput` ile; eski pano içeriği geri yüklenebilir.
- Düzeltme değişiklik listesi LLM yerine `difflib` ile hesaplanır (daha az çıktı token'ı).
- Varsayılan LLM modeli benchmark sonucuna göre `gemma4:e4b-it-qat`.

## [0.1.0] - 2026-09-15

İlk sürüm.

- Tray uygulaması, kayıt overlay'i ve üç panelli sonuç penceresi (ham / düzeltilmiş / çıktı).
- faster-whisper ile yalnızca GPU'da STT; uzun kayıtlarda toplu çözümleme; desteklenmeyen
  `compute_type` için otomatik düşürme.
- Silero VAD ön kontrolü ve halüsinasyon filtresi.
- Ollama, LM Studio, OpenAI, Anthropic, Gemini ve özel uç nokta sağlayıcıları; LLM'in isteğe bağlı olması.
- Düzeltme, İngilizce çeviri ve agent prompt'u görevleri; Türkçe LLM benchmark'ı.
- Sonucun panoya yazılması ve aktif pencereye yapıştırılması; kayıt/çözümleme iptali.
- Global kısayol (Windows), `dikte --toggle` ile IPC (Linux), otomatik başlatma, tek örnek kilidi.
- Sekmeli ayarlar, geçmiş paneli, JSONL oturum geçmişi.
- Windows kurulum paketi (PyInstaller + Inno Setup) ve Linux kurulum betiği; GitHub Actions CI.

[Yayımlanmamış]: https://github.com/sarpel/diktasyon-uygulamasi/commits/main
