"""Frontend assets shared by the analyze-* GUIs."""

from pathlib import Path

WEB_DIR = Path(__file__).resolve().parent
COMMON_CSS = WEB_DIR / "common.css"
UPDATE_JS = WEB_DIR / "update.js"
SETTINGS_JS = WEB_DIR / "settings.js"
I18N_JS = WEB_DIR / "i18n.js"
BOOT_JS = WEB_DIR / "boot.js"
UI_JS = WEB_DIR / "ui.js"
