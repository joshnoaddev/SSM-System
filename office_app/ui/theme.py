"""Single source of truth for application colors, spacing, and radii."""

from PyQt6.QtGui import QColor


DESIGN_TOKENS = {
    "primary": "#155EEF",
    "primary_hover": "#0B4DD8",
    "primary_pressed": "#0A3FAF",
    "primary_soft": "#EFF4FF",
    "primary_selected": "#D1E0FF",
    "secondary": "#475467",
    "app_background": "#F5F7FA",
    "surface": "#FFFFFF",
    "surface_subtle": "#F9FAFB",
    "text_primary": "#101828",
    "text_secondary": "#475467",
    "text_disabled": "#98A2B3",
    "border": "#D0D5DD",
    "border_subtle": "#EAECF0",
    "success": "#067647",
    "success_hover": "#05603A",
    "success_pressed": "#054F31",
    "success_soft": "#ECFDF3",
    "warning": "#B54708",
    "warning_hover": "#93370D",
    "warning_pressed": "#792E0D",
    "warning_soft": "#FFFAEB",
    "danger": "#B42318",
    "danger_hover": "#912018",
    "danger_pressed": "#7A271A",
    "danger_soft": "#FEF3F2",
    "graduated": "#6938EF",
    "graduated_soft": "#F4F3FF",
    "on_brand": "#FFFFFF",
    "splash_start": "#0A3FAF",
    "splash_end": "#1570EF",
    "space_xxs": "4px",
    "space_xs": "8px",
    "space_sm": "12px",
    "space_md": "16px",
    "space_lg": "24px",
    "space_xl": "32px",
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
    """Return a QColor from a named token, optionally with custom alpha."""
    color = QColor(DESIGN_TOKENS[name])
    if alpha is not None:
        color.setAlpha(alpha)
    return color
