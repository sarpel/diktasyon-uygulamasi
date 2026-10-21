"""Ayarlar → Sözlük sekmesi."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QAbstractItemView,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from dikte.config import DictionaryEntry, Settings

TERM_COL, WRONG_COL = 0, 1


class DictionaryTab(QWidget):
    """Özel sözlük: doğru yazımlar, STT'nin sık yanlış tanıdığı biçimler ve LLM düzeltmesine
    eklenen serbest talimat. Boş terimli satır doğrulamada reddedilir.

    "Öğrenilen kelimeler": sonuç penceresindeki "Öğren" ile toplanan, yalnızca Whisper'a
    ipucu verilen kelimeler; buradan seçilerek ya da toptan silinebilir."""

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

        self.learned_list = QListWidget()
        self.learned_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.learned_list.addItems(d.learned)
        self.learned_list.setToolTip(
            "Bu kelimeler zorla değiştirilmez; Whisper'ın onları seçme olasılığı artırılır."
        )
        self.remove_learned_btn = QPushButton("Seçileni sil")
        self.remove_learned_btn.clicked.connect(self._remove_learned)
        self.clear_learned_btn = QPushButton("Tümünü sil")
        self.clear_learned_btn.clicked.connect(self.learned_list.clear)
        self.learned_count_label = QLabel("")
        self.learned_list.model().rowsInserted.connect(self._update_learned_count)
        self.learned_list.model().rowsRemoved.connect(self._update_learned_count)
        self._update_learned_count()
        learned_btns = QHBoxLayout()
        learned_btns.addWidget(self.remove_learned_btn)
        learned_btns.addWidget(self.clear_learned_btn)
        learned_btns.addStretch(1)
        learned_btns.addWidget(self.learned_count_label)
        learned_group = QGroupBox('Öğrenilen kelimeler ("Öğren" düğmesiyle)')
        learned_lay = QVBoxLayout(learned_group)
        learned_lay.addWidget(self.learned_list)
        learned_lay.addLayout(learned_btns)

        lay = QVBoxLayout(self)
        lay.addWidget(self.dictionary_table, 1)
        lay.addLayout(btn_row)
        lay.addWidget(self.instructions_edit)
        lay.addWidget(learned_group)

    def _update_learned_count(self, *_args) -> None:
        self.learned_count_label.setText(f"{self.learned_list.count()} kelime")

    def _remove_learned(self) -> None:
        for item in self.learned_list.selectedItems():
            self.learned_list.takeItem(self.learned_list.row(item))

    def learned(self) -> tuple[str, ...]:
        return tuple(self.learned_list.item(i).text() for i in range(self.learned_list.count()))

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
                "dictionary": s.dictionary.model_copy(
                    update={
                        "entries": entries,
                        "learned": self.learned(),
                        "user_instructions": self.instructions_edit.toPlainText().strip(),
                    }
                )
            }
        )
