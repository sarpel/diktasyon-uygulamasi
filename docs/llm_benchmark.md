# Türkçe LLM düzeltme benchmark'ı

**Durum:** yöntem ve veri seti hazır, **ölçüm henüz yapılmadı.** Bu makinede (WSL) `ollama`
komutu kurulu değil ve `127.0.0.1:11434` yanıt vermiyor. Ayrıca aday model listesi
kullanıcı onayı almadan indirilmeyecektir.

## Neyi ölçüyor

Veri seti: `scripts/eval_data/tr_corrections.json` — **45 örnek**, altı kategori:

| Kategori | Ne sınar | Örnek |
|---|---|---|
| `yazim` | Bilerek yerleştirilmiş fonetik/bitişiklik hataları | "hava çuk güzel" → "çok güzel" |
| `baglam` | Yalnızca bağlamdan çözülebilen ekler | "yarın gel cek" → "gelecek" |
| `teknik_koru` | Teknik terimlerin doğru yazımı | "docker kompoz" → "docker compose" |
| `noktalama` | Noktalama ve büyük harf | "merhaba nasılsın" → "Merhaba, nasılsın?" |
| `anlam_koru` | Zaten doğru cümleyi bozmama | değişiklik oranı ≤ 0,05 |
| `bos_degisiklik` | Doğru metne gereksiz müdahale etmeme | `changes` boş olmalı |

## Puanlama

Örnek başına 0–1 arası:

```
score = 0,60 × (geçen must_contain / toplam)
      + 0,25 × (yasak ifade yoksa 1)
      + 0,15 × (aşırı düzenleme yoksa 1)
```

- Geçersiz JSON veya sağlayıcı hatası → **0 puan** (tur durmaz).
- Aşırı düzenleme: `difflib.SequenceMatcher` ile `1 − ratio > max_change_ratio`.
- `must_contain` içinde `"a|b"` alternatif demektir; biri yeterlidir.
- Model puanı = 10 × örneklerin ortalaması.
- **Gecikme puana girmez**; ayrı sütundur ve yalnızca eşitlikte (±0,3) belirleyicidir.

## Nasıl çalıştırılır

```bash
.venv/bin/python scripts/eval_llm.py --models qwen3.5:4b gemma4:e4b-it-qat --runs 2
```

`--keep-alive 0` (varsayılan) her modelden sonra VRAM'i boşaltır; 8 GB'lık kartta modeller
birbirini ezmez.

## Aday seçimi (çalıştırılmadan önce)

1. `ollama list` ile kurulu modeller yazılır.
2. Ollama kütüphanesinden **son altı ayda yayımlanmış**, ağırlığı ≤ 6 GB (q4 seviyesi) ve
   Türkçe desteği bilinen aileler listelenir — Whisper `large-v3-turbo` ile aynı 8 GB'ı
   paylaşacağı için üst sınır budur.
3. Liste bu belgenin başına "Adaylar ve neden" bölümü olarak yazılır, **kullanıcı onayı
   alınır**, ancak ondan sonra `ollama pull` çalıştırılır.

## Sonuç tablosu

Ölçüm yapıldığında buraya `render_markdown` çıktısı (Model · Puan/10 · kategori kırılımı ·
ortalama gecikme · hata sayısı) yazılacak ve en yüksek puanlı model `LlmSettings.model`
varsayılanı olacaktır.
