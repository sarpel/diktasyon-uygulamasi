"""Ayarlar → Sözlük sekmesi."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QHBoxLayout,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from dikte.config import DictionaryEntry, DictionarySettings, Settings

TERM_COL, WRONG_COL = 0, 1


class DictionaryTab(QWidget):
    """Özel sözlük: doğru yazımlar, STT'nin sık yanlış tanıdığı biçimler ve LLM düzeltmesine
    eklenen serbest talimat. Boş terimli satır doğrulamada reddedilir."""

    title = "Sözlük"

    def __init__(self, settings: Settings, parent=None):
        super().__init__(parent)
        d = settings.dictionary
        self.dictionary_table = QTableWidget(0, 2)
        self.dictionary_table.setHorizontalHeaderLabels(
            ["Doğru yazım", "Yanlış tanınan biçimler (virgülle)"]
        )
        self.dictionary_table.horizontalHeader().setStretchLastSection(True)
        for entry in d.entries:
            self._add_row(entry.term, ", ".join(entry.wrong))

        self.add_entry_btn = QPushButton("Ekle")
        self.add_entry_btn.clicked.connect(lambda: self._add_row("", ""))
        self.remove_entry_btn = QPushButton("Kaldır")
        self.remove_entry_btn.clicked.connect(self._remove_selected)

        btn_row = QHBoxLayout()
        btn_row.addWidget(self.add_entry_btn)
        btn_row.addWidget(self.remove_entry_btn)
        btn_row.addStretch(1)

        self.instructions_edit = QPlainTextEdit(d.user_instructions)
        self.instructions_edit.setPlaceholderText(
            "LLM düzeltmesine eklenecek serbest metin talimat (isteğe bağlı)"
        )

        lay = QVBoxLayout(self)
        lay.addWidget(self.dictionary_table, 1)
        lay.addLayout(btn_row)
        lay.addWidget(self.instructions_edit)

    def _add_row(self, term: str, wrong: str) -> None:
        row = self.dictionary_table.rowCount()
        self.dictionary_table.insertRow(row)
        self.dictionary_table.setItem(row, TERM_COL, QTableWidgetItem(term))
        self.dictionary_table.setItem(row, WRONG_COL, QTableWidgetItem(wrong))

    def _remove_selected(self) -> None:
        rows = sorted({i.row() for i in self.dictionary_table.selectedIndexes()}, reverse=True)
        for row in rows:
            self.dictionary_table.removeRow(row)

    def _rows(self) -> list[tuple[str, str]]:
        rows = []
        for row in range(self.dictionary_table.rowCount()):
            term_item = self.dictionary_table.item(row, TERM_COL)
            wrong_item = self.dictionary_table.item(row, WRONG_COL)
            rows.append(
                (
                    (term_item.text() if term_item else "").strip(),
                    (wrong_item.text() if wrong_item else "").strip(),
                )
            )
        return rows

    # ---- sözleşme
    def validate(self) -> str | None:
        for term, _wrong in self._rows():
            if not term:
                return "Sözlükte boş terim var"
        return None

    def apply(self, s: Settings) -> Settings:
        entries = tuple(
            DictionaryEntry(
                term=term, wrong=tuple(w.strip() for w in wrong.split(",") if w.strip())
            )
            for term, wrong in self._rows()
            if term
        )
        return s.model_copy(
            update={
                "dictionary": DictionarySettings(
                    entries=entries,
                    user_instructions=self.instructions_edit.toPlainText().strip(),
                )
            }
        )
