#!/usr/bin/env python
"""Türkçe STT düzeltme benchmark'ı: bilerek yerleştirilmiş hatalar ve bağlam testleri.

Puanlama saf fonksiyonlardan oluşur (Ollama gerekmez); testler bunları doğrudan çağırır.
Çalıştırma:  python scripts/eval_llm.py --models qwen3.5:4b gemma4:e4b-it-qat
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Literal

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT / "src") not in sys.path:  # kurulum yapılmadan da çalışsın
    sys.path.insert(0, str(REPO_ROOT / "src"))

from dikte.config import LlmSettings  # noqa: E402
from dikte.llm.tasks import CorrectionResult, correct  # noqa: E402

DATA_PATH = REPO_ROOT / "scripts" / "eval_data" / "tr_corrections.json"
DEFAULT_OUT = REPO_ROOT / "docs" / "llm_benchmark.md"
Category = Literal["yazim", "baglam", "teknik_koru", "noktalama", "anlam_koru", "bos_degisiklik"]
CATEGORIES: tuple[str, ...] = (
    "yazim",
    "baglam",
    "teknik_koru",
    "noktalama",
    "anlam_koru",
    "bos_degisiklik",
)
# Ağırlıklar: doğru düzeltme ağır basar; yasak ifadeler ve aşırı müdahale cezalandırılır.
W_CONTAINS, W_VIOLATIONS, W_OVER_EDIT = 0.6, 0.25, 0.15


@dataclass(frozen=True)
class Case:
    id: str
    category: Category
    raw: str
    must_contain: tuple[str, ...] = ()  # "a|b" = alternatiflerden biri yeterli
    must_not_contain: tuple[str, ...] = ()
    max_change_ratio: float = 0.4
    expect_no_changes: bool = False


@dataclass(frozen=True)
class CaseScore:
    case_id: str
    category: str
    passed_contains: int
    total_contains: int
    violations: tuple[str, ...]
    over_edited: bool
    valid_json: bool
    latency_s: float
    score: float


def load_cases(path: Path = DATA_PATH) -> tuple[Case, ...]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return tuple(
        Case(
            id=item["id"],
            category=item["category"],
            raw=item["raw"],
            must_contain=tuple(item.get("must_contain", ())),
            must_not_contain=tuple(item.get("must_not_contain", ())),
            max_change_ratio=float(item.get("max_change_ratio", 0.4)),
            expect_no_changes=bool(item.get("expect_no_changes", False)),
        )
        for item in raw
    )


def _matches(expected: str, text: str) -> bool:
    """'a|b' biçimindeki alternatiflerden biri geçiyorsa yeterli."""
    return any(alt.casefold() in text.casefold() for alt in expected.split("|"))


def _change_ratio(before: str, after: str) -> float:
    return 1.0 - SequenceMatcher(None, before, after).ratio()


def score_case(case: Case, result: CorrectionResult | None, latency_s: float) -> CaseScore:
    """Tek örneğin 0..1 arası puanı. result None ise (hata / geçersiz JSON) puan 0."""
    if result is None:
        return CaseScore(
            case.id, case.category, 0, len(case.must_contain), (), False, False, latency_s, 0.0
        )
    text = result.corrected_text
    passed = sum(1 for expected in case.must_contain if _matches(expected, text))
    violations = tuple(f"yasak: {f}" for f in case.must_not_contain if _matches(f, text))
    if case.expect_no_changes and result.changes:
        violations += ("gereksiz değişiklik",)
    over_edited = _change_ratio(case.raw, text) > case.max_change_ratio
    contains_ratio = passed / len(case.must_contain) if case.must_contain else 1.0
    score = (
        W_CONTAINS * contains_ratio
        + W_VIOLATIONS * (0.0 if violations else 1.0)
        + W_OVER_EDIT * (0.0 if over_edited else 1.0)
    )
    return CaseScore(
        case.id,
        case.category,
        passed,
        len(case.must_contain),
        violations,
        over_edited,
        True,
        latency_s,
        score,
    )


def aggregate(scores: Sequence[CaseScore]) -> dict:
    if not scores:
        return {"score_10": 0.0, "by_category": {}, "avg_latency": 0.0, "failures": 0}
    by_category = {
        category: round(
            10 * statistics.fmean([s.score for s in scores if s.category == category]), 2
        )
        for category in CATEGORIES
        if any(s.category == category for s in scores)
    }
    return {
        "score_10": round(10 * statistics.fmean([s.score for s in scores]), 2),
        "by_category": by_category,
        "avg_latency": round(statistics.fmean([s.latency_s for s in scores]), 2),
        "failures": sum(1 for s in scores if not s.valid_json),
    }


def run_model(
    model: str, cases: Sequence[Case], provider_factory: Callable[[str], object], runs: int = 1
) -> dict:
    provider = provider_factory(model)
    scores: list[CaseScore] = []
    for _ in range(runs):
        for case in cases:
            started = time.perf_counter()
            try:
                result = correct(provider, case.raw)
            except Exception as exc:  # noqa: BLE001 - sağlayıcı hatası 0 puandır, tur sürer
                print(f"  ! {case.id}: {exc}", file=sys.stderr)
                result = None
            scores.append(score_case(case, result, time.perf_counter() - started))
    return aggregate(scores) | {"scores": scores}


def run(
    models: Sequence[str],
    cases: Sequence[Case],
    provider_factory: Callable[[str], object],
    runs: int = 1,
) -> dict[str, dict]:
    return {model: run_model(model, cases, provider_factory, runs) for model in models}


def render_markdown(results: dict[str, dict]) -> str:
    header = "| Model | Puan/10 | " + " | ".join(CATEGORIES) + " | Ort. gecikme | Hata |"
    separator = "|---" * (len(CATEGORIES) + 4) + "|"
    lines = [header, separator]
    for model, data in sorted(results.items(), key=lambda kv: -kv[1]["score_10"]):
        cells = [f"{data['by_category'].get(c, '—')}" for c in CATEGORIES]
        lines.append(
            f"| {model} | **{data['score_10']}** | "
            + " | ".join(cells)
            + f" | {data['avg_latency']} sn | {data['failures']} |"
        )
    return "\n".join(lines)


def _ollama_factory(host: str, keep_alive: str) -> Callable[[str], object]:
    from dikte.llm.ollama_provider import OllamaProvider

    def factory(model: str):
        return OllamaProvider(
            LlmSettings(model=model, ollama_host=host, keep_alive=keep_alive, think=False)
        )

    return factory


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="eval_llm")
    parser.add_argument("--models", nargs="+", required=True, help="Ollama model adları")
    parser.add_argument("--runs", type=int, default=1, help="her örneğin kaç kez sorulacağı")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--host", default=LlmSettings().ollama_host)
    parser.add_argument("--keep-alive", default="0", help="'0' = her modelden sonra VRAM boşalsın")
    args = parser.parse_args(argv)

    cases = load_cases()
    print(f"{len(cases)} örnek, {len(args.models)} model, {args.runs} tur")
    results = run(args.models, cases, _ollama_factory(args.host, args.keep_alive), args.runs)
    table = render_markdown(results)
    print("\n" + table)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        f"# Türkçe LLM düzeltme benchmark'ı\n\n{len(cases)} örnek · {args.runs} tur\n\n{table}\n",
        encoding="utf-8",
    )
    print(f"\nyazıldı: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
