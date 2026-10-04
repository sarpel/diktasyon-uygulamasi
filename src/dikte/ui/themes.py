"""Kayıt göstergesi (overlay) için renk temaları.

Popüler editör/terminal temalarının resmi paletlerinden seçilmiş renkler. Her tema; panel
arka planı, yazı, soluk yazı (canlı transkript), vurgu (kayıt noktası, dalga, küre),
ikinci vurgu (küre diken uçları), uyarı (durum noktası, uyarı satırı) ve hata rengini verir.
Yazı ile panel arasında en az 4.5:1 kontrast (WCAG AA) testlerle güvence altındadır.

Tema adları `config.Settings.overlay_theme` seçenekleriyle aynı olmalıdır (testte denetlenir).
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtGui import QColor

DEFAULT_THEME = "default"


@dataclass(frozen=True)
class OverlayTheme:
    """Bir overlay temasının renkleri (#RRGGBB) ve ayarlarda görünen adı."""

    label: str
    panel: str
    text: str
    muted: str
    accent: str
    accent2: str
    warning: str
    error: str
    panel_alpha: int = 235  # 0–255; panel hafif saydam kalsın
    light: bool = False  # açık temalarda düğme arka planı koyulaştırılır


THEMES: dict[str, OverlayTheme] = {
    "default": OverlayTheme(
        label="Varsayılan",
        panel="#141414",
        panel_alpha=225,
        text="#FFFFFF",
        muted="#BBBBBB",
        accent="#E53935",
        accent2="#FF8A65",
        warning="#F5A623",
        error="#E53935",
    ),
    "dracula": OverlayTheme(
        label="Dracula",
        panel="#282A36",
        text="#F8F8F2",
        muted="#BFBFBF",
        accent="#FF79C6",
        accent2="#BD93F9",
        warning="#FFB86C",
        error="#FF5555",
    ),
    "nord": OverlayTheme(
        label="Nord",
        panel="#2E3440",
        text="#ECEFF4",
        muted="#D8DEE9",
        accent="#88C0D0",
        accent2="#B48EAD",
        warning="#EBCB8B",
        error="#BF616A",
    ),
    "catppuccin_mocha": OverlayTheme(
        label="Catppuccin Mocha",
        panel="#1E1E2E",
        text="#CDD6F4",
        muted="#A6ADC8",
        accent="#CBA6F7",
        accent2="#F5C2E7",
        warning="#FAB387",
        error="#F38BA8",
    ),
    "catppuccin_latte": OverlayTheme(
        label="Catppuccin Latte (açık)",
        panel="#EFF1F5",
        text="#4C4F69",
        muted="#6C6F85",
        accent="#8839EF",
        accent2="#EA76CB",
        warning="#FE640B",
        error="#D20F39",
        light=True,
    ),
    "gruvbox": OverlayTheme(
        label="Gruvbox",
        panel="#282828",
        text="#EBDBB2",
        muted="#A89984",
        accent="#FB4934",
        accent2="#FABD2F",
        warning="#FE8019",
        error="#FB4934",
    ),
    "tokyo_night": OverlayTheme(
        label="Tokyo Night",
        panel="#1A1B26",
        text="#C0CAF5",
        muted="#A9B1D6",
        accent="#7AA2F7",
        accent2="#BB9AF7",
        warning="#E0AF68",
        error="#F7768E",
    ),
    "solarized_dark": OverlayTheme(
        label="Solarized Dark",
        panel="#002B36",
        text="#93A1A1",
        muted="#839496",
        accent="#2AA198",
        accent2="#B58900",
        warning="#CB4B16",
        error="#DC322F",
    ),
    "one_dark": OverlayTheme(
        label="One Dark",
        panel="#282C34",
        text="#ABB2BF",
        muted="#9DA5B4",
        accent="#61AFEF",
        accent2="#C678DD",
        warning="#E5C07B",
        error="#E06C75",
    ),
    "monokai": OverlayTheme(
        label="Monokai",
        panel="#272822",
        text="#F8F8F2",
        muted="#CFCFC2",
        accent="#F92672",
        accent2="#A6E22E",
        warning="#FD971F",
        error="#F92672",
    ),
}


def get_theme(name: str) -> OverlayTheme:
    """Adı verilen tema; bilinmiyorsa varsayılan (eski/elle bozulmuş ayara karşı)."""
    return THEMES.get(name, THEMES[DEFAULT_THEME])


def _luminance(color: str) -> float:
    def channel(v: float) -> float:
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    c = QColor(color)
    return 0.2126 * channel(c.redF()) + 0.7152 * channel(c.greenF()) + 0.0722 * channel(c.blueF())


def contrast_ratio(a: str, b: str) -> float:
    """WCAG kontrast oranı (1–21)."""
    la, lb = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)
