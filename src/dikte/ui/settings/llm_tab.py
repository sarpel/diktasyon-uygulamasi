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
from dikte.llm.keys import key_status

log = logging.getLogger(__name__)
PROVIDERS = ("ollama", "openai", "anthropic", "gemini", "custom")
KEY_PRESENT, KEY_MISSING = "✓ tanımlı", "✗ yok"


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

        self.openai_model_edit = QLineEdit(llm.openai_model)
        self.openai_base_url_edit = QLineEdit(llm.openai_base_url)
        self.openai_key_env_edit = QLineEdit(llm.openai_api_key_env)
        self.openai_key_status = QLabel()
        self.openai_group = QGroupBox("OpenAI")
        openai_form = QFormLayout(self.openai_group)
        openai_form.addRow("Model", self.openai_model_edit)
        openai_form.addRow("Base URL", self.openai_base_url_edit)
        openai_form.addRow("Anahtar ortam değişkeni", self.openai_key_env_edit)
        openai_form.addRow("Anahtar durumu", self.openai_key_status)

        self.anthropic_model_edit = QLineEdit(llm.anthropic_model)
        self.anthropic_key_env_edit = QLineEdit(llm.anthropic_api_key_env)
        self.anthropic_key_status = QLabel()
        self.anthropic_group = QGroupBox("Anthropic")
        anthropic_form = QFormLayout(self.anthropic_group)
        anthropic_form.addRow("Model", self.anthropic_model_edit)
        anthropic_form.addRow("Anahtar ortam değişkeni", self.anthropic_key_env_edit)
        anthropic_form.addRow("Anahtar durumu", self.anthropic_key_status)

        self.gemini_model_edit = QLineEdit(llm.gemini_model)
        self.gemini_key_env_edit = QLineEdit(llm.gemini_api_key_env)
        self.gemini_key_status = QLabel()
        self.gemini_group = QGroupBox("Gemini")
        gemini_form = QFormLayout(self.gemini_group)
        gemini_form.addRow("Model", self.gemini_model_edit)
        gemini_form.addRow("Anahtar ortam değişkeni", self.gemini_key_env_edit)
        gemini_form.addRow("Anahtar durumu", self.gemini_key_status)

        self.custom_format_combo = QComboBox()
        self.custom_format_combo.addItems(("openai", "anthropic"))
        self.custom_format_combo.setCurrentText(llm.custom_format)
        self.custom_format_combo.setToolTip(
            "Uç noktanın konuştuğu protokol: OpenAI-uyumlu (ör. LM Studio, vLLM) "
            "veya Anthropic-uyumlu proxy."
        )
        self.custom_base_url_edit = QLineEdit(llm.custom_base_url)
        self.custom_base_url_edit.setPlaceholderText("http://localhost:1234/v1")
        self.custom_model_edit = QLineEdit(llm.custom_model)
        self.custom_key_env_edit = QLineEdit(llm.custom_api_key_env)
        self.custom_key_env_edit.setPlaceholderText("boş = anahtar gönderilmez")
        self.custom_key_status = QLabel()
        self.custom_group = QGroupBox("Özel uç nokta")
        custom_form = QFormLayout(self.custom_group)
        custom_form.addRow("Format", self.custom_format_combo)
        custom_form.addRow("Base URL", self.custom_base_url_edit)
        custom_form.addRow("Model", self.custom_model_edit)
        custom_form.addRow("Anahtar ortam değişkeni", self.custom_key_env_edit)
        custom_form.addRow("Anahtar durumu", self.custom_key_status)

        self._key_fields = (
            (self.openai_key_env_edit, self.openai_key_status),
            (self.anthropic_key_env_edit, self.anthropic_key_status),
            (self.gemini_key_env_edit, self.gemini_key_status),
            (self.custom_key_env_edit, self.custom_key_status),
        )
        for edit, label in self._key_fields:
            edit.textChanged.connect(self.refresh_key_status)
            label.setToolTip("Anahtarın değeri hiçbir zaman gösterilmez veya kaydedilmez.")
        self.refresh_key_status()

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
        return (
            self.ollama_group,
            self.openai_group,
            self.anthropic_group,
            self.gemini_group,
            self.custom_group,
        )

    def _group_for(self, provider: str) -> QGroupBox:
        return {
            "ollama": self.ollama_group,
            "openai": self.openai_group,
            "anthropic": self.anthropic_group,
            "gemini": self.gemini_group,
            "custom": self.custom_group,
        }[provider]

    def refresh_key_status(self) -> None:
        """Yalnızca anahtarın tanımlı olup olmadığını gösterir; değeri okunmaz."""
        for edit, label in self._key_fields:
            label.setText(KEY_PRESENT if key_status(edit.text().strip()) else KEY_MISSING)

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
        if provider == "openai" and not self.openai_model_edit.text().strip():
            return "OpenAI model adı boş olamaz"
        if provider == "anthropic" and not self.anthropic_model_edit.text().strip():
            return "Anthropic model adı boş olamaz"
        if provider == "gemini" and not self.gemini_model_edit.text().strip():
            return "Gemini model adı boş olamaz"
        if provider == "custom":
            if not self.custom_base_url_edit.text().strip():
                return "Özel sağlayıcı için base URL gerekli"
            if not self.custom_model_edit.text().strip():
                return "Özel sağlayıcı için model adı gerekli"
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
                        "openai_model": self.openai_model_edit.text().strip(),
                        "openai_base_url": self.openai_base_url_edit.text().strip(),
                        "openai_api_key_env": self.openai_key_env_edit.text().strip(),
                        "anthropic_model": self.anthropic_model_edit.text().strip(),
                        "anthropic_api_key_env": self.anthropic_key_env_edit.text().strip(),
                        "gemini_model": self.gemini_model_edit.text().strip(),
                        "gemini_api_key_env": self.gemini_key_env_edit.text().strip(),
                        "custom_format": self.custom_format_combo.currentText(),
                        "custom_base_url": self.custom_base_url_edit.text().strip(),
                        "custom_model": self.custom_model_edit.text().strip(),
                        "custom_api_key_env": self.custom_key_env_edit.text().strip(),
                    }
                )
            }
        )
