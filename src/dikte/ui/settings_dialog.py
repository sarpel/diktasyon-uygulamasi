from __future__ import annotations

import logging
from functools import reduce

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QTabWidget,
    QVBoxLayout,
)

from dikte.config import Settings
from dikte.ui.settings import (
    AboutTab,
    AdvancedTab,
    AudioTab,
    DictionaryTab,
    GeneralTab,
    LlmTab,
    SttTab,
)

log = logging.getLogger(__name__)

# Sekmelerden diyaloğa yansıtılan alanlar: çağıran kod ve testler tek bir yüzey görür.
_PROXIED = {
    "general": (
        "hotkey_edit",
        "hotkey_translate_edit",
        "hotkey_prompt_edit",
        "autostart_check",
        "auto_copy_check",
        "auto_paste_check",
        "restore_clipboard_check",
        "raise_window_check",
        "close_after_copy_check",
        "sounds_check",
        "push_to_talk_check",
        "history_spin",
    ),
    "audio": ("device_combo", "max_seconds_spin", "silence_stop_spin", "level_bar", "test_btn"),
    "stt": (
        "stt_model_edit",
        "compute_combo",
        "language_edit",
        "batch_check",
        "batch_threshold_spin",
        "batch_size_spin",
        "warm_up_check",
        "vad_check",
        "vad_threshold_spin",
        "vad_min_silence_spin",
        "no_speech_spin",
        "vad_speech_pad_spin",
        "log_prob_spin",
        "hallucination_silence_spin",
        "hallucination_filter_check",
    ),
    "llm": (
        "llm_enabled_check",
        "prewarm_check",
        "provider_combo",
        "llm_model_edit",
        "ollama_host_edit",
        "keep_alive_edit",
        "lmstudio_base_url_edit",
        "lmstudio_model_edit",
        "lmstudio_key_env_edit",
        "lmstudio_group",
        "anthropic_model_edit",
        "anthropic_key_env_edit",
        "openai_model_edit",
        "openai_base_url_edit",
        "openai_key_env_edit",
        "gemini_model_edit",
        "gemini_key_env_edit",
        "custom_format_combo",
        "custom_base_url_edit",
        "custom_model_edit",
        "custom_key_env_edit",
        "ollama_group",
        "openai_group",
        "anthropic_group",
        "gemini_group",
        "custom_group",
        "privacy_label",
        "llm_test_btn",
        "llm_test_status",
    ),
    "dictionary": ("dictionary_table", "add_entry_btn", "remove_entry_btn", "instructions_edit"),
    "advanced": (
        "beam_spin",
        "initial_prompt_edit",
        "num_ctx_spin",
        "top_p_spin",
        "top_k_spin",
        "timeout_spin",
        "think_check",
    ),
    "about": ("gpu_label", "open_log_btn", "open_config_btn"),
}


def list_input_devices() -> tuple[tuple[int, str], ...]:
    try:
        import sounddevice as sd

        return tuple(
            (i, d["name"])
            for i, d in enumerate(sd.query_devices())
            if d.get("max_input_channels", 0) > 0
        )
    except Exception:
        log.exception("ses cihazları listelenemedi")
        return ()


class SettingsDialog(QDialog):
    """Sekmeli ayarlar; her sekme kendi doğrulamasını ve `apply` dönüşümünü yapar."""

    def __init__(self, settings: Settings, devices: tuple[tuple[int, str], ...], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Dikte Ayarları")
        self.resize(560, 520)
        self._settings = settings

        self.general = GeneralTab(settings)
        self.audio = AudioTab(settings, devices)
        self.stt = SttTab(settings)
        self.llm = LlmTab(settings)
        self.dictionary = DictionaryTab(settings)
        self.advanced = AdvancedTab(settings)
        self.about = AboutTab(settings)
        self._tabs_in_order = (
            self.general,
            self.audio,
            self.stt,
            self.llm,
            self.dictionary,
            self.advanced,
            self.about,
        )

        self.tabs = QTabWidget()
        for tab in self._tabs_in_order:
            self.tabs.addTab(tab, tab.title)

        self.error_label = QLabel("")
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet("color:#E53935;")
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        lay = QVBoxLayout(self)
        lay.addWidget(self.tabs, 1)
        lay.addWidget(self.error_label)
        lay.addWidget(buttons)

    # ---- eski düz form arayüzüyle uyum
    def __getattr__(self, name: str):
        for tab_name, widgets in _PROXIED.items():
            if name in widgets:
                return getattr(object.__getattribute__(self, tab_name), name)
        raise AttributeError(name)

    def accept(self) -> None:
        for tab in self._tabs_in_order:
            problem = tab.validate()
            if problem:
                self.error_label.setText(problem)
                self.tabs.setCurrentWidget(tab)
                return
        self.error_label.setText("")
        self.audio.stop_test()
        super().accept()

    def reject(self) -> None:
        self.audio.stop_test()
        super().reject()

    def result_settings(self) -> Settings:
        return reduce(lambda s, tab: tab.apply(s), self._tabs_in_order, self._settings)
