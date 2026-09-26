"""Sekmelerdeki ortak "Varsayılanlara döndür" düğmesi."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtWidgets import QHBoxLayout, QPushButton

RESET_TEXT = "Varsayılanlara döndür"
RESET_TOOLTIP = (
    "Yalnızca bu sekmedeki ayarları varsayılan değerlere döndürür. "
    "Değişiklikler Tamam'a basılana kadar kaydedilmez."
)


def make_reset_button(on_click: Callable[[], None]) -> QPushButton:
    """Sekmeye özgü "Varsayılanlara döndür" düğmesi; kaydetmez, yalnızca alanları doldurur."""
    btn = QPushButton(RESET_TEXT)
    btn.setToolTip(RESET_TOOLTIP)
    btn.clicked.connect(on_click)
    return btn


def reset_row(btn: QPushButton) -> QHBoxLayout:
    """Düğmeyi sağa yaslayan satır."""
    row = QHBoxLayout()
    row.addStretch(1)
    row.addWidget(btn)
    return row
