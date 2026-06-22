"""Single source of truth for application colors, spacing, and radii."""

from PyQt6.QtGui import QColor


DESIGN_TOKENS = {
    # Brand
    "primary": "#155EEF",
    "primary_hover": "#0B4DD8",
    "primary_pressed": "#0A3FAF",
    "primary_soft": "#EFF4FF",
    "primary_selected": "#D1E0FF",
    "secondary": "#475467",

    # Surfaces
    "app_background": "#F5F7FA",
    "surface": "#FFFFFF",
    "surface_subtle": "#F9FAFB",

    # Text
    "text_primary": "#101828",
    "text_secondary": "#475467",
    "text_disabled": "#98A2B3",

    # Borders
    "border": "#D0D5DD",
    "border_subtle": "#EAECF0",

    # Semantic — success
    "success": "#067647",
    "success_hover": "#05603A",
    "success_pressed": "#054F31",
    "success_soft": "#ECFDF3",

    # Semantic — warning
    "warning": "#B54708",
    "warning_hover": "#93370D",
    "warning_pressed": "#792E0D",
    "warning_soft": "#FFFAEB",

    # Semantic — danger
    "danger": "#B42318",
    "danger_hover": "#912018",
    "danger_pressed": "#7A271A",
    "danger_soft": "#FEF3F2",

    # Semantic — graduated (distinct purple, not a standard semantic state)
    "graduated": "#6938EF",
    "graduated_soft": "#F4F3FF",

    # Semantic — neutral (used for disabled/unknown states in progress bars, badges)
    "neutral": "#98A2B3",
    "neutral_soft": "#F2F4F7",

    # Misc
    "on_brand": "#FFFFFF",
    "shadow": "#101828",  # Same hue as text_primary; named separately for semantics
    "splash_start": "#0A3FAF",
    "splash_end": "#1570EF",

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
    hex_value = DESIGN_TOKENS.get(name)
    if hex_value is None or not isinstance(hex_value, str) or not hex_value.startswith("#"):
        raise KeyError(f"Unknown or non-color design token: {name!r}")
    color = QColor(hex_value)
    if alpha is not None:
        color.setAlpha(alpha)
    return color
