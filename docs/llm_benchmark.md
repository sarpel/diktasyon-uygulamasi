# Türkçe LLM düzeltme benchmark'ı

<!-- LAST-SYNCED: 2026-09-15 -->

**Durum:** yöntem ve veri seti hazır, **ölçüm henüz yapılmadı.** Bu makinede (WSL) `ollama`
komutu kurulu değil; 11434 portunu LM Studio kullanıyor, dolayısıyla Ollama başka bir porta
alınmalı ve adres `--host` ile verilmelidir. Betik şu an yalnızca Ollama üzerinden ölçer
(`_ollama_factory`); LM Studio ile ölçüm istenirse OpenAI-uyumlu bir fabrika eklenmelidir.
Ayrıca aday model listesi kullanıcı onayı almadan indirilmeyecektir.

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

Ollama farklı bir porttaysa: `--host http://127.0.0.1:11500`.

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

`scripts/eval_llm.py` çalıştırıldığında `render_markdown` çıktısı (Model · Puan/10 ·
kategori kırılımı · ortalama gecikme · hata sayısı) aşağıdaki işaretli bölümün içine
yazılır (`_write_results`); yukarıdaki yöntem ve aday-onay metni korunur. En yüksek puanlı
model `LlmSettings.model` varsayılanı olacaktır.

<!-- RESULTS:BEGIN -->

45 örnek · 2 tur

| Model | Puan/10 | yazim | baglam | teknik_koru | noktalama | anlam_koru | bos_degisiklik | Ort. gecikme | Hata |
|---|---|---|---|---|---|---|---|---|---|
| gemma4:e4b-it-qat | **9.02** | 8.75 | 7.0 | 10.0 | 9.29 | 9.29 | 10.0 | 1.96 sn | 7 |
| qwen3.5:4b | **7.37** | 9.0 | 4.88 | 8.62 | 9.29 | 7.36 | 5.0 | 2.44 sn | 7 |

<!-- RESULTS:END -->
