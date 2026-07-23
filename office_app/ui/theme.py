"""Single source of truth for application colors, spacing, and radii."""

from PyQt6.QtGui import QColor

LIGHT_THEME = {
    # Brand
    "primary": "#073C33",
    "primary_hover": "#0B5144",
    "primary_pressed": "#052E27",
    "primary_soft": "#EAF3EF",
    "primary_selected": "#DCEDE6",
    "secondary": "#60756F",
    "accent": "#F2B705",
    "accent_soft": "#FFF4CF",

    # Surfaces
    "app_background": "#FAF8F3",
    "surface": "#FFFDF9",
    "surface_subtle": "#EAF3EF",
    "surface_raised": "#FFFFFF",

    # Text
    "text_primary": "#17322C",
    "text_secondary": "#60756F",
    "text_disabled": "#8A9B96",

    # Borders
    "border": "#DDE5DF",
    "border_subtle": "#E3E9E5",

    # Navigation shell
    "sidebar": "#073C33",
    "sidebar_surface": "#10483E",
    "sidebar_selected": "#19574B",
    "sidebar_text": "#F8F6EF",
    "sidebar_muted": "#A9C9BF",
    "sidebar_nav": "#D9E8E3",
    "sidebar_subtitle": "#BBD3CA",
    "sidebar_active_text": "#FFFFFF",
    "sidebar_group": "#8FC2B2",
    "sidebar_operator": "#9FD0C2",
    "sidebar_version": "#9FC8BC",
    "sidebar_border": "#246458",

    # Semantic — success
    "success": "#0E8A68",
    "success_hover": "#0B7559",
    "success_pressed": "#085E48",
    "success_soft": "#E6F4EE",

    # Semantic — warning
    "warning": "#C89000",
    "warning_hover": "#A97700",
    "warning_pressed": "#865E00",
    "warning_soft": "#FFF4CF",

    # Semantic — danger
    "danger": "#C95555",
    "danger_hover": "#B24343",
    "danger_pressed": "#963636",
    "danger_soft": "#FBEDED",

    # Semantic — graduated (distinct purple, not a standard semantic state)
    "graduated": "#7056D8",
    "graduated_soft": "#F0ECFF",

    # Semantic — neutral (used for disabled/unknown states in progress bars, badges)
    "neutral": "#98A2B3",
    "neutral_soft": "#F2F4F7",

    # Misc
    "on_brand": "#FFFFFF",
    "shadow": "#26352F",
    "splash_start": "#0A241D",
    "splash_end": "#176B52",

    # QSS spacing values; the numeric Python equivalents are defined by Spacing.
    "space_xxs": "4px",
    "space_xs": "8px",
    "space_sm": "12px",
    "space_md": "16px",
    "space_lg": "24px",
    "space_xl": "32px",

    # Radii
    "radius_sm": "4px",
    "radius_md": "8px",
    "radius_lg": "12px",
    "radius_pill": "999px",
}

