# GUI decisions

> 日本語版は [gui.ja.md](gui.ja.md) を参照してください。

Closed decisions about the GUI that analyze-loudness and analyze-spectrum share. How the GUI works today is in `AGENTS.md` ("Shared frontend scripts (web)", "Theme and language settings"); this file keeps what was chosen, why, what was rejected and what happened on the way.

## Rules both apps share live in common.css

- **Decision** (2026-10-17): a rule whose body is the same in both apps, and a variable whose value is the same in both themes, lives in `src/analyze_common/web/common.css`. Each GUI serves it as `/common/common.css` and loads it before its own `style.css`. The variable names are the ones analyze-spectrum had (`--text`, `--bg-card`, `--text-secondary`, `--text-muted`).
- **What moving a rule changes**:
  - A rule moved to `common.css` now comes before `style.css`, so it loses to a `style.css` rule of the same specificity that it used to follow. A pixel comparison of the page at rest does not show it; hover and focus do. When a rule is moved, every pair whose order is reversed is checked, and the consumers' `tests/test_frontend.py` measure the computed style under hover and focus.
  - The other direction: Dependabot's submodule update reaches a consumer's `master` before the consumer's own migration, so `master` holds the new `common.css` with the old `style.css` for a while. A rule added to `common.css` with a higher specificity than the old `style.css` rule for the same state then wins and reads a variable the old `style.css` does not define. A shared rule that overrides a state an old rule still covers lowers its specificity with `:where()`, and the new `common.css` is measured on the old consumer frontend, hover included.
  - `h1` inside `@media (max-width: 480px)` has to come after `style.css`'s `h1`, so it stays in each `style.css`.
  - A feature merged after the move had used a variable name from before it (`--fg-muted`). Old names are searched for after every rebase.
- **Harm records**: the hover color of Cancel turned into the ordinary hover's blue (semnil/analyze-spectrum#67); the focus ring of analyze-loudness's URL field disappeared (semnil/analyze-loudness#61); the hover face of Analyze became transparent on an old `style.css` (semnil/py-analyze-common#43).

## Icons of the input bar buttons are drawn by JS

- **Decision** (2026-11-04): the icons of the input bar's buttons are drawn by `_applyButtonIcons()` in `web/ui.js`, from the same `_createIcon()` SVG as the theme toggle and the warning and error marks.
- **Accepted with it**: Chromium can paint the page before the script inserts the icons, so on Windows the first frame can show these buttons without them. The decision was made with the timing measured (semnil/py-analyze-common#43).
- **Rejected alternatives**: writing the same SVG into each `index.html`; a CSS mask on a pseudo-element in `common.css`.

## Focus after a queue row moves

- **Decision** (2026-11-04, semnil/py-analyze-common#44): after a theme or language switch and after a removal, the focus stays at the same position in the queue. After a move it follows its track, and at the top or the bottom the row itself takes it.
- **Rejected alternative**: keeping the focus at the same position after a move as well. A second press would then move another track.

## The input bar wraps at 900 px

- **Decision** (2026-11-04, semnil/py-analyze-common#45): the input bar wraps at 900 CSS px wide and narrower, by a rule in `common.css`. The consumers hold no wrap rule of their own.
- **Reason**: the width one row needs follows the font. The 800 px of semnil/py-analyze-common#44 came from one font, and with wider fonts the bar stayed on one row where it did not fit. The widths are in semnil/py-analyze-common#45.
- **Rejected alternative**: grouping the buttons and letting the browser wrap them, with no width in the rule.
- **Windows**: the check of the real WebView2 window with the Windows fonts, with no control past the bar, is recorded in semnil/py-analyze-common#49 ("On Windows after the merge").

## The result area looks the same in both apps

- **Decision** (2026-11-04, semnil/py-analyze-common#46): the title row, the save buttons, the Copy button and the date and source line of the result area are shared. The directions chosen:
  - The title row follows analyze-loudness: the title on the left, the buttons on the right. A long title wraps instead of ending in an ellipsis.
  - The save buttons take the primary face, as in analyze-spectrum.
  - The error line's background is analyze-loudness's opaque color.
- **Harm records**: a variable missing from one theme, a source link at 1.82:1 in the dark theme, and a toolbar that took the first Tab are in semnil/py-analyze-common#46 and semnil/analyze-spectrum#170.

## The remaining differences between the apps (2026-11-05)

- **Decision** (2026-11-05): the differences left between the two apps were settled one by one.
  - The `!important` of uPlot's dark-theme rules is removed (single and comparison results drawn in Chromium and WebKit showed no pixel difference).
  - The default window is 1200 x 900 in both apps.
  - Pressing Analyze moves the source in the field into the queue; one row makes a single analysis and two or more a comparison. analyze-loudness took analyze-spectrum's behavior.
  - Adding, removing and a JSON entering the queue clear the shown result. Clear All also clears the result and the status. A move reorders the shown comparison.
  - analyze-spectrum's summary table takes the full width.
  - `#status` has `min-height: 20px` in `common.css`.
  - A legend label with no break in it widened the page in analyze-spectrum only (analyze-loudness's legend holds no track name), so its `style.css` has `.u-legend .u-label { overflow-wrap: anywhere; }`.
- **Superseded**: `#status` had `min-height: 40px` before, to hold the spinner with a two-line countdown without moving the layout. The 20 px above replaced it.
- **Harm record**: the full-width table was first shown with `display: table`. With long labels the table grew wider than the window (1539 px in a 1100 px window). The rows went into a `tbody` with `display: table; width: 100%`, which scrolls sideways inside the table's frame; the pixels are the same as in the proposal.

## The app name and chart titles stay in English

- **Decision**: the app name (`app.title`) and the chart titles (`chart.*`) are English literals in the `ja` dictionary as well. The names of the metrics (Duration, Track, RMS, True Peak and the others) are English in both languages, so that technical terms are not half translated. The explanations in tooltips are Japanese.

## The theme and language are kept in the settings file

- **Decision** (2026-10-20, semnil/py-analyze-common#10, semnil/analyze-spectrum#74, semnil/analyze-loudness#71): the chosen theme and language are kept in the app's settings file and reach the page through a script built for each request (`/common/settings.js`, `no-store`). The shared part in this library was made first, and the apps followed.
- **Rejected alternatives**:
  - Passing the values in the query of the window's URL: stale after a reload, and the page would hold a second copy.
  - Starting pywebview with `private_mode=False` and a fixed port, so that localStorage survives a relaunch: the webview's own storage would stay the source of truth.

## One writer for each label the page rewrites

- **Decision** (semnil/analyze-spectrum#75, semnil/analyze-loudness#73): a label the page rewrites by state (the theme button, the submit button while busy) has one writer. Its `data-i18n*` attribute is removed.
- **Rejected alternative**: writing the label again after `applyStatic()`, which would still depend on the order of the `DOMContentLoaded` handlers.
