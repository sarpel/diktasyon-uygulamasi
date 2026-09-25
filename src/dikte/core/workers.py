from __future__ import annotations

import logging
from collections.abc import Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot

log = logging.getLogger(__name__)


class _Signals(QObject):
    result = Signal(object)
    error = Signal(str)


class _Job(QRunnable):
    def __init__(self, fn: Callable[[], object], signals: _Signals):
        super().__init__()
        self._fn, self._signals = fn, signals
        self.setAutoDelete(True)

    @Slot()
    def run(self) -> None:
        try:
            self._signals.result.emit(self._fn())
        except Exception as exc:
            log.exception("worker hatası")
            self._signals.error.emit(str(exc))


def run_in_pool(
    fn: Callable[[], object],
    on_result: Callable[[object], None],
    on_error: Callable[[str], None],
    pool: QThreadPool | None = None,
    on_finished: Callable[[], None] | None = None,
) -> _Signals:
    """fn'i thread havuzunda çalıştırır; sonuç/hata Qt sinyaliyle çağıran thread'e döner.
    Dönen _Signals nesnesi, job bitene kadar referansı canlı tutmak için saklanmalıdır.
    `on_finished`, sonuç ya da hata geri çağrısından SONRA (aynı thread'de) çağrılır; iş
    başlamadan bağlandığı için hızlı biten işlerde de kaçırılmaz."""
    signals = _Signals()
    signals.result.connect(on_result)
    signals.error.connect(on_error)
    if on_finished is not None:
        signals.result.connect(lambda _r: on_finished())
        signals.error.connect(lambda _e: on_finished())
    (pool or QThreadPool.globalInstance()).start(_Job(fn, signals))
    return signals
