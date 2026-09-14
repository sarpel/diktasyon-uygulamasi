"""qwen3.5:4b ve gemma4:e4b-it-qat'i Türkçe STT-hatası düzeltmede karşılaştırır."""

import sys
import time

from dikte.config import LlmSettings
from dikte.llm.ollama_provider import OllamaProvider
from dikte.llm.tasks import correct

SAMPLES = [
    "bugün hava çuk güzel dışarı çıkalım mı",
    "projeyi git hapa pushladım pull rikuest açar mısın",
    "toplantıyı yarın saat on beşe ertele yelim lütfen",
    "bu fonksiyonda nul pointer hatası alıyorum bak abilir misin",
    "faster whisper modelini large turbo ya güncelle",
    "kullanıcı giriş ekranında şifre alanı boş bırakılınca uyarı vermiyor",
    "docker kompoz dosyasında port çakışması var sanırım",
    "rapor u pdf olarak dışa aktar butonu ekle",
    "veri tabanı migrasyonunu geri almak için komut nedir",
    "bu promptu ingilizceye çevirip agent a ver",
]
MODELS = sys.argv[1:] or ["qwen3.5:4b", "gemma4:e4b-it-qat"]

for model in MODELS:
    p = OllamaProvider(LlmSettings(model=model))
    print(f"\n=== {model} ===")
    total = 0.0
    for raw in SAMPLES:
        t0 = time.perf_counter()
        res = correct(p, raw)
        dt = time.perf_counter() - t0
        total += dt
        print(f"[{dt:4.1f}s] {raw}\n        -> {res.corrected_text}")
        for c in res.changes:
            print(f"           {c.original} -> {c.replacement} ({c.reason})")
    print(f"toplam {total:.1f}s, ort. {total / len(SAMPLES):.1f}s/cümle")
