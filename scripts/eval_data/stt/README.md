# STT benchmark verisi

Bu klasöre ses dosyaları **konmaz** (repo boyutunu şişirir, telifi belirsizdir). Yalnızca
`manifest.json` ve bu README repoda tutulur; ses dosyalarını kendi makinenizde ayrı bir
klasörde (ör. `scripts/eval_data/stt/audio/`, `.gitignore`'da) tutup `manifest.json`'da yola
işaret edin.

## Kayıt nasıl alınır

- 16 kHz, mono, WAV (faster-whisper zaten yeniden örnekler; 16 kHz vermek gecikmeyi azaltır).
- 20 kayıt önerilir: gündelik cümleler, teknik terimler (ör. "Kubernetes", "Docker Compose"),
  kısa sessizlikli doğal duraksamalar, en az birkaçı arka plan gürültülü.
- Her kayıt 5–20 saniye arası, tek bir konuşmacı.
- Referans metni (`manifest.json`'daki `text`) kaydı dinleyip **elle, tam ve doğru noktalamayla**
  yazın; WER karşılaştırması bu referansa göre yapılır.

**Alternatif: Common Voice TR.** Kendi kaydınız yoksa Mozilla Common Voice'un Türkçe
alt kümesinden (CC0/CC-BY lisanslı, `commonvoice.mozilla.org`) 20 kısa klip indirip aynı
formatta bir `manifest.json` oluşturabilirsiniz.

## `manifest.json` formatı

```json
[
  {"file": "/mutlak/veya/betiğe-göre/yol/kayit-01.wav", "text": "Bugün hava çok güzel."},
  {"file": "/mutlak/veya/betiğe-göre/yol/kayit-02.wav", "text": "Docker Compose ile başlattım."}
]
```

- `file`: ses dosyasının yolu (mutlak önerilir; betik `Path(file)` olarak açar).
- `text`: o kaydın doğru, tam transkripsiyonu (WER referansı).

Çalıştırma:

```bash
.venv/bin/python scripts/eval_stt.py --manifest scripts/eval_data/stt/manifest.json \
    --beam 1,2,5 --cond true,false --write
```
