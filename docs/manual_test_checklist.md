# Manuel Test Kontrol Listesi (Windows 11)

- [ ] Uygulama açılınca tray ikonu görünür, tooltip "Model yükleniyor…" → ~10 s içinde "Hazır".
- [ ] Ctrl+Alt+Space → ekran alt-ortasında overlay; konuşunca dalga çubukları hareket eder; kırmızı nokta 0,5 s aralıkla yanıp söner; süre sayar.
- [ ] Ctrl+Alt+Space (ikinci) → overlay "Yazıya dökülüyor…" sonra "Düzeltiliyor…", ardından sonuç penceresi öne gelir.
- [ ] 20 s'lik Türkçe kayıt için STT + düzeltme toplam < 8 s.
- [ ] Ham ve Düzeltilmiş pane'ler dolu; değişiklik listesi mantıklı ("çuk → çok").
- [ ] Düzeltilmiş pane elle düzenlenebilir; sağ üst kopyala → "Kopyalandı" toast'ı; Notepad'e yapıştırınca aynı metin.
- [ ] "İngilizce'ye Çevir" → üçüncü pane başlığı "İngilizce Çeviri", içerik İngilizce; butonlar işlem sırasında kilitli.
- [ ] "Agent Prompt'a Dönüştür" → "# Goal" ile başlayan İngilizce Markdown prompt; kopyalanabilir.
- [ ] Sonuç penceresi açıkken Ctrl+Alt+Space → yeni kayıt başlar, pane'ler temizlenir.
- [ ] Transkripsiyon sırasında kısayol yok sayılır.
- [ ] Pencereyi X ile kapat → tray'de kalır; tray çift tık → pencere geri gelir.
- [ ] İkinci kez `python -m dikte` → yeni örnek açılmaz, mevcut pencere öne gelir.
- [ ] Ollama kapalıyken kayıt → tray'de kırmızı bildirim, ham metin yine de gösterilir (düzeltilmiş = ham).
- [ ] Mikrofon yokken kayıt → hata bildirimi, IDLE'a döner.
- [ ] Ayarlar → kısayolu ctrl+shift+d yap → yeni kısayol anında çalışır; regedit HKCU\...\Run altında "Dikte" değeri var/yok toggle'a göre.
- [ ] Oturumu kapat/aç → uygulama tray'de otomatik başlar (`--minimized`).
- [ ] %APPDATA%\Dikte\history.jsonl her sonuçtan sonra bir satır büyür.
- [ ] `nvidia-smi`: boşta VRAM ≈ 1,6 GB (Whisper) + Ollama ≈ 3,5–4,5 GB (4B model); toplam < 7,5 GB, CPU offload yok (`ollama ps` → "100% GPU").

## Linux (ikincil ortam)

- [ ] `./packaging/linux/install.sh` hatasız tamamlanır; uygulama menüsünde "Dikte" görünür.
- [ ] `dikte --minimized` → tray ikonu belirir, pencere açılmaz.
- [ ] Uygulama kapalıyken `dikte --toggle` → "çalışmıyor" mesajı, çıkış kodu 1.
- [ ] Uygulama açıkken `dikte --toggle` → kayıt başlar; ikinci kez → durur ve metin gelir.
- [ ] Masaüstü kısayolu (GNOME/KDE/sway) `dikte --toggle` komutuna bağlanır ve çalışır.
- [ ] Ayarlar → otomatik başlatma açık → `~/.config/autostart/dikte.desktop` oluşur; kapalı → silinir.
- [ ] Tray ipucu global kısayol yerine `dikte --toggle` yazar, hata bildirimi çıkmaz.
- [ ] Veriler `~/.config/Dikte/`, modeller `~/.cache/Dikte/models/` altına yazılır.
- [ ] Mikrofon PulseAudio/PipeWire üzerinden seçilebilir (`libportaudio2` kurulu).

## GPU zorunluluğu ve toplu çözümleme

- [ ] NVIDIA sürücüsü devre dışıyken (veya `CUDA_VISIBLE_DEVICES=-1`) uygulama açılır,
      tray'de "CUDA destekli GPU bulunamadı" hatası çıkar ve CPU'ya düşmez.
