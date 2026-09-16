from __future__ import annotations

from typing import Literal, cast

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from dikte.config import AppProfile, Settings

NAME_COL, MATCH_COL, MODE_COL, PASTE_COL, LLM_COL, TRAILING_COL = range(6)

Mode = Literal["correct", "translate", "prompt"]
Paste = Literal["ctrl+v", "ctrl+shift+v", "type"]
Trailing = Literal["", " ", "\n"]

_MODES: tuple[Mode, ...] = ("correct", "translate", "prompt")
_PASTES: tuple[Paste, ...] = ("ctrl+v", "ctrl+shift+v", "type")
_TRAILING_LABELS: dict[Trailing, str] = {"": "(yok)", " ": "boşluk", "\n": "yeni satır"}
_TRAILING_VALUES: dict[str, Trailing] = {label: value for value, label in _TRAILING_LABELS.items()}


class ProfilesTab(QWidget):
    """Ön plandaki uygulamaya göre mod, yapıştırma tuşu ve LLM'in devre dışı bırakılmasını
    tanımlayan profiller; eşleşme yoksa genel ayarlar geçerli olur."""

    title = "Profiller"

    def __init__(self, settings: Settings, parent=None):
        super().__init__(parent)
        self.profiles_table = QTableWidget(0, 6)
        self.profiles_table.setHorizontalHeaderLabels(
            ["Ad", "Eşleşme", "Mod", "Yapıştırma", "LLM", "Sonek"]
        )
        self.profiles_table.horizontalHeader().setStretchLastSection(True)
        for profile in settings.profiles:
            self._add_row(profile)

        self.add_profile_btn = QPushButton("Ekle")
        self.add_profile_btn.clicked.connect(lambda: self._add_row(AppProfile(name="", match="")))
        self.remove_profile_btn = QPushButton("Kaldır")
        self.remove_profile_btn.clicked.connect(self._remove_selected)

        btn_row = QHBoxLayout()
        btn_row.addWidget(self.add_profile_btn)
        btn_row.addWidget(self.remove_profile_btn)
        btn_row.addStretch(1)

        lay = QVBoxLayout(self)
        lay.addWidget(self.profiles_table, 1)
        lay.addLayout(btn_row)

    def _add_row(self, profile: AppProfile) -> None:
        row = self.profiles_table.rowCount()
        self.profiles_table.insertRow(row)
        self.profiles_table.setItem(row, NAME_COL, QTableWidgetItem(profile.name))
        self.profiles_table.setItem(row, MATCH_COL, QTableWidgetItem(profile.match))

        mode_combo = QComboBox()
        mode_combo.addItems(list(_MODES))
        mode_combo.setCurrentText(profile.mode)
        self.profiles_table.setCellWidget(row, MODE_COL, mode_combo)

        paste_combo = QComboBox()
        paste_combo.addItems(list(_PASTES))
        paste_combo.setCurrentText(profile.paste)
        self.profiles_table.setCellWidget(row, PASTE_COL, paste_combo)

        llm_check = QCheckBox()
        llm_check.setChecked(profile.llm_enabled)
        self.profiles_table.setCellWidget(row, LLM_COL, llm_check)

        trailing_combo = QComboBox()
        trailing_combo.addItems(list(_TRAILING_LABELS.values()))
        trailing_combo.setCurrentText(_TRAILING_LABELS[profile.trailing])
        self.profiles_table.setCellWidget(row, TRAILING_COL, trailing_combo)

    def _remove_selected(self) -> None:
        rows = sorted({i.row() for i in self.profiles_table.selectedIndexes()}, reverse=True)
        for row in rows:
            self.profiles_table.removeRow(row)

    def _rows(self) -> list[AppProfile]:
        profiles = []
        for row in range(self.profiles_table.rowCount()):
            name_item = self.profiles_table.item(row, NAME_COL)
            match_item = self.profiles_table.item(row, MATCH_COL)
            mode_combo = cast(QComboBox, self.profiles_table.cellWidget(row, MODE_COL))
            paste_combo = cast(QComboBox, self.profiles_table.cellWidget(row, PASTE_COL))
            llm_check = cast(QCheckBox, self.profiles_table.cellWidget(row, LLM_COL))
            trailing_combo = cast(QComboBox, self.profiles_table.cellWidget(row, TRAILING_COL))
            profiles.append(
                AppProfile(
                    name=(name_item.text() if name_item else "").strip(),
                    match=(match_item.text() if match_item else "").strip(),
                    mode=cast(Mode, mode_combo.currentText()),
                    paste=cast(Paste, paste_combo.currentText()),
                    llm_enabled=llm_check.isChecked(),
                    trailing=_TRAILING_VALUES[trailing_combo.currentText()],
                )
            )
        return profiles

    # ---- sözleşme
    def validate(self) -> str | None:
        for profile in self._rows():
            if not profile.name or not profile.match:
                return "Profilde ad ve eşleşme alanları boş olamaz"
        return None

    def apply(self, s: Settings) -> Settings:
        return s.model_copy(update={"profiles": tuple(self._rows())})
