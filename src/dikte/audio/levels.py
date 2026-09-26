"""Ses seviyesi ölçümü: overlay'deki seviye göstergesi için RMS ve tepe kovaları."""

import numpy as np


def rms(frame: np.ndarray) -> float:
    """Çerçevenin RMS seviyesi, [0, 1] aralığına kırpılmış; boş çerçevede 0."""
    if frame.size == 0:
        return 0.0
    val = float(np.sqrt(np.mean(np.square(frame, dtype=np.float64))))
    return min(1.0, val)


def bucketize(frame: np.ndarray, buckets: int) -> tuple[float, ...]:
    """Çerçeveyi `buckets` eşit parçaya bölüp her birinin mutlak tepe değerini (≤ 1) verir."""
    if frame.size == 0 or buckets <= 0:
        return (0.0,) * max(buckets, 0)
    chunks = np.array_split(frame, buckets)
    return tuple(min(1.0, float(np.max(np.abs(c)))) if c.size else 0.0 for c in chunks)
