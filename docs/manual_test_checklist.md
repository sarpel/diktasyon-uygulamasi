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

## Yeniden başlatma gerektirmeyen ayarlar

- [ ] Ayarlar → Konuşma Tanıma'da model veya hassasiyet değiştirip kaydedince uygulama
      yeniden başlatılmaz; bir sonraki dikte modeli arka planda yeniden yükler.
- [ ] Süren bir dikte varken model değiştirilip kaydedilirse bilgilendirme mesajı çıkar
      ("Model değişikliği süren iş bittikten sonra..."); iş bitince Ayarlar tekrar
      kaydedilince model yeniden yüklenir.
- [ ] Ayarlar → Ses'te mikrofon değiştirilince süren kayıt etkilenmez, bir sonraki kayıt
      yeni cihazı kullanır.

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
- [ ] Ollama portu değiştirildiğinde (ör. 11500) "Sunucu adresi" kutusundan yeni adres girilip düzeltme çalışıyor;
      boş bırakılırsa Kaydet engelleniyor.
- [ ] LM Studio: Developer > Start Server açıkken, model kimliği girilip düzeltme çalışıyor;
      anahtar alanı boş bırakılabiliyor ve gizlilik uyarısı görünmüyor (yerel sağlayıcı).
- [ ] LM Studio 11434 portunu kullanıyorsa Ollama ile çakışma yok: iki sağlayıcı ayrı adreslerle çalışıyor.
- [ ] Durum çubuğu seçili sağlayıcının modelini gösteriyor (ör. LM Studio modeli, Ollama modeli değil).
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

## Canlı çözümleme

- [ ] Ayarlar → Konuşma Tanıma → "Canlı çözümleme parça süresi" varsayılan (20 sn) iken ~2 dk
      sürekli konuşulan bir dikte yapılır: overlay'de dalganın altında kayıt sürerken canlı
      transkript (son ~70 karakter) beliriyor ve konuştukça güncelleniyor.
- [ ] Kayıt durdurulunca bekleme süresi kısa kalıyor (tüm 2 dk'nın sonda tek seferde
      çözümlenmesini beklemek yerine, yalnızca son küçük parça bekleniyor).
- [ ] Sonuç metni eksiksiz ve parça sınırlarında kelime/cümle kopması yok.
- [ ] Parça süresi `0`'a (Kapalı) çekilince davranış eskisi gibi: overlay'de canlı metin
      görünmüyor, kayıt bitince tek seferde çözümleniyor.
- [ ] Kısa bir dikte (birkaç saniye, parça süresinden kısa) normal çalışıyor — canlı çözümleme
      hiç tetiklenmese de sonuç eksiksiz geliyor.

## Bas-konuş / tıkla-aç (Windows)

- [ ] Kısayolu 1 sn basılı tut → bırakınca çözümleme başlıyor (bas-konuş).
- [ ] Kısayola kısa basıp bırak → normal aç/kapat gibi davranıyor (tıkla-aç).
- [ ] Ayarlar → Genel → "Bas-konuş" kapatılınca kısayol her zaman aç/kapat olarak çalışıyor.

## Özel sözlük

- [ ] Ayarlar → Sözlük'e "Kubernetes" (yanlış biçim: "kuber netes") eklenip kaydedilince,
      diktede "kuber netes" denince sonuçta "Kubernetes" çıkıyor (LLM kapalıyken bile).
- [ ] Sözlükteki terimler LLM açıkken düzeltme kalitesini gözle görülür şekilde artırıyor
      (ör. nadir özel adlar artık yanlış tahmin edilmiyor).
- [ ] Boş terimli bir satırla kaydetmeye çalışınca "Sözlükte boş terim var" hatası çıkıyor.

## Elle düzenleme ve yeniden yapıştırma

- [ ] Sonuç penceresinde düzeltilmiş metni değiştirip 800 ms bekleyince düzenleme geçmişteki
      kayda yansıyor (geçmiş kaydı büyümüyor, aynı satır güncelleniyor).
