#!/usr/bin/env python
"""Türkçe STT benchmark'ı: WER, beam_size ve bağlam koşullama karşılaştırması.

Ses dosyaları repoya konmaz (bkz. scripts/eval_data/stt/README.md); gerçek çözümleme GPU +
faster-whisper gerektirir ve kullanıcı config'i değil varsayılan `SttSettings` kullanılır.
Her `--beam` × `--cond` bileşimi ayrı ölçülür. Tablo her zaman yazdırılır; dosyaya
(`--out`, varsayılan docs/stt_benchmark.md) yalnızca `--write` ile yazılır.

Çalıştırma:
  .venv/bin/python scripts/eval_stt.py --manifest scripts/eval_data/stt/manifest.json \
      --beam 1,2,5 --cond true,false --write
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import time
import unicodedata
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT / "src") not in sys.path:  # kurulum yapılmadan da çalışsın
    sys.path.insert(0, str(REPO_ROOT / "src"))

DEFAULT_MANIFEST = REPO_ROOT / "scripts" / "eval_data" / "stt" / "manifest.json"
DEFAULT_OUT = REPO_ROOT / "docs" / "stt_benchmark.md"

_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)


@dataclass(frozen=True)
class Case:
    """Manifest girdisi: ses dosyasının yolu ve doğru (referans) metni."""

    file: str
    text: str


@dataclass(frozen=True)
class Config:
    """Karşılaştırılan tek bir çözümleme ayarı bileşimi."""

    beam_size: int
    condition_on_previous_text: bool


def load_cases(manifest: Path = DEFAULT_MANIFEST) -> tuple[Case, ...]:
    raw = json.loads(manifest.read_text(encoding="utf-8"))
    return tuple(Case(file=item["file"], text=item["text"]) for item in raw)


def _normalize(text: str) -> list[str]:
    """casefold + aksan/noktalama sil + ı→i (WER diyakritiğe duyarsız karşılaştırır)."""
    text = text.casefold().replace("ı", "i")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = _PUNCT.sub("", text)
    return text.split()


def wer(reference: str, hypothesis: str) -> float:
    """Kelime düzeyi Levenshtein mesafesi / referans kelime sayısı."""
    ref, hyp = _normalize(reference), _normalize(hypothesis)
    if not ref:
        return 0.0 if not hyp else 1.0
    prev = list(range(len(hyp) + 1))
    for i, rword in enumerate(ref, start=1):
        cur = [i] + [0] * len(hyp)
        for j, hword in enumerate(hyp, start=1):
            cost = 0 if rword == hword else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
        prev = cur
    return prev[len(hyp)] / len(ref)


def _config_key(config: Config) -> str:
    return f"beam={config.beam_size},cond={config.condition_on_previous_text}"


def run(
    cases: Sequence[Case],
    configs: Sequence[Config],
    transcribe: Callable[[Path, Config], tuple[str, float]],
) -> dict[str, dict]:
    results: dict[str, dict] = {}
    for config in configs:
        wers: list[float] = []
        latencies: list[float] = []
        for case in cases:
            hypothesis, latency_s = transcribe(Path(case.file), config)
            wers.append(wer(case.text, hypothesis))
            latencies.append(latency_s)
        results[_config_key(config)] = {
            "wer": round(statistics.fmean(wers), 4) if wers else 0.0,
            "latency_s": round(statistics.fmean(latencies), 2) if latencies else 0.0,
        }
    return results


def render_markdown(results: dict[str, dict]) -> str:
    header = "| Ayar | WER | Ort. gecikme (sn) |"
    separator = "|---|---|---|"
    lines = [header, separator]
    for key, data in sorted(results.items(), key=lambda kv: kv[1]["wer"]):
        lines.append(f"| {key} | {data['wer']:.4f} | {data['latency_s']:.2f} |")
    return "\n".join(lines)


RESULTS_BEGIN, RESULTS_END = "<!-- RESULTS:BEGIN -->", "<!-- RESULTS:END -->"


def _write_results(path: Path, n_cases: int, table: str) -> None:
    """Yalnız işaretli sonuç bölümünü değiştirir; yöntem metnine dokunmaz (eval_llm.py deseni)."""
    block = f"{RESULTS_BEGIN}\n\n{n_cases} kayıt\n\n{table}\n\n{RESULTS_END}"
    if path.exists():
        text = path.read_text(encoding="utf-8")
        if RESULTS_BEGIN in text and RESULTS_END in text:
            before, rest = text.split(RESULTS_BEGIN, 1)
            _, after = rest.split(RESULTS_END, 1)
            text = before + block + after
        else:
            text = text.rstrip() + "\n\n" + block + "\n"
    else:
        text = f"# Türkçe STT benchmark'ı\n\n{block}\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _real_transcribe_factory(stt_settings) -> Callable[[Path, Config], tuple[str, float]]:
    """Gerçek çözümleme: FasterWhisperEngine + faster_whisper.decode_audio.

    `condition_on_previous_text` `SttSettings`'e eklenmez (yalnızca bu benchmark'a özgü bir
    parametredir); bu yüzden motorun genel `transcribe()`'ı yerine `engine._model.transcribe`
    doğrudan çağrılır.
    """
    from faster_whisper import decode_audio

    from dikte.stt.engine import FasterWhisperEngine

    engine = FasterWhisperEngine(stt_settings)
    engine.load()

    def transcribe(path: Path, config: Config) -> tuple[str, float]:
        audio = np.asarray(decode_audio(str(path), sampling_rate=16000), dtype=np.float32)
        started = time.perf_counter()
        assert engine._model is not None  # load() çağrıldı
        segments, _info = engine._model.transcribe(
            audio,
            language=stt_settings.language,
            beam_size=config.beam_size,
            condition_on_previous_text=config.condition_on_previous_text,
        )
        text = "".join(seg.text for seg in segments)
        return text.strip(), time.perf_counter() - started

    return transcribe


def _parse_int_list(value: str) -> tuple[int, ...]:
    return tuple(int(v) for v in value.split(","))


def _parse_bool_list(value: str) -> tuple[bool, ...]:
    return tuple(v.strip().casefold() == "true" for v in value.split(","))


def main(argv: list[str] | None = None) -> int:
    from dikte.config import SttSettings

    parser = argparse.ArgumentParser(prog="eval_stt")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--beam", default="1,2,5", help="virgülle ayrılmış beam_size listesi")
    parser.add_argument(
        "--cond",
        default="true,false",
        help="virgülle ayrılmış condition_on_previous_text listesi",
    )
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--write", action="store_true", help="sonucu docs/stt_benchmark.md'e yazar")
    args = parser.parse_args(argv)

    if not args.manifest.exists():
        print(f"manifest bulunamadı: {args.manifest}", file=sys.stderr)
        return 1

    cases = load_cases(args.manifest)
    configs = [
        Config(beam_size=b, condition_on_previous_text=c)
        for b in _parse_int_list(args.beam)
        for c in _parse_bool_list(args.cond)
    ]
    print(f"{len(cases)} kayıt, {len(configs)} ayar")
    transcribe = _real_transcribe_factory(SttSettings())
    results = run(cases, configs, transcribe)
    table = render_markdown(results)
    print("\n" + table)
    if args.write:
        _write_results(args.out, len(cases), table)
        print(f"\nyazıldı: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
