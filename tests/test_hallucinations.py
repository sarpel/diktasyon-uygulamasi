import pytest

from dikte.stt.hallucinations import filter_segments, is_hallucination
from dikte.stt.result import Segment


@pytest.mark.parametrize(
    "text",
    [
        "Altyazı M.K.",
        "altyazı m.k",
        "ALTYAZI M.K.",
        "İzlediğiniz için teşekkürler.",
        "Abone olmayı unutmayın!",
        "Altyazı",
        "Bu videoyu beğendiyseniz",
        "Subtitles by the Amara.org community",
    ],
)
def test_known_phrases_detected(text):
    assert is_hallucination(text)


@pytest.mark.parametrize(
    "text",
    [
        "Bugün toplantıda altyazı ekleme özelliğini konuştuk.",
        "Teşekkürler, raporu aldım.",
        "Videoyu izlediğiniz için teşekkürler diyen bir e-posta taslağı hazırla lütfen.",
        "Abone sayısını raporda göster.",
        "Lütfen altyazı ekle",
        "Çeviriyi gönder",
    ],
)
def test_real_sentences_kept(text):
    assert not is_hallucination(text)


def test_empty_text_is_not_hallucination():
    assert not is_hallucination("   ")


def test_filter_drops_known_phrases_and_high_no_speech_prob():
    segments = (
        Segment(0, 1, "Merhaba", no_speech_prob=0.1),
        Segment(1, 2, "Altyazı M.K.", no_speech_prob=0.2),
        Segment(2, 3, "gürültü", no_speech_prob=0.95),
    )
    kept = filter_segments(segments, no_speech_threshold=0.6)
    assert [s.text for s in kept] == ["Merhaba"]


def test_filter_keeps_everything_when_threshold_is_high():
    segments = (Segment(0, 1, "belirsiz", no_speech_prob=0.9),)
    assert filter_segments(segments, no_speech_threshold=1.0) == segments


def test_filter_returns_new_tuple():
    segments = (Segment(0, 1, "Merhaba", no_speech_prob=0.0),)
    assert filter_segments(segments, no_speech_threshold=0.6) is not segments


def test_filter_keeps_high_confidence_segment_despite_no_speech_prob():
    segments = (
        Segment(0, 1, "gerçek konuşma", no_speech_prob=0.95, avg_logprob=-0.2),
    )
    kept = filter_segments(
        segments, no_speech_threshold=0.6, log_prob_threshold=-1.0
    )
    assert [s.text for s in kept] == ["gerçek konuşma"]


def test_filter_drops_high_no_speech_prob_when_log_prob_threshold_is_none():
    segments = (
        Segment(0, 1, "gürültü", no_speech_prob=0.95, avg_logprob=-0.2),
    )
    kept = filter_segments(segments, no_speech_threshold=0.6)
    assert kept == ()