- [ ] Araç çubuğu → "Yeniden yapıştır" (Ctrl+Enter): pencere gizlenip metin tekrar aktif
      pencereye yapıştırılıyor.
- [ ] Tek kelimelik bir düzeltme yapılınca (ör. "çuk" → "çok") alt çubukta "Sözlüğe ekle" önerisi
      çıkıyor; "Sözlüğe ekle" tıklanınca terim Ayarlar → Sözlük'e ekleniyor.
- [ ] "Yok say" tıklanınca öneri çubuğu kapanıyor, sözlüğe hiçbir şey eklenmiyor.
- [ ] Ayarlar → Genel → "Elle düzeltmelerden tek kelimelik sözlük önerisi çıkar" kapatılınca
      öneri çubuğu hiç görünmüyor.

## İnceleme sonrası eklenenler (yalnızca gerçek cihazda doğrulanabilir)

- [ ] Windows: dikte sonrası `Win+V` pano geçmişinde dikte metni görünmüyor (Ayarlar → Genel →
      "Pano geçmişinden hariç tut" açıkken); kapatınca görünüyor.
- [ ] "Eski pano içeriğini geri yükle" açıkken yapıştırmadan hemen sonra başka bir şey
      kopyalanınca yeni kopya ezilmiyor.
- [ ] Windows `.[media]` kurulu, Spotify/YouTube çalarken "Kayıtta medyayı duraklat" açık:
      kayıt başlayınca duruyor, bitince devam ediyor; hiçbir şey çalmıyorken kayıt başlatınca
      oynatma **başlamıyor**. Linux'ta aynısı `playerctl` ile.
- [ ] Profilde "Yazarak" yapıştırma: çok satırlı metin Windows'ta Shift+Enter ile satır atlıyor
      (sohbet uygulamasında mesaj erken gönderilmiyor); Linux'ta 500+ karakterlik metin yarıda
      kesilmiyor.
- [ ] Kayıt sırasında USB mikrofon çıkarılınca kayıt duruyor ve hata bildiriliyor; mikrofon
      sessize alınınca ~3 sn sonra overlay'de "Mikrofondan ses gelmiyor" uyarısı çıkıyor.
