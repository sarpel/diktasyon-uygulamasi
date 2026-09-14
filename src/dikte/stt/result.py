from dataclasses import dataclass


@dataclass(frozen=True)
class Segment:
    start: float
    end: float
    text: str


@dataclass(frozen=True)
class TranscriptResult:
    text: str
    language: str
    duration_s: float
    segments: tuple[Segment, ...]