DARK_THEME = {
    # Brand
    "primary": "#4FC39A",
    "primary_hover": "#63D2AA",
    "primary_pressed": "#7ADDB8",
    "primary_soft": "#17352B",
    "primary_selected": "#214C3D",
    "secondary": "#A7B8B0",
    "accent": "#F5C451",
    "accent_soft": "#413719",

    # Surfaces
    "app_background": "#101714",
    "surface": "#18211D",
    "surface_subtle": "#202C27",
    "surface_raised": "#202C27",

    # Text
    "text_primary": "#FFFFFF",
    "text_secondary": "#B4C2BB",
    "text_disabled": "#72837A",

    # Borders
    "border": "#3B4B43",
    "border_subtle": "#2A3832",

    # Navigation shell
    "sidebar": "#091510",
    "sidebar_surface": "#14271F",
    "sidebar_selected": "#203B30",
    "sidebar_text": "#F7F5EE",
    "sidebar_muted": "#9DB1A7",
    "sidebar_nav": "#D9E8E3",
    "sidebar_subtitle": "#BBD3CA",
    "sidebar_active_text": "#FFFFFF",
    "sidebar_group": "#8FC2B2",
    "sidebar_operator": "#9FD0C2",
    "sidebar_version": "#9FC8BC",
    "sidebar_border": "#246458",

    # Semantic — success
    "success": "#66bb6a",
    "success_hover": "#76c27a",
    "success_pressed": "#86ca8a",
    "success_soft": "#1c331d",

    # Semantic — warning
    "warning": "#ffa726",
    "warning_hover": "#ffb746",
    "warning_pressed": "#ffc766",
    "warning_soft": "#332a1e",

    # Semantic — danger
    "danger": "#ef5350",
    "danger_hover": "#ff6360",
    "danger_pressed": "#ff7370",
    "danger_soft": "#3e2323",

    # Semantic — graduated (distinct purple, not a standard semantic state)
    "graduated": "#ab47bc",
    "graduated_soft": "#3c234a",

    # Semantic — neutral (used for disabled/unknown states in progress bars, badges)
    "neutral": "#757575",
    "neutral_soft": "#3e3e3e",

    # Misc
    "on_brand": "#07130F",
    "shadow": "#000000",
    "splash_start": "#073E30",
    "splash_end": "#136B50",

    # QSS spacing values; the numeric Python equivalents are defined by Spacing.
    "space_xxs": "4px",
    "space_xs": "8px",
    "space_sm": "12px",
    "space_md": "16px",
    "space_lg": "24px",
    "space_xl": "32px",

    # Radii
    "radius_sm": "4px",
    "radius_md": "8px",
    "radius_lg": "12px",
    "radius_pill": "999px",
}

TYPOGRAPHY_DEFAULT = {
    "font_micro": "10px",
    "font_caption": "12px",
    "font_body": "14px",
    "font_subheading": "16px",
    "font_heading": "20px",
    "font_display": "26px",
    "font_metric": "32px",
}

TYPOGRAPHY_LARGE = {
    "font_micro": "12px",
    "font_caption": "14px",
    "font_body": "16px",
    "font_subheading": "18px",
    "font_heading": "23px",
    "font_display": "30px",
    "font_metric": "36px",
}

DESIGN_TOKENS = LIGHT_THEME

THEMES = {
    "Light": LIGHT_THEME,
    "Dark": DARK_THEME,
}

_large_text_enabled = False
_active_theme_tokens = {
    **DESIGN_TOKENS,
    **TYPOGRAPHY_DEFAULT,
}

def set_active_theme(theme_name: str):
    """Sets the active theme for the application."""
    global _active_theme_tokens
    palette = THEMES.get(theme_name, DESIGN_TOKENS)
    typography = (
        TYPOGRAPHY_LARGE if _large_text_enabled else TYPOGRAPHY_DEFAULT
    )
    _active_theme_tokens = {**palette, **typography}


def set_large_text(enabled: bool) -> None:
    """Switch typography tokens while preserving the active color palette."""
    global _large_text_enabled
    _large_text_enabled = bool(enabled)
    typography = (
        TYPOGRAPHY_LARGE if _large_text_enabled else TYPOGRAPHY_DEFAULT
    )
    _active_theme_tokens.update(typography)

def get_active_theme_tokens():
    """Returns the currently active theme tokens."""
    return _active_theme_tokens


class Spacing:
    """Numeric counterpart to the QSS spacing tokens for Python layouts."""

    XXS = 4
    XS = 8
    S = 12
    M = 16
    L = 24
    XL = 32
    XXL = 40
    XXXL = 48


def theme_color(name: str, alpha: int | None = None) -> QColor:
    """Return a QColor from a named color token, optionally with custom alpha."""
    hex_value = _active_theme_tokens.get(name)
    if hex_value is None or not isinstance(hex_value, str) or not hex_value.startswith("#"):
        raise KeyError(f"Unknown or non-color design token: {name!r} in active theme")
    color = QColor(hex_value)
    if alpha is not None:
        color.setAlpha(alpha)
    return color
