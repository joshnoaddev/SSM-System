# Instructions to Add Theme Switching

Please apply the following changes to `app.py`.

## 1. Add new imports

Add `set_active_theme` and `get_active_theme_tokens` to the imports from `office_app.ui`.

```python
from office_app.ui import (
    ActionButton, Card, EmptyState, Spacing, StatusBadge,
    theme_color, set_active_theme, get_active_theme_tokens,
)
```

## 2. Update `render_qss` function

This function needs to use the active theme.

```python
def render_qss(template: str) -> str:
    """Expand @token references because Qt QSS does not support variables."""
    dropdown_icon = resource_path(
        os.path.join("assets", "icons", "chevron-down.svg")
    ).replace("", "/")
    template = template.replace("@dropdown_icon", dropdown_icon)
    tokens = get_active_theme_tokens()
    # Replace longer names first so @primary does not partially consume
    # @primary_hover, @primary_pressed, and similar prefixed tokens.
    for name in sorted(tokens, key=len, reverse=True):
        value = tokens[name]
        template = template.replace(f"@{name}", value)
    return template
```

## 3. Update `CircularProgress` widget

In the `paintEvent` method of the `CircularProgress` widget, replace the direct use of `DESIGN_TOKENS` with `theme_color`.

```python
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        pen_width = max(4, int(self.width() * 0.07))
        margin = pen_width + 2
        rect = QRectF(margin, margin, self.width() - (margin * 2), self.height() - (margin * 2))
        
        # Draw background track
        pen_bg = QPen(theme_color("border_subtle"), pen_width)
        painter.setPen(pen_bg)
        painter.drawArc(rect, 0, 360 * 16)
        
        # Determine color based on completion
        if self.value == 100: color = theme_color("success")
        elif self.value >= 75: color = theme_color("primary")
        elif self.value >= 50: color = theme_color("warning")
        else: color = theme_color("danger")
        
        # Draw progress arc
        pen_fg = QPen(color, pen_width)
        pen_fg.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen_fg)
        span_angle = int((self.value / 100) * 360 * 16)
        painter.drawArc(rect, 90 * 16, -span_angle) # Start at top (90 degrees)
        
        # Draw percentage text
        painter.setPen(theme_color("text_primary"))
        font = painter.font()
        font.setPixelSize(max(8, int(self.width() * 0.19)))
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, f"{self.value}%")
```

## 4. Add `change_theme` method to `StudentApp`

Add this method to the `StudentApp` class.

```python
    def change_theme(self, theme_name: str):
        set_active_theme(theme_name)
        self.apply_modern_stylesheet()
```

## 5. Update `StudentApp.__init__`

In the `__init__` method of `StudentApp`, add the logic to set the initial theme and connect the `theme_changed` signal.

Find this block:
```python
        self.setMinimumSize(980, 680)
        
        self.apply_modern_stylesheet()
```
And replace it with this:
```python
        self.setMinimumSize(980, 680)
        
        # Set initial theme before applying stylesheet
        initial_theme = self._settings().value("theme", "Light", type=str)
        self.change_theme(initial_theme)
```

Then, find this line:
```python
        self.create_settings_screen()   # Index 7
```
And add this line after it:
```python
        self.settings_view.theme_changed.connect(self.change_theme)
```
