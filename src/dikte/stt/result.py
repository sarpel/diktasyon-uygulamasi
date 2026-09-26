"""STT sonuç veri tipleri ve "konuşma algılanmadı" hata mesajı sabiti."""

from dataclasses import dataclass

# VAD ön-kontrolü konuşma bulamadığında motorun yükselttiği hata; denetleyici bunu gerçek bir
# arızadan ayırır (sessiz kaydın sesi "yeniden dene" için saklanmaz).
NO_SPEECH_MESSAGE = "Konuşma algılanmadı; mikrofon ve VAD eşiğini kontrol edin"


@dataclass(frozen=True)
class Segment:
    """Whisper'ın ürettiği tek bir metin segmenti (saniye cinsinden başlangıç/bitiş)."""

    start: float
    end: float
    text: str
    # Whisper'ın segment başına verdiği güven ölçütleri; halüsinasyon filtresi bunları kullanır.
    no_speech_prob: float = 0.0
    avg_logprob: float = 0.0


@dataclass(frozen=True)
class TranscriptResult:
    """Bir çözümlemenin sonucu; `text` filtrelenmiş segmentlerin birleşimidir (boş olabilir)."""

    text: str
    language: str
    duration_s: float
    segments: tuple[Segment, ...]
