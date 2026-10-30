// UI helpers shared by both GUIs, loaded as a classic script before the app's
// main.js, which calls them as globals: SVG icons, the theme toggle's drawing,
// tooltips, button widths reserved across both languages, the drop overlay's
// text and the error line of the status area.  They read window.i18n.

// 24x24 outline icons drawn with currentColor: sun / crescent moon / half-filled circle.
var _THEME_ICON_SHAPES = {
  light: [
    ["circle", { cx: 12, cy: 12, r: 4 }],
    ["path", { d: "M12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" }],
  ],
  dark: [
    ["path", { d: "M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z" }],
  ],
  auto: [
    ["circle", { cx: 12, cy: 12, r: 8 }],
    ["path", { d: "M12 4a8 8 0 0 1 0 16z", fill: "currentColor" }],
  ],
};

// Warning triangle for status messages, same drawing conventions as the theme icons.
var _WARNING_ICON_SHAPES = [
  ["path", { d: "M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z" }],
  ["path", { d: "M12 9v4M12 17h.01" }],
];

function _createThemeIcon(mode) {
  return _createIcon(_THEME_ICON_SHAPES[mode], 18);
}

function _createIcon(shapes, size) {
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("width", String(size));
  svg.setAttribute("height", String(size));
  svg.setAttribute("fill", "none");
  svg.setAttribute("stroke", "currentColor");
  svg.setAttribute("stroke-width", "2");
  svg.setAttribute("stroke-linecap", "round");
  svg.setAttribute("stroke-linejoin", "round");
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("focusable", "false");
  for (const [tag, attrs] of shapes) {
    const el = document.createElementNS(ns, tag);
    for (const k of Object.keys(attrs)) el.setAttribute(k, attrs[k]);
    svg.appendChild(el);
  }
  return svg;
}

function _systemDark() {
  return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
}

// Applies the theme mode ("light" | "dark" | "auto") to <html> and redraws the
// #theme-toggle button (icon, title, aria-label) when the page has one.
function _applyThemeMode(mode) {
  const resolved = mode === "auto" ? (_systemDark() ? "dark" : "light") : mode;
  document.documentElement.setAttribute("data-theme", resolved);
  const btn = document.getElementById("theme-toggle");
  if (!btn) return;
  btn.textContent = "";
  btn.appendChild(_createThemeIcon(mode));
  btn.title = window.i18n.t("theme.title." + mode);
  btn.setAttribute("aria-label", window.i18n.t("theme.aria_state." + mode));
}

function _applyDropText() {
  document.body.setAttribute("data-drop-text", window.i18n.t("drop.overlay"));
}

// Reserve each variable-label button's width for the widest label it can show,
// across both languages, so a language switch or a state change never resizes
// the button and shifts the row.  Measured in place, so the button's own font
// and padding apply.
function _reserveButtonWidth(btn, keys, textSel) {
  if (!btn || !window.i18n || !window.i18n.tr) return;
  const target = textSel ? btn.querySelector(textSel) : btn;
  if (!target) return;
  const savedText = target.textContent;
  const savedFlex = btn.style.flex;
  btn.style.flex = "none";
  btn.style.width = "auto";
  btn.style.minWidth = "0";
  let max = 0;
  for (const lang of ["en", "ja"]) {
    for (const key of keys) {
      target.textContent = window.i18n.tr(key, lang);
      const w = btn.getBoundingClientRect().width;
      if (w > max) max = w;
    }
  }
  target.textContent = savedText;
  btn.style.flex = savedFlex;
  // Pin both the floor and the flex-basis: at a narrow viewport the input bar
  // switches to flex:1 1 auto, where a bare min-width still lets the width
  // follow the current label through the auto basis.
  btn.style.minWidth = max + "px";
  btn.style.width = max + "px";
}

