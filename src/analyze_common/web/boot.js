// Loaded in <head> after the settings and the app's i18n.js, before the CSS:
// resolves the theme and the language on <html> before the first paint, so the
// page does not flash the other theme and screen readers do not announce the
// wrong language.
(function() {
  var s = (window.analyzeSettings || {}).theme;
  var mode = (s === "light" || s === "dark") ? s : "auto";
  var resolved = mode === "auto"
    ? (window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light")
    : mode;
  document.documentElement.setAttribute("data-theme", resolved);
  document.documentElement.setAttribute("lang", window.i18n.lang());
})();
