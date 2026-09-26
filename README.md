# Dikte

[![CI](https://github.com/sarpel/diktasyon-uygulamasi/actions/workflows/ci.yml/badge.svg)](https://github.com/sarpel/diktasyon-uygulamasi/actions/workflows/ci.yml)
[![Lisans: MIT](https://img.shields.io/badge/lisans-MIT-blue.svg)](LICENSE)
![Python 3.11–3.12](https://img.shields.io/badge/python-3.11%20%7C%203.12-blue.svg)
![Platform](https://img.shields.io/badge/platform-Windows%2011%20%7C%20Linux-lightgrey.svg)

**Türkçe odaklı, tamamen yerel çalışan masaüstü diktasyon uygulaması.**
Bir kısayola basın, konuşun, tekrar basın: sesiniz GPU'da metne çevrilir, isteğe bağlı olarak
yerel bir LLM ile düzeltilir ve çalıştığınız pencereye yapıştırılır. Ses ve metin varsayılan
olarak bilgisayarınızdan çıkmaz.

*English summary: [README.en.md](README.en.md)*

## Özellikler

- **Yerel ve hızlı STT:** [faster-whisper](https://github.com/SYSTRAN/faster-whisper)
  `large-v3-turbo`, NVIDIA GPU üzerinde. Uzun kayıtlarda kayıt sürerken **canlı, parça parça
  çözümleme**; kayıt bitince bekleme süresi neredeyse sabit.
- **LLM ile düzeltme (isteğe bağlı):** Yanlış tanınan kelimeler, noktalama ve büyük harfler
  yerel Ollama (`gemma4:e4b-it-qat`) ile düzeltilir. LM Studio, OpenAI, Anthropic, Gemini veya
  kendi uç noktanız da seçilebilir. LLM tamamen kapatılabilir.
- **İngilizce çeviri ve agent prompt'u:** Dikteyi tek tuşla İngilizceye çevirin ya da bir AI
  kodlama ajanı için yapılandırılmış bir prompt'a dönüştürün.
- **Doğrudan yapıştırma:** Sonuç panoya yazılır ve aktif pencereye yapıştırılır; eski pano
  içeriği geri yüklenebilir, Windows pano geçmişine girmez.
- **Özel sözlük:** Terimleriniz Whisper'a ipucu, LLM'e sözlük ve kural tabanlı düzeltme olarak üç
  katmanda uygulanır.
- **Sesli komutlar:** "yeni satır", "yeni paragraf", "son cümleyi sil", "son kelimeyi sil", "geri al".
- **Uygulama profilleri:** Ön plandaki uygulamaya göre mod, yapıştırma tuşu ve LLM kullanımı.
- **Halüsinasyon koruması:** Sessiz kayıtta model hiç çağrılmaz; bilinen Whisper uydurmaları elenir.
- **Kullanım kolaylıkları:** bas-konuş, sessizlikte otomatik durdurma, kayıtta medyayı duraklatma,
  aranabilir geçmiş, başarısız kaydı yeniden deneme, ses dosyası sürükle-bırak, ilk açılışta
  durum kontrolü ve tek tıkla model indirme.

## Gereksinimler

- Windows 11 (birincil) veya Linux (X11 / Wayland)
- **CUDA destekli NVIDIA GPU** ve güncel sürücü (≥ 525). CPU'da çalışmaz.
  Hedef donanım: RTX 3060 Ti 8 GB (Whisper ≈ 1,6 GB VRAM + yerel LLM ≈ 4 GB)
- İsteğe bağlı: metin düzeltme için [Ollama](https://ollama.com) veya başka bir LLM sağlayıcısı

## Hızlı kurulum

**Windows:** [Releases](https://github.com/sarpel/diktasyon-uygulamasi/releases) sayfasından
`Dikte-Setup-<sürüm>.exe`'yi indirip çalıştırın. İlk açılışta "Durum kontrolü" penceresinden
Whisper modelini indirin (~1,6 GB).

**Linux:**

```bash
sudo apt install python3.11 python3.11-venv libportaudio2 pipx xdotool
git clone https://github.com/sarpel/diktasyon-uygulamasi.git && cd diktasyon-uygulamasi
./packaging/linux/install.sh
```

Ardından masaüstü ortamınızın kısayol ayarına `dikte --toggle` komutunu bağlayın.

**LLM düzeltmesi için (isteğe bağlı):**

```bash
ollama pull gemma4:e4b-it-qat
```

Kaynaktan kurulum, extra'lar, kaldırma ve sorun giderme: **[docs/INSTALL.md](docs/INSTALL.md)**.

## Hızlı başlangıç

| Eylem | Nasıl |
|---|---|
| Kaydı başlat / durdur | `Ctrl+Alt+Space` (Windows) · `dikte --toggle` (Linux) |
| İptal | `Esc` veya overlay'deki "Vazgeç" |
| Ayarlar | Tray menüsü → "Ayarlar…" veya `Ctrl+,` |
| Geçmiş | `Ctrl+H`, aramak için `Ctrl+F` |

Tüm kısayollar, ayarlar, sağlayıcılar, profiller ve komut satırı: **[docs/USAGE.md](docs/USAGE.md)**.

## Gizlilik

- STT her zaman yerel GPU'da çalışır. Varsayılan LLM (Ollama) da yereldir.
- Uzak bir LLM sağlayıcısı seçerseniz yalnızca dikte metni o servise gönderilir; ses gönderilmez.
- API anahtarları yalnızca ortam değişkenlerinden okunur; diske yazılmaz, loglanmaz.
- Telemetri yoktur. Ağ erişimi yalnızca model indirme ve seçtiğiniz LLM sağlayıcısı içindir.

Veri konumları ve saklama ayarları: [docs/USAGE.md → Veri ve gizlilik](docs/USAGE.md#veri-ve-gizlilik).

## Belgeler

| Belge | İçerik |
|---|---|
| [docs/INSTALL.md](docs/INSTALL.md) | Kurulum, güncelleme, kaldırma, sorun giderme |
| [docs/USAGE.md](docs/USAGE.md) | Kullanım kılavuzu ve tüm ayarlar |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Geliştirme ortamı, mimari, test ve katkı kuralları |
| [CHANGELOG.md](CHANGELOG.md) | Sürüm notları |
| [docs/llm_benchmark.md](docs/llm_benchmark.md) | Türkçe LLM düzeltme benchmark'ı (varsayılan modelin seçimi) |
| [docs/stt_benchmark.md](docs/stt_benchmark.md) | Türkçe STT (WER) benchmark yöntemi |
| [docs/manual_test_checklist.md](docs/manual_test_checklist.md) | Gerçek cihazda manuel test listesi |
| [SECURITY.md](SECURITY.md) | Güvenlik açığı bildirme |
| [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) | Üçüncü taraf bileşenlerin lisansları |

## Katkı

Hata bildirimi, öneri ve pull request'ler memnuniyetle karşılanır. Başlamadan önce
[CONTRIBUTING.md](CONTRIBUTING.md) ve [davranış kurallarına](CODE_OF_CONDUCT.md) göz atın.

## Lisans

[MIT](LICENSE) © Sarpel GÜRAY. Dağıtılan kurulum paketi, kendi lisanslarıyla gelen üçüncü taraf
bileşenler içerir; bkz. [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
