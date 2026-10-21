"""Ayarlar → Görünüm sekmesi: kayıt göstergesi (küre / dalga) ve tema, canlı önizlemeli."""

from __future__ import annotations

import math
from typing import cast

from PySide6.QtCore import QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QColorDialog,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from dikte.config import IndicatorSettings, Settings
from dikte.ui.settings._reset import make_reset_button, reset_row
from dikte.ui.sphere import SphereWidget
from dikte.ui.themes import THEMES, get_theme
from dikte.ui.waveform import WaveformWidget

OVERLAY_INDICATORS = (
    ("sphere", "Küre"),
    ("wave", "Dalga"),
)

COLOR_MODES = (
    ("holo", "Holografik (ton aralığı)"),
    ("theme", "Tema renkleri"),
    ("custom", "Özel iki renk"),
)

# (alan, etiket, alt, üst, adım, ipucu) — float alanlar QDoubleSpinBox, int alanlar QSpinBox.
_COMMON = (
    ("size", "Boyut", 48, 240, 4, "Kürenin kutusu / dalganın yüksekliği (piksel)."),
    (
        "sensitivity",
        "Duyarlılık",
        0.2,
        5.0,
        0.1,
        "Ses seviyesi çarpanı; sessiz mikrofonda artırın.",
    ),
    ("decay", "Sönüm", 0.5, 0.99, 0.01, "Ses kesilince dikenlerin/çubukların inme yavaşlığı."),
    ("fps", "Kare hızı", 10, 60, 5, "Saniyedeki çizim sayısı; düşük değer CPU'yu rahatlatır."),
)
_SPHERE = (
    ("hue_low", "Ton başı", 0.0, 1.0, 0.01, "Holografik kipte ton aralığının başı (0–1)."),
    ("hue_high", "Ton sonu", 0.0, 1.0, 0.01, "Holografik kipte ton aralığının sonu (0–1)."),
    ("point_count", "Diken sayısı", 30, 600, 10, "Kürenin yüzeyindeki diken sayısı."),
    ("max_spike", "En uzun diken", 0.1, 2.0, 0.05, "Tam seste dikenin yarıçapa oranı."),
    ("rest_spike", "Sessizlikte diken", 0.0, 0.5, 0.01, "Ses yokken kalan diken boyu."),
    ("spikiness", "Düzensizlik", 0.0, 1.0, 0.05, "0: tüm dikenler eşit uzar, 1: çok düzensiz."),
    ("spin_speed", "Dönüş hızı", 0.0, 5.0, 0.1, "Radyan/sn; 0 = sabit küre."),
    ("tilt", "Eğim", -1.5, 1.5, 0.05, "Kürenin bakış açısı (radyan)."),
    ("glow", "Parıltı", 0.0, 3.0, 0.1, "Neon hale yoğunluğu; 0 = kapalı."),
    ("line_width", "Çizgi kalınlığı", 0.3, 4.0, 0.1, "Diken kalınlığı çarpanı."),
    ("shimmer_speed", "Renk kayması", 0.0, 5.0, 0.1, "Holografik renk akışının hızı."),
    ("core_opacity", "Çekirdek", 0.0, 3.0, 0.1, "Cam çekirdeğin görünürlüğü; 0 = yalnız dikenler."),
)
_WAVE = (
    ("bar_count", "Çubuk sayısı", 8, 128, 1, "Dalgadaki çubuk sayısı."),
    ("wave_width", "Genişlik", 80, 600, 10, "Dalganın genişliği (piksel)."),
    ("bar_gap", "Çubuk aralığı", 0.0, 8.0, 0.5, "Çubuklar arası boşluk (piksel)."),
)


def _spin(lo, hi, step, tip) -> QSpinBox | QDoubleSpinBox:
    box = QSpinBox() if isinstance(lo, int) and isinstance(step, int) else QDoubleSpinBox()
    if isinstance(box, QDoubleSpinBox):
        box.setDecimals(2)
    box.setRange(lo, hi)
    box.setSingleStep(step)
    box.setToolTip(tip)
    return box


