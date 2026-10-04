# Kullanım kılavuzu

Dikte'nin günlük kullanımı, ayarları ve ileri özellikleri. Kurulum için bkz.
[INSTALL.md](INSTALL.md).

## İçindekiler

- [Temel akış](#temel-akış)
- [Kısayollar ve eylemler](#kısayollar-ve-eylemler)
- [Sonuç nasıl teslim edilir](#sonuç-nasıl-teslim-edilir)
- [Canlı çözümleme](#canlı-çözümleme)
- [Halüsinasyon ve sessizlik](#halüsinasyon-ve-sessizlik)
- [LLM sağlayıcıları](#llm-sağlayıcıları)
- [Ayarlar](#ayarlar)
- [Özel sözlük](#özel-sözlük)
- [Sesli komutlar](#sesli-komutlar)
- [Ses dosyası çözümleme](#ses-dosyası-çözümleme)
- [Uygulama profilleri](#uygulama-profilleri)
- [Komut satırı](#komut-satırı)
- [Veri ve gizlilik](#veri-ve-gizlilik)

## Temel akış

1. Dikte tray'de (sistem tepsisi) sürekli açık durur.
2. Kısayola basarsınız (Windows varsayılanı `Ctrl+Alt+Space`) → ekranda küçük bir kayıt
   penceresi (overlay) açılır; konuşurken dikenleri sesle uzayan dönen bir küre (ya da Ayarlar →
   Genel → "Kayıt göstergesi" ile seçilirse çubuk dalga) hareket eder.
3. Tekrar basınca kayıt durur; ses GPU'da metne çevrilir, isteğe bağlı olarak LLM ile düzeltilir.
4. Metin panoya yazılır ve çalıştığınız pencereye yapıştırılır.

İlk açılışta (veya GPU / Whisper modeli / LLM bağlantısında sorun varsa) **"Durum kontrolü"**
penceresi açılır: her öğe için ✓/✗, bir ipucu ve gerekiyorsa tek tıkla çözüm ("Modeli indir",
"Ollama'yı başlat"). Aynı pencere Ayarlar → Hakkında → **"Durum kontrolü…"** ile de açılır.

## Kısayollar ve eylemler

| Eylem | Kısayol / yer |
|---|---|
| Kaydı başlat / durdur | Windows: `Ctrl+Alt+Space` (ayarlardan değiştirilebilir) · Linux: `dikte --toggle`'a bağladığınız tuş |
| Bas-konuş (Windows) | Kısayolu basılı tutun, bırakınca çözümlenir; kısa basış aç/kapat olarak çalışır (Ayarlar → Genel → "Bas-konuş"). Linux'ta `dikte --start` / `dikte --stop` komutlarını tuşa basma/bırakmaya bağlayın |
| Düzeltilmiş metni kopyala | Panelin sağ üstündeki kopyala ikonu veya `Ctrl+Shift+C` |
| İngilizce çeviri | Alt araç çubuğu → "İngilizce'ye Çevir" · veya Ayarlar → Genel'de ayrı bir kısayol (Linux: `dikte --toggle --mode translate`) |
| Agent prompt'u | Alt araç çubuğu → "Agent Prompt'a Dönüştür" · veya Ayarlar → Genel'de ayrı bir kısayol (Linux: `dikte --toggle --mode prompt`) |
| Kaydı/çözümlemeyi iptal et | `Esc` (Windows'ta global) · overlay veya araç çubuğunda "Vazgeç" · tray menüsü |
| Ayarları aç | Araç çubuğu → "Ayarlar…" veya `Ctrl+,` |
| Geçmiş panelini aç/kapat | Araç çubuğu → "Geçmiş" veya `Ctrl+H` |
| Geçmişte ara | `Ctrl+F` (paneli açar ve arama kutusuna odaklanır) |
| Geçmişi dışa aktar | Geçmiş paneli → "Dışa aktar…" (`.md` → Markdown, `.txt` → düz metin; her oturumun teslim edilen metni: çeviri/prompt modunda o çıktı) |
| Son diktenin metnini kopyala | Tray menüsü → "Son metni kopyala" veya "Son dikteler" alt menüsü |
| Son sonucu yeniden yapıştır | Tray menüsü → "Son sonucu yapıştır" · veya Ayarlar → Genel'de ayrı bir kısayol (yalnızca Windows) |
| Başarısız kaydı yeniden dene | Tray menüsü → "Başarısız kaydı yeniden dene" (çözümleme hata verdiyse veya boş döndüyse ses saklanır) |
| Düzeltilmiş metni yeniden yapıştır | Metni elle düzenleyip `Ctrl+Enter` |
| Pencereyi gizle | `X` (uygulama tray'de kalır) |
| Çıkış | Tray menüsü → "Çıkış" |

Başlat/durdur/hata sesleri Ayarlar → Genel'den kapatılabilir. Aynı yerden, kayıt sırasında
çalan medyanın (YouTube, Spotify…) duraklatılması açılabilir: yalnızca o an çalan oynatıcılar
duraklatılır ve kayıt bitince sürdürülür (Linux'ta `playerctl` gerekir; Windows kurulum paketinde
hazırdır, kaynaktan kurulumda `.[media]` extra'sı gerekir).

Kayıt başladıktan sonra birkaç saniye mikrofondan hiç ses gelmezse overlay'de uyarı çıkar.
Kayıtlı mikrofon takılı değilse varsayılan mikrofon kullanılır ve bu bildirilir. Overlay'i
sürükleyip istediğiniz yere taşıyabilirsiniz; konum hatırlanır (Ayarlar → Genel → "Gösterge konumu").

## Sonuç nasıl teslim edilir

Kayıt bitip metin hazır olduğunda üç şey olur:

1. Düzeltilmiş metin **panoya** yazılır (Ayarlar → Genel → "Sonucu panoya kopyala").
2. Ön plandaki uygulama Dikte değilse metin oraya **Ctrl+V** ile yapıştırılır
   (Ayarlar → Genel → "Sonucu aktif pencereye yapıştır"). Windows'ta yerleşiktir; Linux'ta `xdotool`
   (X11) veya `wtype` (Wayland) kurulu olmalıdır, yoksa metin yalnızca panoda kalır. Wayland'de
   önce `wtype` denenir; GNOME gibi sanal klavye desteklemeyen ortamlarda yapıştırma yapılamaz,
   metin panodadır (`Ctrl+V` ile yapıştırın). Panoya yazılamazsa (başka bir uygulama panoyu
   kilitlediyse) yapıştırma hiç yapılmaz ve bildirim gösterilir.
3. Oturum **geçmişe** yazılır.

Ek davranışlar:

- "Yapıştırdıktan sonra eski pano içeriğini geri yükle" açıksa pano 2–5 sn sonra (metin
  uzadıkça daha geç) önceki içeriğine döner; yavaş uygulamalar dikte yerine eski içeriği
  yapıştırmasın diye beklenir. Bu arada yeni bir şey kopyaladıysanız geri yükleme yapılmaz.
  `Ctrl+Shift+V` profillerinde (terminaller) ve uzak masaüstü / sanal makine pencerelerinde
  (Uzak Masaüstü, Hyper-V, VirtualBox, VMware, Remmina…) hiç geri yükleme yapılmaz.
- Windows'ta dikte metni varsayılan olarak pano geçmişine (`Win+V`) ve bulut panosuna girmez
  (Ayarlar → Genel → "Dikte metnini pano geçmişine ve bulut eşitlemesine alma").
- Düzeltilmiş metni elle düzenleyip `Ctrl+Enter` ile yeniden yapıştırabilirsiniz; düzeltmeniz
  geçmişe yazılır ve tek kelimelik düzeltmeler için sözlüğe ekleme önerilir.
- Sonuç penceresi varsayılan olarak öne gelmez; odağınız çalıştığınız uygulamada kalır
  (Ayarlar → Genel → "Sonuçta pencereyi öne getir").

Kayıt süresi varsayılan olarak **sınırsızdır** (Ayarlar → Ses → "Kayıt süresi sınırı" = 0).
16 kHz float32 ham ses bellekte yaklaşık **230 MB/saat** yer tutar. Bir sınır girilirse süre
dolunca kayıt otomatik durur ve o ana kadarki ses çözümlenir.

## Canlı çözümleme

Uzun diktelerde tüm kaydı sonda tek seferde çözümlemek yerine, kayıt sürerken konuşma +
sessizlik biriktikçe **parça parça** çözümlenir (Ayarlar → Konuşma Tanıma → "Canlı çözümleme
parça süresi", varsayılan 20 sn, `0` = kapalı). Her parça, önceki parçaların metniyle birlikte
(bağlam olarak) çözümlenir ve overlay'de dalganın altında **canlı transkript** olarak görünür.

- Uzun bir dikte bittiğinde bekleme süresi neredeyse **sabit kalır**; yalnızca son küçük parça beklenir.
- Hiç susmadan konuşulursa parça **45 saniyede** (`live_max_chunk_s`) sessizlikten bağımsız bölünür.
- Kayıt durdurulduğunda henüz çözümlenmemiş parçalar da beklenir; metin eksik kalmaz.

Parça süresinden kısa kayıtlarda davranış değişmez: kayıt bitince tek seferde çözümlenir.

## Halüsinasyon ve sessizlik

Whisper, sessiz veya çok gürültülü parçalarda eğitim verisindeki altyazı kalıplarını tekrar
edebilir ("Altyazı M.K.", "İzlediğiniz için teşekkürler"). Dikte bunu üç katmanda engeller:

1. **Ön kontrol:** Kayıtta hiç konuşma yoksa (Silero VAD) model **hiç çağrılmaz**;
   "Konuşma algılanmadı" uyarısı verilir.
2. **Eşikler:** Çözümlemeye `no_speech_threshold`, `log_prob_threshold` ve
   `hallucination_silence_threshold` geçilir; düşük güvenli segmentler elenir.
3. **Kara liste:** Bilinen uydurma kalıplar yalnızca tek başına bir segmenti kapladığında atılır;
   gerçek bir cümlenin içinde geçtiğinde korunur.

Eşik önerileri (Ayarlar → Konuşma Tanıma → "Sessizlik ve halüsinasyon"):

| Ortam | VAD eşiği |
|---|---|
| Gürültülü (açık ofis, fan) | 0,60 |
| Normal | 0,50 (varsayılan) |
| Kısık / yumuşak ses | 0,35 |

VAD kapatılırsa toplu çözümleme de devre dışı kalır (toplu çözümleme konuşma aralıklarını VAD'den alır).

## LLM sağlayıcıları

Metin düzeltme varsayılan olarak yereldeki Ollama ile yapılır (`gemma4:e4b-it-qat`; ölçüm:
[llm_benchmark.md](llm_benchmark.md)). Yerel bir alternatif (LM Studio) veya uzak bir sağlayıcı
da seçilebilir:

| Sağlayıcı | Ortam değişkeni (varsayılan ad) | Kurulum (kaynak kurulumda) | Base URL |
|---|---|---|---|
| Ollama (yerel) | — | çekirdek | `http://127.0.0.1:11434` |
| LM Studio (yerel) | gerekmez (boş bırakın) | `.[openai]` | `http://127.0.0.1:1234/v1` |
| OpenAI | `OPENAI_API_KEY` | `.[openai]` | `https://api.openai.com/v1` |
| Anthropic | `ANTHROPIC_API_KEY` | `.[anthropic]` | — |
| Gemini | `GEMINI_API_KEY` | `.[gemini]` | — |
| Custom (OpenAI-uyumlu) | kendi belirlediğiniz ad (boş bırakılabilir) | `.[openai]` | ör. `http://localhost:1234/v1` |
| Custom (Anthropic-uyumlu) | kendi belirlediğiniz ad (boş bırakılabilir) | `.[anthropic]` | proxy adresiniz |

Windows kurulum paketi (`Dikte-Setup-*.exe`) tüm sağlayıcı SDK'larını içerir; ek kurulum gerekmez.

- Tablodaki adresler ilgili uygulamaların **varsayılan portlarıdır** (Ollama 11434, LM Studio 1234).
  Farklıysa Ayarlar → Metin Düzeltme → "Sunucu adresi" / "Temel URL" kutusundan değiştirin.
- LM Studio'da sunucuyu açmak için: Developer sekmesi → **Start Server**; "Model" kutusuna
  LM Studio'nun listelediği model kimliğini yazın.
- Özel uç noktanın protokolü Ayarlar → Metin Düzeltme → "Biçim" ile seçilir. OpenAI-uyumlu sunucu
  `json_schema` desteklemiyorsa otomatik olarak `json_object` moduna düşülür.
- Yanıt çıktı sınırına takılıp yarıda kesilirse yarım metin yapıştırılmaz; hata gösterilir.
- "Düzeltme metinden çok saparsa ham metni kullan" açıkken (varsayılan) model düzeltmek yerine
  cevap verdi ya da özetlediyse ham metne dönülür. Kontroller: kelime sayısı ham metnin 0,5–1,6
  katı olmalı ("ee", "şey" gibi dolgular sayılmaz); 4 kelimeden kısa diktelerde en fazla 2 kelime
  eklenebilir; ham metnin içerik kelimelerinin en az %40'ı düzeltmede korunmalıdır (birleşen ve
  yazımı düzeltilen kelimeler korunmuş sayılır). Çeviri ve prompt iyileştirmede boş ya da aşırı
  uzun yanıtlar reddedilir ve düzeltilmiş metin gösterilir.
- LLM tamamen kapatılabilir (Ayarlar → Metin Düzeltme → "LLM ile metin düzeltme"): ham metin
  doğrudan sonuç olur, ek VRAM kullanılmaz. Düşük VRAM'de `keep_alive` değerini `0` yaparak
  Ollama modelini her istekten sonra boşaltabilirsiniz.

**Gizlilik:** Uzak sağlayıcı seçtiğinizde dikte edilen metin ilgili servise gönderilir.
API anahtarları **yalnızca ortam değişkeninden** okunur; `config.json`'a yazılmaz, loglanmaz ve
arayüzde gösterilmez. Ayarlarda yalnızca "✓ tanımlı / ✗ yok" bilgisi görünür.

## Ayarlar

Ayarlar penceresi (tray menüsü veya araç çubuğu → "Ayarlar…") sekiz sekmeden oluşur:

| Sekme | İçerik |
|---|---|
| Genel | Kısayol (tuşa basarak yakalanır) + isteğe bağlı çeviri / agent-prompt / son sonucu yapıştır kısayolları, bas-konuş (yalnızca Windows), geçmiş kayıt sayısı ve saklama süresi, açılışta başlat, panoya kopyala / yapıştır / pencereyi öne getir, pano geçmişinden hariç tutma, kayıtta medyayı duraklat, başarısız diktelerin sesini sakla, gösterge (overlay) konumu ve kayıt göstergesi (Küre / Dalga), sesli komutlar, elle düzeltmelerden sözlük önerisi |
| Ses | Mikrofon (adıyla saklanır; Windows'ta WASAPI cihazları), kayıt süresi sınırı (0 = sınırsız), sessizlikte otomatik durdurma (0 = kapalı), sessiz mikrofon uyarısı, canlı seviye testi |
| Konuşma Tanıma | Whisper modeli, hassasiyet (compute_type), dil, toplu çözümleme, açılışta ısıtma, canlı çözümleme parça süresi, "Sessizlik ve halüsinasyon" (VAD eşiği, en kısa sessizlik, konuşma yok eşiği, kara liste) |
| Metin Düzeltme | LLM aç/kapa, sağlayıcı ve sağlayıcıya özel alanlar, bellekte tutma, sağlamlık kontrolü ("Düzeltme metinden çok saparsa ham metni kullan") |
| Sözlük | Özel terimler (doğru yazım + yanlış tanınan biçimler), LLM düzeltmesine ek serbest talimat |
| Gelişmiş | beam_size, başlangıç promptu, num_ctx, top_p, top_k, zaman aşımı, düşünme modu |
| Profiller | Ön plandaki uygulamaya göre mod / yapıştırma / LLM / sonek profilleri |
| Hakkında | Sürümler, GPU ve desteklenen hassasiyetler, VRAM kullanımı (`nvidia-smi`), log / ayar klasörünü aç, durum kontrolü |

- Ayar değişiklikleri yeniden başlatma gerektirmez. Model/hassasiyet değişince model arka planda
  yeniden yüklenir (süren bir iş varsa iş bitince); mikrofon değişikliği sonraki kayıtta geçerlidir.
- Alanların açıklaması, fare üstüne gelince ipucu olarak görünür.
- Konuşma Tanıma, Metin Düzeltme ve Gelişmiş sekmelerinde "Varsayılanlara döndür" düğmesi vardır.
- `config.json` içindeki kısayol bozuksa uygulama çökmez, varsayılana döner ve bunu bildirir.
  Başka bir alan geçersizse yalnızca o alan varsayılana döner; diğer ayarlarınız korunur, eski
  dosya `config.json.bak` olarak yedeklenir ve hangi alanların atlandığı bildirilir.
- `float16` için GPU'nun Compute Capability değeri ≥ 7.0 olmalıdır (RTX 20xx ve üzeri). Daha eski
  kartlarda motor otomatik olarak desteklenen bir hassasiyete (`float32`) düşer ve uyarı gösterir.

## Özel sözlük

Ayarlar → Sözlük'te eklenen her terim üç katmanda devreye girer:

1. **Whisper hotwords + başlangıç promptu:** Terimler modelin doğru yazımı tanıma olasılığını artırır.
2. **LLM sözlüğü:** Terimler ve "Ek talimat" alanı, düzeltme talimatına "Sözlük (doğru yazımlar): …"
   bloğu olarak eklenir.
3. **Kural tabanlı düzeltme:** Her terimin "yanlış tanınan biçimler" listesindeki her varyant, ham
   metinde tam kelime eşleşmesiyle (büyük/küçük harf duyarsız) doğru yazımla değiştirilir.
   LLM kapalıyken bile çalışır.

## Sesli komutlar

Ham metin, sözlük kurallarından sonra sesli komutlar için taranır (Ayarlar → Genel → "Sesli
komutları tanı"; büyük/küçük harf duyarsız, komut etrafındaki virgül/nokta temizlenir):

- **"yeni satır"** → satır sonu ekler, sonrasındaki ilk harfi büyütür.
- **"yeni paragraf"** → boş satırla ayrılan yeni bir paragraf başlatır.
- **"son cümleyi sil"** → komutu ve ondan önceki cümleyi siler. "14.30" veya "3. madde" gibi
  rakamlı noktalar cümle sonu sayılmaz.
- **"son kelimeyi sil"** → komutu ve ondan önceki kelimeyi siler.
- **"geri al"** → dikte yalnızca bu iki kelimeden oluşuyorsa metin yapıştırılmaz; ön plandaki
  uygulamaya `Ctrl+Z` gönderilir (ör. az önce yapıştırılan metni geri almak için).

Örnek: "bugün hava güzel son cümleyi sil yarın yağmur var" → "Yarın yağmur var".

Noktalama komutları ("noktalı virgül" gibi) bilinçli olarak desteklenmez: Türkçede bu ifadeler
gerçek kelime olarak da geçer ve yanlışlıkla komut sanılabilir.

## Ses dosyası çözümleme

Hazır bir ses dosyasını da çözümletebilirsiniz:

- Araç çubuğu → **"Dosya aç…"** ile dosya seçin, veya
- Dosyayı sonuç penceresinin üzerine **sürükleyip bırakın**
  (`.wav`, `.mp3`, `.m4a`, `.ogg`, `.flac`, `.webm`, `.mp4`, `.opus`).

Süren bir kayıt/çözümleme varsa yeni dosya kabul edilmez. Sonuç, mikrofon kaydındaki tüm
adımlardan (sözlük, sesli komutlar, LLM) geçer; tek fark **panoya kopyalanır ama otomatik
yapıştırılmaz**.

## Uygulama profilleri

Ayarlar → Profiller'de, kısayola bastığınız anda **ön plandaki uygulamanın sürecine göre** mod,
yapıştırma tuşu, LLM düzeltmesi ve sonek değiştirilebilir:

| Alan | Anlamı |
|---|---|
| Ad | Listede tanımak için; boş bırakılamaz |
| Eşleşme | Süreç adı (`.exe` yazılabilir de, yazılmayabilir de) veya içinde aranan alt dize, ör. `code`, `windowsterminal` |
| Mod | Düzelt / Çevir / Prompt. Yalnızca kısayol "düzelt" modundaysa devreye girer; ayrı çeviri/prompt kısayolları profille geçersiz kılınmaz |
| Yapıştırma | `ctrl+v`, `ctrl+shift+v` (bazı terminaller) veya `type` (panoyu kullanmadan karakter karakter yazar; satır sonları `Shift+Enter` ile gönderilir) |
| LLM | Kapatılırsa bu uygulamada ham metin doğrudan teslim edilir |

Wayland oturumlarında etkin uygulama güvenilir biçimde algılanamaz; bu yüzden profiller
uygulanmaz, varsayılan ayarlar kullanılır ve durum bir kez bildirilir. "Tuş tuş yaz" yarıda
kalırsa ya da hedefe ulaştığı doğrulanamazsa metin panodadır ve bildirim gösterilir.
| Sonek | Sonuca eklenecek `(yok)` / `boşluk` / `yeni satır` |

Birden fazla profil eşleşirse önce süreç adıyla **tam eşleşen**, yoksa **en uzun alt dizeyle**
eşleşen kazanır (`code` profili `vscode`'u da yakalar ama `vscode` profili varsa o seçilir);
eşitlikte listede önce gelen kazanır. Eşleşme alanı boş bir profil hiçbir zaman eşleşmez.

Örnekler:

- **Windows Terminal:** Eşleşme=`windowsterminal`, Yapıştırma=`ctrl+shift+v`.
- **LLM'siz hızlı not:** Eşleşme=`notepad`, LLM=kapalı.

Ön plan sürecinin adı Windows'ta Win32 API ile, Linux'ta `xdotool` (yalnızca X11) ile okunur.
Araç yoksa veya sorgu başarısız olursa profil eşleştirme sessizce atlanır ve genel ayarlar
geçerli olur. Hiç profil tanımlı değilse ön plan sürecine bakılmaz.

## Komut satırı

```text
dikte [--minimized] [--toggle | --start | --stop] [--mode {correct,translate,prompt}] [--version]
```

| Seçenek | Anlamı |
|---|---|
| `--minimized` | Pencere açmadan tray'de başla (otomatik başlatma bunu kullanır) |
| `--toggle` | Çalışan örnekte kaydı başlat/durdur. Uygulama açık değilse hata verip 1 döner |
| `--start` / `--stop` | Çalışan örnekte kaydı başlat / durdur (Linux'ta bas-konuş için) |
| `--mode` | `--toggle`/`--start` ile birlikte: sonucu doğrudan bu modda üretir (varsayılan `correct`) |
| `--version` | Sürümü yazıp çıkar |

Komutlar çalışan örneğe kullanıcıya özel yerel bir soket üzerinden gider; aynı makinedeki başka
bir kullanıcının Dikte'sini tetiklemez.

## Veri ve gizlilik

- Ses ve metin varsayılan olarak **makineden çıkmaz**: STT yerel GPU'da, düzeltme yerel Ollama'da
  yapılır. Yalnızca uzak bir LLM sağlayıcısı seçerseniz metin o servise gider.
- Uygulama telemetri toplamaz. Ağ erişimi yalnızca model indirme (Hugging Face) ve seçtiğiniz LLM
  sağlayıcısı içindir.

| Veri | Windows | Linux |
|---|---|---|
| Ayarlar (`config.json`) | `%APPDATA%\Dikte\` | `~/.config/Dikte/` |
| Geçmiş (`history.jsonl`) | `%APPDATA%\Dikte\` | `~/.config/Dikte/` |
| Log (`dikte.log`) | `%APPDATA%\Dikte\` | `~/.config/Dikte/` |
| Son başarısız kayıt (`failed/last.wav`) | `%APPDATA%\Dikte\` | `~/.config/Dikte/` |
| Whisper modeli | `%LOCALAPPDATA%\Dikte\models\` | `~/.cache/Dikte/models/` |

- Linux'ta veri klasörleri yalnızca sahibinin okuyabileceği izinle (`0700`) oluşturulur.
- Geçmiş için kayıt sayısı sınırı ve saklama süresi (gün) Ayarlar → Genel'den ayarlanır; süresi
  dolan kayıtlar açılışta ve ayar değişince diskten silinir.
- Başarısız kaydın saklanmasını Ayarlar → Genel → "Başarısız diktelerin sesini sakla" ile kapatabilirsiniz.