- [ ] 10 saniyelik kayıt → tek geçişli çözümleme (log'da "Toplu çözümleme açıldı" yok).
- [ ] 90 saniyelik kayıt → log'da "Toplu çözümleme açıldı (batch_size=8)" görünür,
      `nvidia-smi` anlık VRAM artışı < 2 GB ve toplam < 7,5 GB.
- [ ] Ayarlar → "Uzun kayıtlarda toplu çözümleme" kapatıldığında uzun kayıt da tek geçişte çözülür.
- [ ] CC < 7.0 GPU'da (ör. GTX 970) uygulama açılır, `float32`'ye düşer ve tray'de
      "GPU ... desteklemiyor" bildirimi çıkar; transkripsiyon çalışır.

## LLM'in isteğe bağlı olması

- [ ] Ayarlar → "LLM ile metin düzeltme" kapatıldığında sağlayıcı/model/host alanları pasifleşir.
- [ ] LLM kapalıyken dikte: CORRECTING durumu hiç görünmez, sonuç penceresinde
      "Düzeltilmiş" paneli ham metnin aynısını gösterir, `ollama ps` boş kalır.
- [ ] LLM kapalıyken "İngilizce'ye Çevir" ve "Agent Prompt'a Dönüştür" düğmeleri pasif,
      ipucu metni "LLM kapalı" yazar.
- [ ] LLM tekrar açıldığında uygulama yeniden başlatılmadan çalışır (yeniden başlatma uyarısı çıkmaz).
- [ ] `keep_alive` = 0 iken istek bittikten sonra `ollama ps` modeli listeden düşürür (VRAM boşalır).

## İptal

- [ ] Kayıt sürerken `Esc` (Windows'ta global): overlay kapanır, durum boşa döner, tepside "İptal edildi" bildirimi çıkar.
- [ ] Çözümleme sürerken overlay'deki "Vazgeç": durum boşa döner ve **geç gelen sonuç pencereye düşmez**.
- [ ] Tepsi menüsündeki "Vazgeç": yalnızca kayıt/çözümleme/düzeltme sırasında etkin, boştayken soluk.
- [ ] Linux'ta global Esc kaydedilemez; overlay düğmesi, pencere odaktayken `Esc` ve tepsi menüsü ile iptal çalışır.
- [ ] İptalden sonra kısayola basınca yeni kayıt sorunsuz başlar (önceki oturum metni temizlenmiş olur).

## Geçmiş paneli

- [ ] Araç çubuğundaki "Geçmiş" düğmesi sağdaki paneli açar/kapatır; panel kapatılınca düğme de kalkar.
- [ ] Yeni bir dikte bitince kayıt listenin **en üstüne** düşer.
- [ ] Arama kutusu: "toplanti" yazınca "Toplantısı" geçen kayıt görünür (aksan ve büyük/küçük harf duyarsız).
- [ ] Bir kayda tıklayınca ham/düzeltilmiş/çıktı panelleri o kayıtla dolar.
- [ ] "Sil" seçili kaydı, "Tümünü temizle" onaydan sonra tüm geçmişi siler; dosya (`history.jsonl`) da güncellenir.
- [ ] Ayarlardaki "Geçmiş kayıt sayısı" 200 iken 201. kayıt eklenince en eski düşer.
- [ ] Durum çubuğu: sol tarafta "12 sn · 34 kelime", sağda "large-v3-turbo · float16 · LLM: …".
- [ ] Değişiklik listesinde `x → x` biçiminde özdeş satır görünmez.

## LLM sağlayıcıları

- [ ] Ollama (varsayılan): yerel model çalışırken düzeltme yapılıyor, keep_alive uygulanıyor.
- [ ] OpenAI: `OPENAI_API_KEY` tanımlı, anahtar durumu "✓ tanımlı"; düzeltme JSON şemasıyla dönüyor.
- [ ] Anthropic: `ANTHROPIC_API_KEY` ile düzeltme çalışıyor.
- [ ] Gemini: `GEMINI_API_KEY` ile düzeltme çalışıyor.
- [ ] Custom / openai formatı: LM Studio (`http://localhost:1234/v1`), anahtar alanı boş; şema
      desteklenmiyorsa `json_object`'e düşüp yine de düzeltme üretiyor.
- [ ] Custom / anthropic formatı: Anthropic-uyumlu bir proxy base URL'i ile çalışıyor.
- [ ] Anahtar tanımlı değilken sağlayıcı seçilirse uygulama çökmüyor; tepside açıklayıcı hata çıkıyor
      ve ham metin gösteriliyor.
- [ ] Ayar dosyasında (`config.json`) hiçbir anahtar **değeri** yok, yalnızca ortam değişkeni adları var.

## Sessizlik ve halüsinasyon

- [ ] Kısayola basıp hiç konuşmadan durdur: "Konuşma algılanmadı" uyarısı çıkıyor, uydurma metin yok.
- [ ] Normal dikte: metin eksiksiz; cümle başları/sonları VAD tarafından kırpılmıyor.
- [ ] VAD eşiği 0,35'e çekilince fısıltıyla konuşma da yakalanıyor.
- [ ] "Bilinen uydurma metinleri ele" kapalıyken sessizlikten gelen metin görünüyor (karşılaştırma).
- [ ] "Bugün toplantıda altyazı ekleme özelliğini konuştuk" cümlesi **elenmiyor** (yanlış pozitif yok).
- [ ] VAD kapalıyken uzun kayıt hata vermiyor (toplu çözümleme otomatik devre dışı kalıyor).