- [ ] Windows: Ayarlar → Ses'te bir WASAPI mikrofonu seçip (cihaz 48 kHz'de) kayıt başlıyor ve
      metin çıkıyor (16 kHz'e auto_convert); seçili cihaz açılamazsa varsayılan mikrofonla
      sürüp uyarı veriyor.
- [ ] Başarısız bir kayıttan sonra yanlışlıkla boş bir kayıt yapınca "yeniden dene" hâlâ
      önceki (konuşmalı) kaydı çözümlüyor.
- [ ] Kayıtlı USB mikrofon takılı değilken açılışta varsayılan mikrofon kullanılıyor ve uyarı
      veriliyor; Ayarlar → Ses'te "(bulunamadı)" görünüyor.
- [ ] Sessiz/boş bir kayıttan sonra tepsi → "Başarısız kaydı yeniden dene" etkin; tıklayınca
      aynı ses yeniden çözümleniyor.
- [ ] "Geri al" diye tek başına dikte edince önceki yapıştırma hedef uygulamada geri alınıyor.
- [ ] Overlay sürüklenip bırakılınca sonraki kayıtta aynı yerde açılıyor.
- [ ] Linux: ikinci bir kullanıcı oturumunda `dikte --toggle` kendi örneğini tetikliyor.
- [ ] Linux: otomatik başlatmayla (başlatıcı olmadan) açılan uygulama GPU'da modeli yüklüyor.
- [ ] Paketlenmiş `Dikte.exe --version` sürümü yazıp 0 ile çıkıyor; açılışta ve Ayarlar
      açılırken konsol penceresi yanıp sönmüyor.
- [ ] Kurulum paketiyle (Dikte-Setup) kurulan uygulamada "Kayıt sırasında çalan medyayı
      duraklat" açıkken Spotify/YouTube kayıtta duruyor, bitince devam ediyor (winrt pakette).
- [ ] Geçmiş panelinden ve sonuç panellerinden kopyalanan metin `Win+V` pano geçmişinde görünmüyor
      ("pano geçmişine alma" ayarı açıkken).
- [ ] Ayarlar → Hakkında → "Durum kontrolü…": Ollama kapalıyken "Ollama'yı başlat" düğmesi çıkıyor.
- [ ] Uzun bir dosya çözümlenirken Ayarlar'da Whisper modeli değiştirilip Kaydet'e basınca
      arayüz donmuyor; çözümleme bitince yeni model yükleniyor.

## Kod incelemesi düzeltmeleri (gerçek cihazda doğrulanmalı)

- [ ] Windows 11, Python 3.13 venv: `pip install ".[media]"`, Spotify/YouTube çalarken kayıt
      başlat: medya duruyor, bitince devam ediyor. Aynısını PyInstaller paketiyle dene (winrt,
      `msvcp140.dll` ve `foundation.collections` pakette).
- [ ] Windows: Ctrl+Alt'lı bas-konuş kısayolu; sonuç gelirken tuşları basılı tut: `Ctrl+V`
      yapıştırıyor (`Ctrl+Alt+V` değil); Win/Alt bırakılınca Başlat menüsü ve menü çubuğu açılmıyor.
- [ ] Windows: Dikte'yi yönetici olarak, sonra ikinci kez normal başlat: tek örnek/IPC davranışı
      ve gerekiyorsa uyarı görünüyor.
- [ ] Windows: aynı kullanıcıdan `dikte --toggle` çalışıyor; başka bir kullanıcı hesabının
      açtığı pipe reddediliyor.
- [ ] Windows: Ayarlar ve diyalog düğmeleri Türkçe (Tamam/İptal/Evet/Hayır); paketlenmiş
      sürümde de.
- [ ] Kayıt ya da çözümleme sürerken oturumu kapat / Windows'u yeniden başlat: mikrofon
      göstergesi sönüyor, kapanış takılmıyor, duraklatılan medya sürüyor.
- [ ] Hakkında → Durum kontrolü → Modeli indir; indirme sürerken Ayarlar'ı kapat: çökme yok,
      model indikten sonra yükleniyor.
- [ ] Otomatik yapıştırma + "pencereyi öne getir" açık, Not Defteri'ne dikte: metin bir kez Not
      Defteri'ne yapışıyor, pencere sonra öne geliyor, sonuç penceresinde metin ikilenmiyor.
- [ ] "Eski panoyu geri yükle" açıkken Teams/Outlook/Word'e uzun metin dikte: dikte metni
      yapışıyor, eski pano içeriği yapışmıyor; ardından eski pano geri geliyor.
- [ ] RDP (mstsc), Hyper-V/VirtualBox penceresine ve `Ctrl+Shift+V` profilli Windows
      Terminal'e dikte: eski pano geri yüklenmiyor.
- [ ] Bir uygulama panoyu kilitli tutarken dikte: yapıştırma yapılmıyor, bildirim çıkıyor.
- [ ] "Tuş tuş yaz" profiliyle 2000+ karakterlik dikte: arayüz donmuyor; araç yoksa ya da zaman
      aşımında bildirim çıkıyor; Linux'ta `ps aux` metni göstermiyor.
- [ ] Başka uygulamanın kullandığı bir çeviri kısayolunu ata: bildirim çıkıyor, önceki çeviri
      kısayolu çalışmaya devam ediyor.
- [ ] Gerçek mikrofonla canlı parçalamada kaydı iptal edip hemen yeniden başlat: eski konuşma
      yeni metne karışmıyor.
- [ ] Linux Wayland (KDE/Sway): yapıştırma ve "tuş tuş yaz" `wtype` ile; Türkçe karakterler ve
      çok satırlı metin doğru.
- [ ] Linux Wayland (GNOME): otomatik yapıştırma "yapılamadı" bildiriyor, metin panoda; profil
      "bilinmiyor" uyarısı bir kez çıkıyor.
- [ ] Linux, `XDG_RUNTIME_DIR` yokken: `/tmp/dikte-<uid>` 0700 oluşuyor ve `dikte --toggle` çalışıyor.
