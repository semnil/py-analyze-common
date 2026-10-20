"""Frontend assets shared by the analyze-* GUIs."""

from pathlib import Path

WEB_DIR = Path(__file__).resolve().parent
COMMON_CSS = WEB_DIR / "common.css"
UPDATE_JS = WEB_DIR / "update.js"
