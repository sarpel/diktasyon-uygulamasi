from __future__ import annotations

import logging

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from dikte.config import Settings

log = logging.getLogger(__name__)
PROVIDERS = ("ollama", "anthropic")


class LlmTab(QWidget):
    """LLM sağlayıcısı ve düzeltme ayarları."""

    title = "Metin Düzeltme"

    def __init__(self, settings: Settings, parent=None):
        super().__init__(parent)
        llm = settings.llm
        self.llm_enabled_check = QCheckBox("LLM ile metin düzeltme (kapalıyken VRAM kullanılmaz)")
        self.llm_enabled_check.setChecked(llm.enabled)
        self.prewarm_check = QCheckBox("Açılışta LLM'i belleğe al")
        self.prewarm_check.setChecked(llm.prewarm)
        self.provider_combo = QComboBox()
        self.provider_combo.addItems(PROVIDERS)
        self.provider_combo.setCurrentText(llm.provider)

        self.llm_model_edit = QLineEdit(llm.model)
        self.ollama_host_edit = QLineEdit(llm.ollama_host)
        self.keep_alive_edit = QLineEdit(llm.keep_alive)
        self.keep_alive_edit.setToolTip(
            "Ollama modelinin bellekte kalma süresi. Düşük VRAM'de '0' yazarak "
            "her istekten sonra boşaltabilirsiniz (ör. 30m, 5m, 0)."
        )
        self.ollama_group = QGroupBox("Ollama (yerel)")
        ollama_form = QFormLayout(self.ollama_group)
        ollama_form.addRow("Model", self.llm_model_edit)
        ollama_form.addRow("Host", self.ollama_host_edit)
        ollama_form.addRow("Model bellekte kalsın", self.keep_alive_edit)

        self.anthropic_model_edit = QLineEdit(llm.anthropic_model)
        self.anthropic_group = QGroupBox("Anthropic")
        anthropic_form = QFormLayout(self.anthropic_group)
        anthropic_form.addRow("Model", self.anthropic_model_edit)

        self.privacy_label = QLabel(
            "⚠ Uzak sağlayıcıda dikte metni dış servise gönderilir. "
            "API anahtarı yalnızca ortam değişkeninden okunur."
        )
        self.privacy_label.setWordWrap(True)
        self.privacy_label.setStyleSheet("color:#F5A623;")

        top = QFormLayout()
        top.addRow(self.llm_enabled_check)
        top.addRow("Sağlayıcı", self.provider_combo)
        top.addRow(self.prewarm_check)

        lay = QVBoxLayout(self)
        lay.addLayout(top)
        for group in self._groups():
            lay.addWidget(group)
        lay.addWidget(self.privacy_label)
        lay.addStretch(1)

        self.provider_combo.currentTextChanged.connect(self._show_group)
        self.llm_enabled_check.toggled.connect(self._set_fields_enabled)
        self._show_group(llm.provider)
        self._set_fields_enabled(llm.enabled)

    # ---- iç
    def _groups(self) -> tuple[QGroupBox, ...]:
        return (self.ollama_group, self.anthropic_group)

    def _group_for(self, provider: str) -> QGroupBox:
        return {"ollama": self.ollama_group, "anthropic": self.anthropic_group}[provider]

    def _show_group(self, provider: str) -> None:
        wanted = self._group_for(provider)
        for group in self._groups():
            group.setVisible(group is wanted)
        self.privacy_label.setVisible(provider != "ollama")

    def _set_fields_enabled(self, enabled: bool) -> None:
        self.provider_combo.setEnabled(enabled)
        self.prewarm_check.setEnabled(enabled)
        for group in self._groups():
            group.setEnabled(enabled)

    # ---- sözleşme
    def validate(self) -> str | None:
        if not self.llm_enabled_check.isChecked():
            return None
        provider = self.provider_combo.currentText()
        if provider == "ollama" and not self.llm_model_edit.text().strip():
            return "LLM model adı boş olamaz"
        if provider == "anthropic" and not self.anthropic_model_edit.text().strip():
            return "Anthropic model adı boş olamaz"
        return None

    def apply(self, s: Settings) -> Settings:
        return s.model_copy(
            update={
                "llm": s.llm.model_copy(
                    update={
                        "enabled": self.llm_enabled_check.isChecked(),
                        "prewarm": self.prewarm_check.isChecked(),
                        "provider": self.provider_combo.currentText(),
                        "model": self.llm_model_edit.text().strip(),
                        "ollama_host": self.ollama_host_edit.text().strip(),
                        "keep_alive": self.keep_alive_edit.text().strip() or "0",
                        "anthropic_model": self.anthropic_model_edit.text().strip(),
                    }
                )
            }
        )
