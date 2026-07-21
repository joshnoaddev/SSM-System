"""Render deterministic offscreen previews of the SSM startup dialog."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QApplication

from app import StartupDialog, USERS


def render(output: Path, state: str) -> None:
    application = QApplication.instance() or QApplication(sys.argv)
    settings = QSettings("YWAMBalut", "SSMStudentProfilingSystem")
    previous_reduce_motion = settings.value("reduce_motion", False)
    settings.setValue("reduce_motion", True)
    try:
        dialog = StartupDialog()
        dialog._select_user(USERS[min(1, len(USERS) - 1)])
        dialog.show()
        application.processEvents()
        if state == "loading":
            dialog._stack.setCurrentIndex(1)
            dialog._set_loading_phase("database")
            dialog._set_loading_status("Connecting to office database")
            dialog._set_loading_progress(72, animate=False)
        application.processEvents()
        output.parent.mkdir(parents=True, exist_ok=True)
        dialog.grab().save(str(output))
        dialog.close()
    finally:
        settings.setValue("reduce_motion", previous_reduce_motion)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("state", choices=("choose", "loading"))
    args = parser.parse_args()
    render(args.output.resolve(), args.state)
