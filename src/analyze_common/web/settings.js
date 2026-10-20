// Theme and language the user picked, shared by the analyze-* GUIs and served
// at /common/settings.js.  The app's server keeps them in its settings file and
// sets window.analyzeSettingsStored ahead of this file (analyze_common.ui_settings).
//
// window.analyzeSettings.theme is "light" / "dark" / "auto" and .lang is "en" /
// "ja" / null (null: follow the OS language), as stored when the page loaded.
// save(name, value) posts {name: value} to the app's /settings endpoint and
// returns a promise of the stored values, which rejects with the server's
// error.  Saves are sent one after another, so the value picked last is the
// value stored.
(function () {
  const stored = window.analyzeSettingsStored || {};
  let queue = Promise.resolve();

  async function post(body) {
    const response = await fetch("/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    let data = {};
    try {
      data = await response.json();
    } catch (e) {
      data = {};
    }
    if (!response.ok) throw new Error(data.error || "HTTP " + response.status);
    return data;
  }

  window.analyzeSettings = {
    theme: stored.theme || "auto",
    lang: stored.lang || null,
    save: function (name, value) {
      const body = {};
      body[name] = value;
      const result = queue.then(function () { return post(body); });
      queue = result.catch(function () {});
      return result;
    },
  };
})();
