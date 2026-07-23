"""Render the code-native SSM app mark into Windows icon assets."""

from __future__ import annotations

from pathlib import Path

from PIL import Image
from PyQt6.QtCore import QRectF, QSize
from PyQt6.QtGui import QGuiApplication, QImage, QPainter
from PyQt6.QtSvg import QSvgRenderer


ROOT = Path(__file__).resolve().parents[1]
SVG_PATH = ROOT / "assets" / "ssm_app_icon.svg"
PNG_PATH = ROOT / "assets" / "ssm_app_icon.png"
ICO_PATH = ROOT / "assets" / "ssm_app_icon.ico"


def render_png(size: int = 1024) -> None:
    application = QGuiApplication.instance() or QGuiApplication([])
    renderer = QSvgRenderer(str(SVG_PATH))
    if not renderer.isValid():
        raise RuntimeError(f"Could not load {SVG_PATH}")

    image = QImage(QSize(size, size), QImage.Format.Format_ARGB32)
    image.fill(0)
    painter = QPainter(image)
    renderer.render(painter, QRectF(0, 0, size, size))
    painter.end()
    bits = image.bits()
    bits.setsize(image.sizeInBytes())
    rendered = Image.frombuffer(
        "RGBA",
        (size, size),
        bytes(bits),
        "raw",
        "BGRA",
        image.bytesPerLine(),
        1,
    )
    rendered.save(PNG_PATH, format="PNG")
    application.processEvents()


def build_icon() -> None:
    render_png()
    with Image.open(PNG_PATH) as source:
        source.save(
            ICO_PATH,
            format="ICO",
            sizes=[(16, 16), (20, 20), (24, 24), (32, 32), (40, 40),
                   (48, 48), (64, 64), (128, 128), (256, 256)],
        )


if __name__ == "__main__":
    build_icon()
    print(f"Created {PNG_PATH}")
    print(f"Created {ICO_PATH}")