class ColorButton(QPushButton):
    """Rengini gösteren ve tıklanınca renk seçici açan düğme; `color` #RRGGBB."""

    def __init__(self, on_change, picker=QColorDialog.getColor, parent=None):
        super().__init__(parent)
        self._picker = picker
        self._on_change = on_change
        self.color = "#000000"
        self.clicked.connect(self._pick)

    def set_color(self, color: str) -> None:
        self.color = QColor(color).name().upper()
        self.setText(self.color)
        # :enabled — devre dışıyken (renk kipi özel değilse) sistem stiline döner, soluk görünür.
        self.setStyleSheet(
            f"QPushButton:enabled{{background:{self.color};color:{_contrast(self.color)};}}"
        )

    def _pick(self) -> None:
        chosen = self._picker(QColor(self.color), self, "Renk seçin")
        if chosen.isValid():
            self.set_color(chosen.name())
            self._on_change()


def _contrast(color: str) -> str:
    return "#000000" if QColor(color).lightness() > 140 else "#FFFFFF"


class AppearanceTab(QWidget):
    """Kayıt göstergesinin türü, teması ve küre/dalga animasyonunun her parametresi.

    Sağdaki önizleme değişikliği anında gösterir; "Önizleme sesi" yapay ses seviyesi verir.
    Ton başı ton sonundan büyük olamaz (doğrulama)."""

    title = "Görünüm"

    def __init__(self, settings: Settings, parent=None, color_picker=QColorDialog.getColor):
        super().__init__(parent)
        self.overlay_indicator_combo = QComboBox()
        for value, label in OVERLAY_INDICATORS:
            self.overlay_indicator_combo.addItem(label, value)
        self.overlay_indicator_combo.setToolTip(
            "Kayıt sırasında sese tepki veren animasyon: dikenleri sesle uzayan dönen bir "
            "küre ya da çubuk dalga."
        )
        self.overlay_theme_combo = QComboBox()
        for value, theme in THEMES.items():
            self.overlay_theme_combo.addItem(theme.label, value)
        self.overlay_theme_combo.setToolTip("Kayıt göstergesinin renk teması.")
        self.color_mode_combo = QComboBox()
        for value, label in COLOR_MODES:
            self.color_mode_combo.addItem(label, value)
        self.color_mode_combo.setToolTip("Küre dikenlerinin renkleri nereden gelsin.")
        self.color1_btn = ColorButton(self._refresh_preview, color_picker)
        self.color2_btn = ColorButton(self._refresh_preview, color_picker)
        self.color1_btn.setToolTip("Özel kipte birinci renk")
        self.color2_btn.setToolTip("Özel kipte ikinci renk")

        self.spins: dict[str, QSpinBox | QDoubleSpinBox] = {}
        top = QFormLayout()
        top.addRow("Kayıt göstergesi", self.overlay_indicator_combo)
        top.addRow("Gösterge teması", self.overlay_theme_combo)
        common = self._group("Ortak", _COMMON)
        sphere = self._group("Küre", _SPHERE)
        sphere_form = cast(QFormLayout, sphere.layout())
        sphere_form.insertRow(0, "Renk kipi", self.color_mode_combo)
        colors = QHBoxLayout()
        colors.addWidget(self.color1_btn)
        colors.addWidget(self.color2_btn)
        sphere_form.insertRow(1, "Özel renkler", colors)
        wave = self._group("Dalga", _WAVE)

        self.preview_sphere = SphereWidget()
        self.preview_wave = WaveformWidget()
        self.preview_btn = QPushButton("Önizleme sesi")
        self.preview_btn.setCheckable(True)
        self.preview_btn.setToolTip("Önizlemeye yapay ses seviyesi gönderir")
        self._fake_audio = QTimer(self)
        self._fake_audio.setInterval(60)
        self._fake_audio.timeout.connect(self._push_fake_audio)
        self._fake_t = 0
        self.preview_btn.toggled.connect(
            lambda on: self._fake_audio.start() if on else self._fake_audio.stop()
        )
        preview = QGroupBox("Önizleme")
        preview_lay = QVBoxLayout(preview)
        preview_lay.addWidget(self.preview_sphere)
        preview_lay.addWidget(self.preview_wave)
        preview_lay.addWidget(self.preview_btn)
        preview_lay.addStretch(1)

        self.reset_btn = make_reset_button(lambda: self.load(Settings()))
        left = QVBoxLayout()
        left.addLayout(top)
        for group in (common, sphere, wave):
            left.addWidget(group)
        left.addLayout(reset_row(self.reset_btn))
        row = QHBoxLayout(self)
        row.addLayout(left, 1)
        row.addWidget(preview)

        for box in self.spins.values():
            box.valueChanged.connect(self._refresh_preview)
        for combo in (
            self.overlay_indicator_combo,
            self.overlay_theme_combo,
            self.color_mode_combo,
        ):
            combo.currentIndexChanged.connect(self._refresh_preview)
        self.load(settings)

    def _group(self, title: str, fields) -> QGroupBox:
        group = QGroupBox(title)
        form = QFormLayout(group)
        for name, label, lo, hi, step, tip in fields:
            self.spins[name] = _spin(lo, hi, step, tip)
            form.addRow(label, self.spins[name])
        return group

    # ---- sözleşme
    def load(self, settings: Settings) -> None:
        """Alanları `settings`ten doldurur; "Varsayılanlara döndür" de bunu kullanır."""
        for combo, value in (
            (self.overlay_indicator_combo, settings.overlay_indicator),
            (self.overlay_theme_combo, settings.overlay_theme),
            (self.color_mode_combo, settings.indicator.color_mode),
        ):
            combo.setCurrentIndex(max(combo.findData(value), 0))
        for name, box in self.spins.items():
            box.setValue(getattr(settings.indicator, name))
        self.color1_btn.set_color(settings.indicator.custom_color)
        self.color2_btn.set_color(settings.indicator.custom_color2)
        self._refresh_preview()

    def indicator_settings(self) -> IndicatorSettings:
        return IndicatorSettings.model_validate(
            {
                **{name: box.value() for name, box in self.spins.items()},
                "color_mode": self.color_mode_combo.currentData(),
                "custom_color": self.color1_btn.color,
                "custom_color2": self.color2_btn.color,
            }
        )

    def validate(self) -> str | None:
        if self.spins["hue_low"].value() > self.spins["hue_high"].value():
            return "Görünüm: ton başı ton sonundan büyük olamaz"
        return None

    def apply(self, s: Settings) -> Settings:
        return s.model_copy(
            update={
                "overlay_indicator": self.overlay_indicator_combo.currentData(),
                "overlay_theme": self.overlay_theme_combo.currentData(),
                "indicator": self.indicator_settings(),
            }
        )

    # ---- önizleme
    def _refresh_preview(self) -> None:
        if self.validate() is not None:
            return
        cfg = self.indicator_settings()
        theme = get_theme(self.overlay_theme_combo.currentData())
        self.preview_sphere.set_settings(cfg)
        self.preview_sphere.set_colors(theme.accent, theme.accent2)
        self.preview_sphere.setFixedSize(cfg.size, cfg.size)
        self.preview_wave.set_settings(cfg)
        self.preview_wave.set_color(theme.accent)
        self.preview_wave.setFixedSize(cfg.wave_width, 44)
        sphere = self.overlay_indicator_combo.currentData() == "sphere"
        self.preview_sphere.setVisible(sphere)
        self.preview_wave.setVisible(not sphere)
        for name in ("hue_low", "hue_high"):
            self.spins[name].setEnabled(cfg.color_mode == "holo")
        for btn in (self.color1_btn, self.color2_btn):
            btn.setEnabled(cfg.color_mode == "custom")

    def _push_fake_audio(self) -> None:
        self._fake_t += 1
        level = 0.5 + 0.5 * math.sin(self._fake_t * 0.35)
        buckets = tuple(level * (0.5 + 0.5 * math.sin(self._fake_t * 0.9 + i)) for i in range(16))
        self.preview_sphere.push_buckets(buckets)
        self.preview_wave.push_buckets(buckets)
