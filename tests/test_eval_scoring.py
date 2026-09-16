import pytest
from eval_llm import (
    CATEGORIES,
    RESULTS_BEGIN,
    RESULTS_END,
    Case,
    _write_results,
    aggregate,
    load_cases,
    render_markdown,
    run,
    score_case,
)

from dikte.llm.tasks import Change, CorrectionResult


def test_perfect_result_scores_one():
    c = Case("x", "yazim", "çuk güzel", ("çok güzel",), ("çuk",), 0.5)
    s = score_case(c, CorrectionResult("çok güzel", (Change("çuk", "çok", "yazım"),)), 1.0)
    assert s.score == 1.0 and s.valid_json


def test_alternatives_in_must_contain():
    c = Case("x", "teknik_koru", "docker kompoz", ("docker compose|docker-compose",), ("kompoz",))
    assert score_case(c, CorrectionResult("docker-compose dosyası", ()), 1.0).passed_contains == 1


def test_violation_costs_its_weight():
    c = Case("x", "yazim", "çok ama çuk kaldı", ("çok",), ("çuk",), max_change_ratio=0.9)
    s = score_case(c, CorrectionResult("çok ama çuk kaldı", ()), 1.0)
    assert s.violations and not s.over_edited and s.score == pytest.approx(0.75)


def test_over_edit_penalised():
    c = Case("x", "anlam_koru", "Bu iyi.", ("Bu iyi.",), (), 0.05)
    s = score_case(c, CorrectionResult("Bu gerçekten çok iyi bir şey. Bu iyi.", ()), 1.0)
    assert s.over_edited and s.score < 0.9


def test_unnecessary_change_is_a_violation():
    c = Case(
        "x",
        "bos_degisiklik",
        "Bugün hava çok güzel.",
        ("Bugün hava çok güzel.",),
        max_change_ratio=0.02,
        expect_no_changes=True,
    )
    s = score_case(c, CorrectionResult("Bugün hava çok güzel.", (Change("a", "b", "r"),)), 1.0)
    assert "gereksiz değişiklik" in s.violations


def test_no_changes_case_can_score_full():
    c = Case(
        "x",
        "bos_degisiklik",
        "Bugün hava çok güzel.",
        ("Bugün hava çok güzel.",),
        max_change_ratio=0.02,
        expect_no_changes=True,
    )
    assert score_case(c, CorrectionResult("Bugün hava çok güzel.", ()), 1.0).score == 1.0


def test_none_result_scores_zero():
    s = score_case(Case("x", "yazim", "a", ("a",)), None, 0.0)
    assert s.score == 0.0 and s.valid_json is False


def test_case_without_expectations_is_not_free_points():
    """must_contain boşsa oran 1 sayılır ama yasak/aşırı düzenleme yine cezalandırılır."""
    c = Case("x", "anlam_koru", "Kısa.", (), ("uydurma",), 0.05)
    s = score_case(c, CorrectionResult("Kısa ama uydurma eklendi.", ()), 1.0)
    assert s.score < 0.7


def test_aggregate_scale_and_categories():
    scores = [
        score_case(Case("a", "yazim", "çuk", ("çok",), ("çuk",)), CorrectionResult("çok", ()), 1.0),
        score_case(Case("b", "noktalama", "merhaba", ("?",)), CorrectionResult("merhaba", ()), 3.0),
    ]
    out = aggregate(scores)
    assert 0 <= out["score_10"] <= 10
    assert set(out["by_category"]) == {"yazim", "noktalama"}
    assert out["avg_latency"] == 2.0 and out["failures"] == 0


def test_aggregate_of_nothing_is_zero():
    assert aggregate([])["score_10"] == 0.0


def test_render_markdown_has_table_header_and_sorts_by_score():
    table = render_markdown(
        {
            "zayif": {"score_10": 4.0, "avg_latency": 0.5, "by_category": {}, "failures": 1},
            "guclu": {
                "score_10": 8.2,
                "avg_latency": 1.1,
                "by_category": {"yazim": 9.0},
                "failures": 0,
            },
        }
    )
    assert "| Model |" in table and all(c in table for c in CATEGORIES)
    assert table.index("guclu") < table.index("zayif")


def test_dataset_is_complete_and_unique():
    cases = load_cases()
    assert len(cases) >= 40
    assert len({c.id for c in cases}) == len(cases)
    for category in CATEGORIES:
        assert sum(1 for c in cases if c.category == category) >= 6


def test_run_uses_provider_factory_without_network():
    class FakeProvider:
        def complete(self, system, user, *, json_schema=None, temperature=0.2):
            return '{"corrected_text": "çok güzel", "changes": []}'

    cases = (Case("a", "yazim", "çuk güzel", ("çok güzel",), ("çuk",)),)
    results = run(("sahte",), cases, lambda model: FakeProvider())
    assert results["sahte"]["score_10"] == 10.0


def test_run_scores_zero_when_provider_fails():
    class BrokenProvider:
        def complete(self, *a, **k):
            raise RuntimeError("bağlanamadı")

    cases = (Case("a", "yazim", "çuk", ("çok",)),)
    results = run(("sahte",), cases, lambda model: BrokenProvider())
    assert results["sahte"]["score_10"] == 0.0 and results["sahte"]["failures"] == 1


def test_rewrite_without_declared_changes_is_still_a_violation():
    """Model metni değiştirip 'changes' listesini boş bırakırsa da ihlal sayılır."""
    c = Case(
        "x",
        "bos_degisiklik",
        "Bugün hava çok güzel.",
        ("Bugün hava",),
        max_change_ratio=0.9,
        expect_no_changes=True,
    )
    s = score_case(c, CorrectionResult("Bugün hava fena değil.", ()), 1.0)
    assert "gereksiz değişiklik" in s.violations


def test_model_is_unloaded_after_its_turn():
    class FakeProvider:
        def __init__(self):
            self.unloaded = 0

        def complete(self, system, user, *, json_schema=None, temperature=0.2):
            return '{"corrected_text": "çok", "changes": []}'

        def unload(self):
            self.unloaded += 1

    created: list[FakeProvider] = []

    def factory(model):
        created.append(FakeProvider())
        return created[-1]

    run(("a", "b"), (Case("x", "yazim", "çuk", ("çok",)),), factory)
    assert [p.unloaded for p in created] == [1, 1]


def test_runs_below_one_is_rejected():
    import eval_llm

    with pytest.raises(SystemExit):
        eval_llm.main(["--models", "m", "--runs", "0"])


def test_write_results_replaces_only_marked_section(tmp_path):
    path = tmp_path / "llm_benchmark.md"
    path.write_text(
        f"# Yöntem\n\nBu bölüm silinmemeli.\n\n"
        f"{RESULTS_BEGIN}\n\neski sonuç\n\n{RESULTS_END}\n\n"
        f"## Aday seçimi\n\nBu da silinmemeli.\n",
        encoding="utf-8",
    )
    _write_results(path, 5, 2, "| Model | Puan |\n|---|---|\n")
    text = path.read_text(encoding="utf-8")
    assert "Bu bölüm silinmemeli." in text
    assert "Bu da silinmemeli." in text
    assert "eski sonuç" not in text
    assert "5 örnek · 2 tur" in text


def test_write_results_appends_markers_when_missing(tmp_path):
    path = tmp_path / "llm_benchmark.md"
    path.write_text("# Yöntem\n\nKorunmalı.\n", encoding="utf-8")
    _write_results(path, 3, 1, "| Model |\n|---|\n")
    text = path.read_text(encoding="utf-8")
    assert "Korunmalı." in text
    assert RESULTS_BEGIN in text and RESULTS_END in text