// The widest label of a button class that is created later (an off-screen
// probe of that class), across both languages.
function _classButtonWidth(className, keys) {
  if (!window.i18n || !window.i18n.tr) return 0;
  const btn = document.createElement("button");
  btn.className = className;
  btn.style.position = "absolute";
  btn.style.left = "-9999px";
  btn.style.visibility = "hidden";
  document.body.appendChild(btn);
  let max = 0;
  for (const lang of ["en", "ja"]) {
    for (const key of keys) {
      btn.textContent = window.i18n.tr(key, lang);
      const w = btn.getBoundingClientRect().width;
      if (w > max) max = w;
    }
  }
  document.body.removeChild(btn);
  return max;
}

// Tooltips: one .tip-popup at a time, shown 200 ms after hover or focus,
// linked to its anchor with aria-describedby.
var _tipEl = null;
var _tipTimer = null;
var _tipAnchor = null;
var _tipSeq = 0;

function _showTip(anchor, text) {
  _hideTip();
  _tipAnchor = anchor;
  _tipTimer = setTimeout(() => {
    _tipEl = document.createElement("div");
    _tipEl.className = "tip-popup";
    _tipEl.setAttribute("role", "tooltip");
    _tipEl.id = anchor.getAttribute("aria-describedby") || ("tip-" + (++_tipSeq));
    anchor.setAttribute("aria-describedby", _tipEl.id);
    _tipEl.textContent = text;
    document.body.appendChild(_tipEl);
    var r = anchor.getBoundingClientRect();
    var tw = 300, th = _tipEl.offsetHeight;
    var left = r.left + r.width / 2 - tw / 2;
    var top = r.bottom + 6;
    if (left < 4) left = 4;
    if (left + tw > window.innerWidth - 4) left = window.innerWidth - tw - 4;
    if (top + th > window.innerHeight - 4) top = r.top - th - 6;
    _tipEl.style.left = left + "px";
    _tipEl.style.top = top + "px";
  }, 200);
}

function _hideTip() {
  clearTimeout(_tipTimer);
  if (_tipAnchor) _tipAnchor.removeAttribute("aria-describedby");
  _tipAnchor = null;
  if (_tipEl) { _tipEl.remove(); _tipEl = null; }
}

function _addTip(cell, textOrFn) {
  cell.className = (cell.className ? cell.className + " " : "") + "has-tip";
  cell.tabIndex = 0;
  var resolve = typeof textOrFn === "function" ? textOrFn : () => textOrFn;
  cell.addEventListener("mouseenter", () => _showTip(cell, resolve()));
  cell.addEventListener("mouseleave", _hideTip);
  cell.addEventListener("focus", () => _showTip(cell, resolve()));
  cell.addEventListener("blur", _hideTip);
}

// Writes an error into the status element: role="alert", a warning icon, the
// message after err.prefix, and a Copy button (reserved at copyBtnWidth) when
// the clipboard is available.
function _renderError(statusEl, message, copyBtnWidth) {
  statusEl.setAttribute("role", "alert");
  statusEl.setAttribute("aria-live", "assertive");
  statusEl.classList.remove("loading");
  statusEl.classList.add("error");
  statusEl.textContent = "";
  const icon = document.createElement("span");
  icon.className = "error-icon";
  icon.setAttribute("aria-hidden", "true");
  icon.appendChild(_createIcon(_WARNING_ICON_SHAPES, 16));
  statusEl.appendChild(icon);
  const text = document.createElement("span");
  text.className = "error-text";
  text.textContent = window.i18n.t("err.prefix") + message;
  statusEl.appendChild(text);
  if (navigator.clipboard) {
    const btn = document.createElement("button");
    btn.className = "copy-btn";
    btn.textContent = window.i18n.t("btn.copy");
    btn.style.minWidth = copyBtnWidth + "px";
    btn.addEventListener("click", () => {
      navigator.clipboard.writeText(message).then(() => {
        btn.textContent = window.i18n.t("btn.copied");
        setTimeout(() => { btn.textContent = window.i18n.t("btn.copy"); }, 1500);
      }).catch(() => {
        btn.textContent = window.i18n.t("btn.copy_failed");
        setTimeout(() => { btn.textContent = window.i18n.t("btn.copy"); }, 1500);
      });
    });
    statusEl.appendChild(btn);
  }
}
