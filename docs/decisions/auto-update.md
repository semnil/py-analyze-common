# Auto-update decisions

> 日本語版は [auto-update.ja.md](auto-update.ja.md) を参照してください。

Closed decisions about the auto-update of analyze-loudness and analyze-spectrum. How an update runs is in [`docs/auto-update.md`](../auto-update.md); this file keeps what was chosen, what was rejected and what was confirmed afterwards.

## The settings dialog keeps the focus while it waits

- **Decision** (2026-10-20, semnil/py-analyze-common#8): the focus stays inside the settings dialog across its redraws and while one of its controls is disabled. When the part that had the focus is disabled, the dialog itself takes the focus, and the browser's focus ring on the dialog stays.
- **Rejected alternatives**: catching the keys on the document while the focus stays on BODY; doing both; taking the ring off the dialog with `outline: none`.
- **Harm record**: with the focus on BODY, Escape reached the page and cancelled the running analysis. The paths are in semnil/py-analyze-common#8.

## A press outside the dialog does not move the focus

- **Decision** (2026-10-20, semnil/py-analyze-common#9): every press on the area outside the dialog has its default action prevented, so the focus does not move. A close by an outside press therefore also leaves the focus on the settings button, where closing returned it.
- **Rejected alternatives**: preventing the default action only while a check is running; catching the keys.

## Real-device checks

- **Result** (stated by the maintainer on 2026-11-12): the checks that had been left for a release after the first one that carried the updater were run by the maintainer, and no problem was found. They were: on Windows the installer (UAC, the wait on the mutex, the relaunch as the original user), the stored theme and language under `%APPDATA%`, the launch color in WebView2 and the button labels; on macOS the swap of Developer ID builds in `/Applications` and through osascript; and in the real webviews the cancel status, Escape and an outside press on the settings dialog, and the theme and language after a restart.
