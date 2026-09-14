from __future__ import annotations

import uuid
from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import Enum, auto

from dikte.llm.tasks import Change


class DictationState(Enum):
    IDLE = auto()
    RECORDING = auto()
    TRANSCRIBING = auto()
    CORRECTING = auto()
    RESULT = auto()


@dataclass(frozen=True)
class Session:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    created_at: datetime = field(default_factory=datetime.now)
    raw_text: str = ""
    corrected_text: str = ""
    changes: tuple[Change, ...] = ()
    translation: str = ""
    enhanced_prompt: str = ""
    duration_s: float = 0.0

    def with_(self, **kwargs) -> Session:
        return replace(self, **kwargs)
