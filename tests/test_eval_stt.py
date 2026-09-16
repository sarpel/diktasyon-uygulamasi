import json

import pytest
from eval_stt import Case, Config, load_cases, render_markdown, run, wer


def test_wer_identical_texts_is_zero():
    assert wer("hava çok güzel", "hava çok güzel") == 0


def test_wer_one_substitution_of_three():
    assert wer("a b c", "a x c") == pytest.approx(1 / 3)


def test_wer_is_diacritic_and_punctuation_insensitive():
    assert wer("Merhaba, dünya!", "merhaba dunya") == 0


def test_load_cases_reads_manifest(tmp_path):
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps([{"file": "a.wav", "text": "hava çok güzel"}]), encoding="utf-8")
    cases = load_cases(manifest)
    assert cases == (Case("a.wav", "hava çok güzel"),)


def test_run_computes_mean_wer_and_latency_per_config():
    cases = (Case("a.wav", "hava çok güzel"), Case("b.wav", "bir iki üç"))
    texts = {"a.wav": "hava çok güzel", "b.wav": "bir iki üç"}

    def fake_transcribe(path, config):
        if config.beam_size == 1:
            return "tamamen farklı bir metin", 0.1
        return texts[path.name], 0.3

    results = run(cases, (Config(1, False), Config(5, True)), fake_transcribe)
    assert results["beam=5,cond=True"]["wer"] == 0.0
    assert results["beam=5,cond=True"]["latency_s"] == pytest.approx(0.3)
    assert results["beam=1,cond=False"]["wer"] > 0
    assert results["beam=1,cond=False"]["latency_s"] == pytest.approx(0.1)


def test_render_markdown_has_table_header():
    table = render_markdown({"beam=1,cond=False": {"wer": 0.1, "latency_s": 0.5}})
    assert "| Ayar | WER |" in table
    assert "beam=1,cond=False" in table
