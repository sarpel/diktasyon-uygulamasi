from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QPlainTextEdit,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from dikte.config import Settings


class AdvancedTab(QWidget):
    """Nadiren değiştirilen çözümleme ve LLM örnekleme parametreleri."""

    title = "Gelişmiş"

    def __init__(self, settings: Settings, parent=None):
        super().__init__(parent)
        stt, llm = settings.stt, settings.llm

        self.beam_spin = QSpinBox()
        self.beam_spin.setRange(1, 10)
        self.beam_spin.setValue(stt.beam_size)
        self.beam_spin.setToolTip("turbo modelde 1–2 genellikle yeterli; büyük değer yavaşlatır")
        self.initial_prompt_edit = QPlainTextEdit(stt.initial_prompt)
        self.initial_prompt_edit.setMaximumHeight(70)
        self.initial_prompt_edit.setToolTip("Modele verilen bağlam cümlesi; boş bırakılabilir")

        stt_group = QGroupBox("Çözümleme")
        stt_form = QFormLayout(stt_group)
        stt_form.addRow("beam_size", self.beam_spin)
        stt_form.addRow("Başlangıç promptu", self.initial_prompt_edit)

        self.num_ctx_spin = QSpinBox()
        self.num_ctx_spin.setRange(2048, 131072)
        self.num_ctx_spin.setSingleStep(1024)
        self.num_ctx_spin.setValue(llm.num_ctx)
        self.num_ctx_spin.setToolTip("Bağlam penceresi; büyütmek VRAM'de KV cache'i büyütür")
        self.top_p_spin = QDoubleSpinBox()
        self.top_p_spin.setRange(0.0, 1.0)
        self.top_p_spin.setSingleStep(0.05)
        self.top_p_spin.setValue(llm.top_p)
        self.top_k_spin = QSpinBox()
        self.top_k_spin.setRange(0, 200)
        self.top_k_spin.setValue(llm.top_k)
        self.timeout_spin = QDoubleSpinBox()
        self.timeout_spin.setRange(1.0, 600.0)
        self.timeout_spin.setSuffix(" sn")
        self.timeout_spin.setValue(llm.timeout_s)
        self.think_check = QCheckBox("Düşünme modu (yavaşlatır)")
        self.think_check.setChecked(llm.think)

        llm_group = QGroupBox("LLM örnekleme")
        llm_form = QFormLayout(llm_group)
        llm_form.addRow("num_ctx", self.num_ctx_spin)
        llm_form.addRow("top_p", self.top_p_spin)
        llm_form.addRow("top_k", self.top_k_spin)
        llm_form.addRow("Zaman aşımı", self.timeout_spin)
        llm_form.addRow(self.think_check)

        lay = QVBoxLayout(self)
        lay.addWidget(stt_group)
        lay.addWidget(llm_group)
        lay.addStretch(1)

    def validate(self) -> str | None:
        return None

    def apply(self, s: Settings) -> Settings:
        return s.model_copy(
            update={
                "stt": s.stt.model_copy(
                    update={
                        "beam_size": self.beam_spin.value(),
                        "initial_prompt": self.initial_prompt_edit.toPlainText().strip(),
                    }
                ),
                "llm": s.llm.model_copy(
                    update={
                        "num_ctx": self.num_ctx_spin.value(),
                        "top_p": self.top_p_spin.value(),
                        "top_k": self.top_k_spin.value(),
                        "timeout_s": float(self.timeout_spin.value()),
                        "think": self.think_check.isChecked(),
                    }
                ),
            }
        )
