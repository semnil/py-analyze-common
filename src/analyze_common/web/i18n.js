// Two-language (en / ja) translation shared by both GUIs.  The app's i18n.js
// calls window.analyzeI18n.install(DICT) with its {en: {...}, ja: {...}}
// dictionary, which sets window.i18n.  The default language follows
// navigator.language ("ja*" -> ja, otherwise en); the user's choice is kept in
// the app's settings file, read from window.analyzeSettings.lang and saved by
// the app's main.js.
//
// Static markup uses data-i18n* attributes and is translated on
// DOMContentLoaded.  Dynamic strings call window.i18n.t(key) directly.
(function () {
  function install(DICT) {
    function systemLang() {
      const l = (navigator.language || "en").toLowerCase();
      return l.startsWith("ja") ? "ja" : "en";
    }

    const saved = (window.analyzeSettings || {}).lang;
    let current = saved === "ja" || saved === "en" ? saved : systemLang();

    function t(key, params) {
      const d = DICT[current] || DICT.en;
      let s;
      if (Object.prototype.hasOwnProperty.call(d, key)) s = d[key];
      else if (Object.prototype.hasOwnProperty.call(DICT.en, key)) s = DICT.en[key];
      else return key;
      if (params) {
        for (const k in params) {
          s = s.replace(new RegExp("\\{" + k + "\\}", "g"), params[k]);
        }
      }
      return s;
    }

    // The raw string for an explicit language (no interpolation), used to reserve
    // button widths across both languages.  Falls back to en, then the key.
    function tr(key, lang) {
      const d = DICT[lang] || DICT.en;
      if (Object.prototype.hasOwnProperty.call(d, key)) return d[key];
      if (Object.prototype.hasOwnProperty.call(DICT.en, key)) return DICT.en[key];
      return key;
    }

    function applyStatic() {
      document.documentElement.setAttribute("lang", current);
      document.querySelectorAll("[data-i18n]").forEach((n) => {
        n.textContent = t(n.getAttribute("data-i18n"));
      });
      document.querySelectorAll("[data-i18n-title]").forEach((n) => {
        n.title = t(n.getAttribute("data-i18n-title"));
      });
      document.querySelectorAll("[data-i18n-placeholder]").forEach((n) => {
        n.placeholder = t(n.getAttribute("data-i18n-placeholder"));
      });
      document.querySelectorAll("[data-i18n-aria-label]").forEach((n) => {
        n.setAttribute("aria-label", t(n.getAttribute("data-i18n-aria-label")));
      });
      const titleEl = document.querySelector("title");
      if (titleEl && titleEl.getAttribute("data-i18n")) {
        titleEl.textContent = t(titleEl.getAttribute("data-i18n"));
      }
    }

    const listeners = [];

    window.i18n = {
      t: t,
      tr: tr,
      lang: function () { return current; },
      setLang: function (lang) {
        if (lang !== "ja" && lang !== "en") return;
        current = lang;
        applyStatic();
        listeners.forEach((fn) => { try { fn(lang); } catch (_) {} });
      },
      onChange: function (fn) { listeners.push(fn); },
      applyStatic: applyStatic,
    };

    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", applyStatic);
    } else {
      applyStatic();
    }
  }

  window.analyzeI18n = { install: install };
})();
