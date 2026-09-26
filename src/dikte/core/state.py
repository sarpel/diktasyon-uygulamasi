"""Dikte durumları, modlar ve değişmez `Session` kaydı."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import Enum, auto

from dikte.llm.tasks import Change


class DictationState(Enum):
    """Denetleyicinin durumları: boşta → kayıt → çözümleme → düzeltme → sonuç."""

    IDLE = auto()
    RECORDING = auto()
    TRANSCRIBING = auto()
    CORRECTING = auto()
    RESULT = auto()


# Kullanıcının bekleme yaşadığı, dolayısıyla iptal edilebilir durumlar.
BUSY_STATES = (
    DictationState.RECORDING,
    DictationState.TRANSCRIBING,
    DictationState.CORRECTING,
)

MODES = ("correct", "translate", "prompt")


@dataclass(frozen=True)
class Session:
    """Tek bir dikte oturumu (değişmez); güncellemeler `with_` ile yeni kopya üretir."""

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    created_at: datetime = field(default_factory=datetime.now)
    mode: str = "correct"
    raw_text: str = ""
    corrected_text: str = ""
    changes: tuple[Change, ...] = ()
    translation: str = ""
    enhanced_prompt: str = ""
    duration_s: float = 0.0
    source_path: str = ""  # dosyadan çözümlendiyse kaynak dosyanın yolu; mikrofon kaydında boş
    profile: str = ""  # eşleşen uygulama profilinin adı; eşleşme yoksa boş

    def with_(self, **kwargs) -> Session:
        return replace(self, **kwargs)

    @property
    def output_text(self) -> str:
        """Sonucun teslim edileceği metin: mod'a göre çeviri/prompt, yoksa düzeltilmiş metin."""
        if self.mode == "translate":
            return self.translation or self.corrected_text
        if self.mode == "prompt":
            return self.enhanced_prompt or self.corrected_text
        return self.corrected_text
