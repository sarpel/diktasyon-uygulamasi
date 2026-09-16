# Türkçe STT benchmark'ı

**Durum:** yöntem ve betik hazır, **ölçüm henüz yapılmadı (GPU gerekli).** Bu benchmark
`faster_whisper` üzerinden gerçek GPU çözümlemesi gerektirir; CUDA'sız bir ortamda (ör. bu
geliştirme makinesi/WSL) çalıştırılamaz.

## Neyi ölçüyor

`scripts/eval_stt.py`, `scripts/eval_data/stt/manifest.json`'daki ses kayıtlarını farklı
`beam_size` ve `condition_on_previous_text` ayarlarıyla çözümleyip her ayar için ortalama
**WER** (Word Error Rate — kelime hata oranı) ve ortalama gecikmeyi raporlar.

- **WER:** kelime düzeyinde Levenshtein (düzenleme) mesafesinin referans kelime sayısına
  oranı. Karşılaştırma büyük/küçük harf, noktalama ve aksan işaretlerine duyarsızdır
  (`casefold` + Unicode NFKD ile aksan ayrıştırma + `ı→i`), çünkü STT çıktısı çoğunlukla
  noktalamayı farklı yerleştirir; benchmark'ın amacı kelime doğruluğunu ölçmek, noktalama
  stilini değil.
- **beam_size:** Whisper'ın arama genişliği. Büyük değer genelde daha doğru ama daha yavaş
  çözümleme demektir.
- **condition_on_previous_text:** önceki segmentin metnini bir sonraki segmentin bağlamı
  olarak kullanır. Uzun kayıtlarda tutarlılığı artırabilir ama halüsinasyonu da (bkz.
  README'deki "Halüsinasyon ve sessizlik" bölümü) tetikleyebilir; bu yüzden burada ayrıca
  ölçülüyor. **Not:** bu parametre `SttSettings`'e eklenmedi — yalnızca bu benchmark'a
  özgüdür ve `engine._model.transcribe(...)`'a doğrudan geçilir (bkz. betikteki yorum).

## Veri toplama

Ses dosyaları repoya konmaz; bkz. `scripts/eval_data/stt/README.md` (kayıt formatı, 20 kayıt
önerisi, Common Voice TR alternatifi, `manifest.json` şeması).

## Çalıştırma

```bash
.venv/bin/python scripts/eval_stt.py --manifest scripts/eval_data/stt/manifest.json \
    --beam 1,2,5 --cond true,false --write
```

`--write` verilirse sonuç tablosu aşağıdaki işaretli bölüme yazılır (yöntem metnine dokunmaz).

## Sonuçlar

<!-- RESULTS:BEGIN -->

ölçüm henüz yapılmadı (GPU gerekli)

<!-- RESULTS:END -->
