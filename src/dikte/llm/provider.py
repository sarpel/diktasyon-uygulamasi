from __future__ import annotations

from typing import Protocol


class LlmError(Exception):
    pass


class LlmProvider(Protocol):
    @property
    def name(self) -> str: ...

    def complete(
        self,
        system: str,
        user: str,
        *,
        json_schema: dict | None = None,
        temperature: float = 0.2,
    ) -> str: ...
