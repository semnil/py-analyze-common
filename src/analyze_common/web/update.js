// Auto-update UI shared by the analyze-* GUIs, served at /common/update.js.
//
// Adds a settings button to the toolbar and a settings dialog holding the
// launch-check toggle, the running version and "Check now".  The setting, the
// check, the confirm and the install go through the app's /update/status,
// /update/settings, /update/check and /update/install endpoints; the app keeps
// the setting in its settings file.  The app calls window.analyzeUpdate.init()
// once, after its own scripts have set up window.i18n and the toolbar.
(function () {
  const DICT = {
    en: {
      "settings": "Settings",
      "close": "Close",
      "section": "Application version",
      "launch": "Check at launch",
      "check_now": "Check now",
      "checking": "Checking…",
      "up_to_date": "Already up to date.",
      "available": "Version {version} is available.",
      "check_failed": "Update check failed.",
      "save_failed": "The setting could not be saved.",
      "busy": "An analysis is running. Try again once it has finished.",
      "installed_only": "Available in the installed app only.",
      "confirm": "Version {version} is available. Update now?\n\nThe app restarts after the update. Results that are not saved are cleared.",
      "downloading": "Downloading update… the app will restart",
      "install_failed": "The update could not be downloaded and installed: {message}",
      "restart_failed": "The update was installed, but the app could not restart ({message}). Quit the app and open it again to use the new version.",
    },
    ja: {
      "settings": "設定",
      "close": "閉じる",
      "section": "アプリケーションのバージョン",
      "launch": "起動時に確認",
      "check_now": "今すぐ確認",
      "checking": "確認しています…",
      "up_to_date": "最新バージョンです。",
      "available": "バージョン {version} が利用可能です。",
      "check_failed": "更新の確認に失敗しました。",
      "save_failed": "設定を保存できませんでした。",
      "busy": "分析中です。終わってからもう一度お試しください。",
      "installed_only": "インストールしたアプリでのみ使えます。",
      "confirm": "バージョン {version} が利用可能です。今すぐ更新しますか?\n\n更新後にアプリを再起動します。保存していない結果は消えます。",
      "downloading": "更新をダウンロード中… 完了後にアプリを再起動します",
      "install_failed": "更新をダウンロード・インストールできませんでした: {message}",
      "restart_failed": "更新はインストールしましたが、アプリを再起動できませんでした ({message})。新しいバージョンを使うにはアプリを終了して開き直してください。",
    },
  };

  function t(key, values) {
    const lang = window.i18n && DICT[window.i18n.lang()] ? window.i18n.lang() : "en";
    let text = DICT[lang][key];
    if (values) {
      Object.keys(values).forEach(function (name) {
        text = text.split("{" + name + "}").join(String(values[name]));
      });
    }
    return text;
  }

  let hooks = null;
  let state = { current: "", supported: false, launch_check: true };
  let checking = false;
  let inflight = null;
  let scrim = null;
  let box = null;
  let settingsButton = null;
  let returnFocus = null;
  let inerted = [];

  // The "Check at launch" setting as /update/status reported it: on unless
  // stored off.
  function launchCheckOn() {
    return state.launch_check !== false;
  }

  // Saved by the app in its settings file.  A failed save puts the toggle
  // back and reports it under the version.
  async function setLaunchCheck(on) {
    state.launch_check = on;
    try {
      const res = await post("/update/settings", { launch_check: on });
      state.launch_check = res.launch_check !== false;
    } catch (e) {
      state.launch_check = !on;
      if (isOpen() && !checking) {
        const note = render();
        note.classList.add("warn");
        note.textContent = t("save_failed");
      }
    }
  }

  async function post(path, body) {
    const response = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
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

  // Cog outline: eight teeth on a 24x24 grid, drawn with currentColor.
  function gearPath() {
    const teeth = 8, outerRadius = 10, innerRadius = 7.4, step = (Math.PI * 2) / teeth;
    const tip = step * 0.17, base = step * 0.27;
    const point = function (radius, angle) {
      return (12 + radius * Math.cos(angle)).toFixed(2) + " " + (12 + radius * Math.sin(angle)).toFixed(2);
    };
    let path = "";
    for (let i = 0; i < teeth; i++) {
      const angle = i * step;
      path += (i === 0 ? "M" : "L") + point(innerRadius, angle - base) + "L" + point(outerRadius, angle - tip) +
        "L" + point(outerRadius, angle + tip) + "L" + point(innerRadius, angle + base) +
        "A" + innerRadius + " " + innerRadius + " 0 0 1 " + point(innerRadius, (i + 1) * step - base);
    }
    return path + "Z";
  }

  function gearIcon() {
    const ns = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(ns, "svg");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("width", "18");
    svg.setAttribute("height", "18");
    svg.setAttribute("fill", "none");
    svg.setAttribute("stroke", "currentColor");
    svg.setAttribute("stroke-width", "2");
    svg.setAttribute("stroke-linejoin", "round");
    svg.setAttribute("aria-hidden", "true");
    svg.setAttribute("focusable", "false");
    const cog = document.createElementNS(ns, "path");
    cog.setAttribute("d", gearPath());
    const hub = document.createElementNS(ns, "circle");
    hub.setAttribute("cx", "12");
    hub.setAttribute("cy", "12");
    hub.setAttribute("r", "3");
    svg.appendChild(cog);
    svg.appendChild(hub);
    return svg;
  }

  function makeNode(tag, className, text) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined) element.textContent = text;
    return element;
  }

  function applyButtonLabel() {
    settingsButton.setAttribute("aria-label", t("settings"));
    settingsButton.title = t("settings");
  }

  function isOpen() {
    return !!scrim && !scrim.hidden;
  }

  // The dialog's content, drawn again on every open, language switch and
  // check settle.  Returns the note node the check outcome is written into.
  function render() {
    box.textContent = "";
    const title = makeNode("h2", "settings-title", t("settings"));
    title.id = "settings-title";
    const section = makeNode("section", "settings-section");
    section.setAttribute("aria-labelledby", "settings-section-title");
    const heading = makeNode("h3", "settings-section-title", t("section"));
    heading.id = "settings-section-title";

    const launchRow = makeNode("label", "settings-row");
    const toggle = makeNode("input");
    toggle.type = "checkbox";
    toggle.id = "settings-update-launch";
    toggle.checked = launchCheckOn();
    toggle.disabled = !state.supported || checking;
    toggle.addEventListener("change", function () { void setLaunchCheck(toggle.checked); });
    launchRow.append(toggle, makeNode("span", "", t("launch")));

    const versionRow = makeNode("div", "settings-row");
    const label = makeNode("span", "settings-label");
    const version = makeNode("span", "settings-version", hooks.appName + " " + state.current);
    version.id = "settings-version";
    const note = makeNode("span", "settings-note");
    note.id = "settings-update-note";
    note.setAttribute("role", "status");
    note.setAttribute("aria-live", "polite");
    label.append(version, note);
    const checkButton = makeNode("button", "settings-btn", t("check_now"));
    checkButton.type = "button";
    checkButton.id = "settings-update-now";
    checkButton.disabled = !state.supported || checking;
    checkButton.addEventListener("click", function () { void runManualCheck(); });
    versionRow.append(label, checkButton);

    section.append(heading, launchRow, versionRow);
    if (!state.supported) section.append(makeNode("p", "settings-tag", t("installed_only")));

    const actions = makeNode("div", "settings-actions");
    const close = makeNode("button", "settings-btn settings-close", t("close"));
    close.type = "button";
    close.disabled = checking;
    close.addEventListener("click", function () { requestClose(); });
    actions.append(close);

    box.append(title, section, actions);
    return note;
  }

  function focusables() {
    return Array.prototype.filter.call(
      box.querySelectorAll("button, input"),
      function (node) { return !node.disabled; });
  }

  function open() {
    if (isOpen()) return;
    returnFocus = document.activeElement;
    render();
    inerted = Array.prototype.filter.call(document.body.children, function (node) {
      return node !== scrim && node.tagName !== "SCRIPT" && !node.inert;
    });
    inerted.forEach(function (node) { node.inert = true; });
    scrim.hidden = false;
    const close = box.querySelector(".settings-close");
    if (close) close.focus({ preventScroll: true });
  }

  function close() {
    if (!isOpen()) return;
    scrim.hidden = true;
    inerted.forEach(function (node) { node.inert = false; });
    inerted = [];
    const target = returnFocus && document.contains(returnFocus) ? returnFocus : settingsButton;
    returnFocus = null;
    if (target && target.focus) target.focus({ preventScroll: true });
  }

  // Every dismissal is refused while a manual check is in flight; the
  // outcome is written into the dialog.
  function requestClose() {
    if (!checking) close();
  }

  function onKeydown(e) {
    if (e.isComposing || e.keyCode === 229) return;
    if (e.key === "Escape") {
      // Kept from the page's own Escape handling (which cancels an analysis).
      e.preventDefault();
      e.stopPropagation();
      requestClose();
      return;
    }
    if (e.key !== "Tab") return;
    const nodes = focusables();
    if (nodes.length === 0) {
      e.preventDefault();
      return;
    }
    const first = nodes[0], last = nodes[nodes.length - 1];
    if (e.shiftKey && (document.activeElement === first || !box.contains(document.activeElement))) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && (document.activeElement === last || !box.contains(document.activeElement))) {
      e.preventDefault();
      first.focus();
    }
  }

  // The check and its confirm.  Answers once the user has answered: an
  // accepted update's download runs after this has returned.  A call made
  // while one is in flight (the launch check and "Check now") shares it, so
  // one confirm is shown.
  function checkForUpdates() {
    if (!inflight) {
      inflight = checkAndConfirm().finally(function () { inflight = null; });
    }
    return inflight;
  }

  async function checkAndConfirm() {
    let version;
    try {
      const res = await post("/update/check");
      if (!res.available) return { kind: "upToDate" };
      version = res.version;
    } catch (e) {
      return { kind: "failed" };
    }
    // Not asked while an analysis runs.
    if (hooks.isBusy()) return { kind: "busy", version: version };
    if (!window.confirm(t("confirm", { version: version }))) {
      return { kind: "declined", version: version };
    }
    close();
    settingsButton.disabled = true;
    hooks.setBusy(true);
    hooks.setStatus(t("downloading"));
    void installAccepted(version);
    return { kind: "installing", version: version };
  }

  // Download, verify and hand off.  The app exits on success; a failure
  // clears the download status and says what failed.
  async function installAccepted(version) {
    let res;
    try {
      res = await post("/update/install", { version: version });
    } catch (e) {
      settingsButton.disabled = false;
      hooks.setBusy(false);
      hooks.showError(t("install_failed", { message: e.message }));
      return;
    }
    if (res.restart_error) {
      hooks.setBusy(false);
      hooks.showError(t("restart_failed", { message: res.restart_error }));
    }
  }

  async function runManualCheck() {
    checking = true;
    let note = render();
    note.textContent = t("checking");
    let outcome;
    try {
      outcome = await checkForUpdates();
    } catch (e) {
      outcome = { kind: "failed" };
    } finally {
      checking = false;
    }
    if (!isOpen()) return;
    note = render();
    if (!box.contains(document.activeElement)) {
      const button = box.querySelector("#settings-update-now");
      if (button) button.focus({ preventScroll: true });
    }
    if (outcome.kind === "upToDate") {
      note.textContent = t("up_to_date");
    } else if (outcome.kind === "declined") {
      note.textContent = t("available", { version: outcome.version });
    } else if (outcome.kind === "failed") {
      note.classList.add("warn");
      note.textContent = t("check_failed");
    } else if (outcome.kind === "busy") {
      note.classList.add("warn");
      note.textContent = t("busy");
    }
  }

  // Ask the server what it runs and whether it can install, then run the
  // launch check when that is on.
  async function boot() {
    try {
      state = await post("/update/status");
    } catch (e) {
      state = { current: "", supported: false, launch_check: true };
    }
    if (isOpen() && !checking) render();
    if (state.supported && launchCheckOn()) await checkForUpdates();
  }

  function init(options) {
    hooks = options;
    settingsButton = makeNode("button", "settings-toggle");
    settingsButton.type = "button";
    settingsButton.id = "settings-toggle";
    settingsButton.setAttribute("aria-haspopup", "dialog");
    settingsButton.appendChild(gearIcon());
    applyButtonLabel();
    settingsButton.addEventListener("click", open);
    const toolbar = document.querySelector(".toolbar");
    if (toolbar) toolbar.appendChild(settingsButton);

    scrim = makeNode("div", "settings-scrim");
    scrim.hidden = true;
    box = makeNode("div", "settings-box");
    box.setAttribute("role", "dialog");
    box.setAttribute("aria-modal", "true");
    box.setAttribute("aria-labelledby", "settings-title");
    box.addEventListener("keydown", onKeydown);
    scrim.appendChild(box);
    // Only a press that starts on the scrim itself dismisses (a drag out of
    // the box does not).
    scrim.addEventListener("mousedown", function (e) {
      if (e.target === scrim) requestClose();
    });
    document.body.appendChild(scrim);

    if (window.i18n && window.i18n.onChange) {
      window.i18n.onChange(function () {
        applyButtonLabel();
        if (isOpen() && !checking) {
          const focusedId = document.activeElement && document.activeElement.id;
          render();
          const again = focusedId && document.getElementById(focusedId);
          (again || box.querySelector(".settings-close")).focus({ preventScroll: true });
        }
      });
    }

    api.ready = boot();
    return api.ready;
  }

  const api = {
    init: init,
    open: open,
    close: requestClose,
    checkForUpdates: checkForUpdates,
    ready: null,  // settles once the launch check (if any) has been answered
    _boot: boot,
    _t: t,
  };
  window.analyzeUpdate = api;
})();
