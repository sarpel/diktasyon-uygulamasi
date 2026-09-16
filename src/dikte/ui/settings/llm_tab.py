from __future__ import annotations

import logging

from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from dikte.config import LlmSettings, Settings
from dikte.core.workers import run_in_pool
from dikte.llm import make_provider
from dikte.llm.keys import key_status
from dikte.llm.provider import LlmError

log = logging.getLogger(__name__)
PROVIDERS = ("ollama", "lmstudio", "openai", "anthropic", "gemini", "custom")
# Dikte metninin makineden çıktığı sağlayıcılar; uyarı yalnızca bunlarda gösterilir.
REMOTE_PROVIDERS = ("openai", "anthropic", "gemini", "custom")
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
        self.ollama_host_edit.setToolTip(
            "Ollama sunucusunun adresi. Varsayılan port 11434; başka bir uygulama "
            "bu portu kullanıyorsa Ollama'yı taşıyıp adresi burada değiştirin."
        )
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

        self.lmstudio_base_url_edit = QLineEdit(llm.lmstudio_base_url)
        self.lmstudio_base_url_edit.setToolTip(
            "LM Studio'nun yerel sunucu adresi (Developer > Start Server). "
            "Varsayılan port 1234 ve yol /v1 olmalıdır."
        )
        self.lmstudio_model_edit = QLineEdit(llm.lmstudio_model)
        self.lmstudio_model_edit.setPlaceholderText("LM Studio'daki model kimliği")
        self.lmstudio_key_env_edit = QLineEdit(llm.lmstudio_api_key_env)
        self.lmstudio_key_env_edit.setPlaceholderText("boş = anahtar gönderilmez")
        self.lmstudio_key_status = QLabel()
        self.lmstudio_group = QGroupBox("LM Studio (yerel)")
        lmstudio_form = QFormLayout(self.lmstudio_group)
        lmstudio_form.addRow("Base URL", self.lmstudio_base_url_edit)
        lmstudio_form.addRow("Model", self.lmstudio_model_edit)
        lmstudio_form.addRow("Anahtar ortam değişkeni", self.lmstudio_key_env_edit)
        lmstudio_form.addRow("Anahtar durumu", self.lmstudio_key_status)

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
            (self.lmstudio_key_env_edit, self.lmstudio_key_status),
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

        self.llm_test_btn = QPushButton("Bağlantıyı test et")
        self.llm_test_status = QLabel("")
        self.llm_test_btn.clicked.connect(self._test_connection)

        top = QFormLayout()
        top.addRow(self.llm_enabled_check)
        top.addRow("Sağlayıcı", self.provider_combo)
        top.addRow(self.prewarm_check)

        lay = QVBoxLayout(self)
        lay.addLayout(top)
        for group in self._groups():
            lay.addWidget(group)
        lay.addWidget(self.privacy_label)
        test_row = QHBoxLayout()
        test_row.addWidget(self.llm_test_btn)
        test_row.addWidget(self.llm_test_status, 1)
        lay.addLayout(test_row)
        lay.addStretch(1)

        self.provider_combo.currentTextChanged.connect(self._show_group)
        self.llm_enabled_check.toggled.connect(self._set_fields_enabled)
        self._show_group(llm.provider)
        self._set_fields_enabled(llm.enabled)

    # ---- iç
    def _groups(self) -> tuple[QGroupBox, ...]:
        return (
            self.ollama_group,
            self.lmstudio_group,
            self.openai_group,
            self.anthropic_group,
            self.gemini_group,
            self.custom_group,
        )

    def _group_for(self, provider: str) -> QGroupBox:
        return {
            "ollama": self.ollama_group,
            "lmstudio": self.lmstudio_group,
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
        self.privacy_label.setVisible(provider in REMOTE_PROVIDERS)

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
        if provider == "ollama":
            if not self.llm_model_edit.text().strip():
                return "LLM model adı boş olamaz"
            if not self.ollama_host_edit.text().strip():
                return "Ollama host adresi boş olamaz (varsayılan http://127.0.0.1:11434)"
        if provider == "lmstudio":
            if not self.lmstudio_base_url_edit.text().strip():
                return "LM Studio için base URL gerekli (varsayılan http://127.0.0.1:1234/v1)"
            if not self.lmstudio_model_edit.text().strip():
                return "LM Studio için model adı gerekli"
        if provider == "openai":
            if not self.openai_model_edit.text().strip():
                return "OpenAI model adı boş olamaz"
            if not self.openai_base_url_edit.text().strip():
                return "OpenAI için base URL gerekli (varsayılan https://api.openai.com/v1)"
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
        return s.model_copy(update={"llm": s.llm.model_copy(update=self._llm_updates())})

    def _llm_updates(self) -> dict:
        return {
            "enabled": self.llm_enabled_check.isChecked(),
            "prewarm": self.prewarm_check.isChecked(),
            "provider": self.provider_combo.currentText(),
            "model": self.llm_model_edit.text().strip(),
            "ollama_host": self.ollama_host_edit.text().strip(),
            "keep_alive": self.keep_alive_edit.text().strip() or "0",
            "lmstudio_base_url": self.lmstudio_base_url_edit.text().strip(),
            "lmstudio_model": self.lmstudio_model_edit.text().strip(),
            "lmstudio_api_key_env": self.lmstudio_key_env_edit.text().strip(),
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

    def _snapshot_llm_settings(self) -> LlmSettings:
        return LlmSettings().model_copy(update=self._llm_updates())

    def _test_connection(self) -> None:
        """Seçili sağlayıcıyı arka planda dener; UI thread'i bloklamaz."""
        problem = self.validate()
        if problem:
            self.llm_test_status.setText(f"✗ {problem}")
            return
        self.llm_test_btn.setEnabled(False)
        self.llm_test_status.setText("Sınanıyor…")
        try:
            provider = make_provider(self._snapshot_llm_settings())
        except LlmError as exc:
            self._test_done(f"✗ {exc}")
            return
        run_in_pool(
            lambda: provider.complete("Yanıt: OK", "OK"),
            lambda text: self._test_done("✓ Bağlantı kuruldu"),
            lambda exc: self._test_done(f"✗ {exc}"),
            QThreadPool.globalInstance(),
        )

    def _test_done(self, message: str) -> None:
        self.llm_test_btn.setEnabled(True)
        self.llm_test_status.setText(message)
