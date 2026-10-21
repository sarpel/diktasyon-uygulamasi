from typing import cast

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QDoubleSpinBox

from dikte.config import IndicatorSettings, Settings
from dikte.ui.settings.appearance_tab import AppearanceTab


def make(qtbot, settings=None, picker=None):
    kwargs = {"color_picker": picker} if picker else {}
    tab = AppearanceTab(settings or Settings(), **kwargs)
    qtbot.addWidget(tab)
    return tab


def test_every_indicator_field_has_a_widget(qtbot):
    """Yeni bir IndicatorSettings alanı GUI'siz kalmasın."""
    tab = make(qtbot)
    gui = {*tab.spins, "color_mode", "custom_color", "custom_color2"}
    assert gui == set(IndicatorSettings.model_fields)


def test_round_trip_keeps_values(qtbot):
    cfg = IndicatorSettings(
        size=120,
        sensitivity=2.5,
        max_spike=1.2,
        point_count=300,
        color_mode="custom",
        custom_color="#112233",
        custom_color2="#445566",
        bar_count=48,
    )
    s = Settings(indicator=cfg, overlay_indicator="wave", overlay_theme="nord")
    out = make(qtbot, s).apply(Settings())
    assert out.indicator == cfg
    assert out.overlay_indicator == "wave" and out.overlay_theme == "nord"


def test_spin_change_updates_preview(qtbot):
    tab = make(qtbot)
    tab.spins["size"].setValue(140)
    tab.spins["point_count"].setValue(60)
    assert tab.preview_sphere.width() == 140
    assert tab.preview_sphere.settings.point_count == 60
    assert tab.preview_sphere._points.shape == (60, 3)


def test_hue_order_is_validated(qtbot):
    tab = make(qtbot)
    cast(QDoubleSpinBox, tab.spins["hue_low"]).setValue(0.9)
    cast(QDoubleSpinBox, tab.spins["hue_high"]).setValue(0.1)
    assert tab.validate()


def test_color_button_uses_picker(qtbot):
    tab = make(qtbot, picker=lambda *_a: QColor("#ABCDEF"))
    tab.color_mode_combo.setCurrentIndex(tab.color_mode_combo.findData("custom"))
    tab.color1_btn.click()
    assert tab.indicator_settings().custom_color == "#ABCDEF"


def test_reset_restores_defaults(qtbot):
    tab = make(qtbot, Settings(indicator=IndicatorSettings(glow=2.5)))
    tab.reset_btn.click()
    assert tab.indicator_settings() == IndicatorSettings()


def test_fake_audio_drives_preview(qtbot):
    tab = make(qtbot)
    for _ in range(5):
        tab._push_fake_audio()
    assert tab.preview_sphere.level > 0
