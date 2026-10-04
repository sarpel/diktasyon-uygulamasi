import typing

import pytest
from PySide6.QtGui import QColor

from dikte.config import Settings
from dikte.ui.overlay import RecordingOverlay
from dikte.ui.themes import DEFAULT_THEME, THEMES, contrast_ratio, get_theme


def test_theme_names_match_config_choices():
    """Ayar şemasındaki seçenekler ile tema tablosu aynı olmalı (biri eklenip diğeri
    unutulursa ayar doğrulaması ya da arayüz bozulur)."""
    field = Settings.model_fields["overlay_theme"]
    assert set(typing.get_args(field.annotation)) == set(THEMES)
    assert Settings().overlay_theme == DEFAULT_THEME == "default"


@pytest.mark.parametrize("name", sorted(THEMES))
def test_every_theme_color_is_valid(name):
    t = THEMES[name]
    for color in (t.panel, t.text, t.muted, t.accent, t.accent2, t.warning, t.error):
        assert QColor(color).isValid(), (name, color)
    assert 0 < t.panel_alpha <= 255
    assert t.label  # ayarlarda gösterilen Türkçe/özgün ad


@pytest.mark.parametrize("name", sorted(THEMES))
def test_every_theme_text_is_readable(name):
    """WCAG AA: normal metin için en az 4.5:1 kontrast."""
    t = THEMES[name]
    assert contrast_ratio(t.text, t.panel) >= 4.5, name


def test_default_theme_keeps_original_look():
    t = THEMES["default"]
    assert (t.panel, t.panel_alpha, t.accent, t.warning) == ("#141414", 225, "#E53935", "#F5A623")


def test_unknown_theme_falls_back_to_default():
    assert get_theme("yok-boyle-tema") is THEMES[DEFAULT_THEME]


def test_contrast_ratio_extremes():
    assert contrast_ratio("#000000", "#FFFFFF") == pytest.approx(21.0, rel=1e-3)
    assert contrast_ratio("#777777", "#777777") == pytest.approx(1.0)


def test_overlay_applies_theme_colors(qtbot):
    o = RecordingOverlay()
    qtbot.addWidget(o)
    t = THEMES["dracula"]
    o.set_theme("dracula")
    assert o.theme == "dracula"
    assert QColor(t.panel).red() == QColor("#282A36").red()
    assert "40,42,54" in o.styleSheet()  # panel rgba
    o.show_recording()
    assert t.accent.lower() in o._dot.styleSheet().lower()
    assert o._sphere._base == QColor(t.accent) and o._sphere._tip == QColor(t.accent2)
    assert o._wave._color == QColor(t.accent)


def test_overlay_status_and_error_dots_use_theme_roles(qtbot):
    o = RecordingOverlay()
    qtbot.addWidget(o)
    t = THEMES["nord"]
    o.set_theme("nord")
    o.show_status("Düzeltiliyor…")
    assert t.warning.lower() in o._dot.styleSheet().lower()
    o.show_error("olmadı")
    assert t.error.lower() in o._dot.styleSheet().lower()


def test_theme_change_keeps_overlay_hidden(qtbot):
    o = RecordingOverlay()
    qtbot.addWidget(o)
    o.set_theme("gruvbox")
    assert not o.isVisible()


def test_settings_theme_combo(qtbot):
    from dikte.ui.settings_dialog import SettingsDialog

    d = SettingsDialog(Settings(), ())
    qtbot.addWidget(d)
    combo = d.overlay_theme_combo
    assert combo.count() == len(THEMES)
    assert combo.currentData() == "default"
    assert combo.itemText(0) == "Varsayılan"
    combo.setCurrentIndex(combo.findData("tokyo_night"))
    assert d.result_settings().overlay_theme == "tokyo_night"


def test_settings_theme_combo_loads_saved_value(qtbot):
    from dikte.ui.settings_dialog import SettingsDialog

    d = SettingsDialog(Settings(overlay_theme="catppuccin_latte"), ())
    qtbot.addWidget(d)
    assert d.overlay_theme_combo.currentData() == "catppuccin_latte"


def test_invalid_theme_in_config_resets_only_that_field(tmp_path):
    import json

    from dikte.config import load_settings_with_issues

    p = tmp_path / "config.json"
    p.write_text(json.dumps({"hotkey": "f9", "overlay_theme": "pembe"}), encoding="utf-8")
    s, issues = load_settings_with_issues(p)
    assert s.hotkey == "f9" and s.overlay_theme == "default"
    assert issues == ("overlay_theme",)


def test_overlay_unknown_theme_name_reports_default(qtbot):
    o = RecordingOverlay()
    qtbot.addWidget(o)
    o.set_theme("yok-boyle-tema")
    assert o.theme == "default"


@pytest.mark.parametrize("show_first", [False, True])
def test_panel_is_painted_in_theme_color(qtbot, show_first):
    """Stil metninin doğru olması yetmez; panel gerçekten tema rengiyle çizilmeli. Tema,
    overlay hiç gösterilmeden (açılışta, ayar kaydında) uygulandığında Qt eski stili
    önbellekte tutup varsayılan renkle çiziyordu."""
    from PySide6.QtWidgets import QApplication

    o = RecordingOverlay()
    qtbot.addWidget(o)
    if show_first:
        o.show_recording()
    o.set_theme("catppuccin_latte")
    o.show_recording()
    QApplication.processEvents()
    img = o.grab().toImage()
    top_middle = img.pixelColor(img.width() // 2, 6)
    assert top_middle.lightness() > 200  # açık tema: açık panel
