// verso site — the colour theme: as the system's (auto), light or dark. The choice is kept in the browser, one key
// for every site served from one host. Loaded in the head, before the body is drawn, so a page opens in the theme
// chosen and does not flash the other first; the button in the bar is wired once the page is read. Without a
// script the button stays hidden and the page follows the system.
(function () {
  "use strict";
  var KEY = "verso.site.theme";
  var MODES = ["auto", "light", "dark"];
  var root = document.documentElement;

  function read() {
    try { var kept = window.localStorage.getItem(KEY); } catch (e) { return "auto"; }   // a private window, blocked data
    return MODES.indexOf(kept) === -1 ? "auto" : kept;
  }
  function keep(mode) {
    try {
      if (mode === "auto") { window.localStorage.removeItem(KEY); } else { window.localStorage.setItem(KEY, mode); }
    } catch (e) { /* not kept: the choice lasts this page */ }
  }
  function apply(mode) {
    if (mode === "auto") { root.removeAttribute("data-theme"); } else { root.setAttribute("data-theme", mode); }
  }

  var mode = read();
  apply(mode);

  function wire() {
    var button = document.getElementById("page.theme");
    if (!button) { return; }
    function show() {
      button.setAttribute("data-mode", mode);
      var label = button.getAttribute("data-" + mode) || "";
      button.setAttribute("aria-label", label);
      button.title = label;
    }
    button.addEventListener("click", function () {
      mode = MODES[(MODES.indexOf(mode) + 1) % MODES.length];
      apply(mode);
      keep(mode);
      show();
    });
    // a choice made in another tab of the same host
    window.addEventListener("storage", function (event) {
      if (event.key !== KEY && event.key !== null) { return; }
      mode = read();
      apply(mode);
      show();
    });
    // a page back from the browser's cache, while the choice changed on another
    window.addEventListener("pageshow", function (event) {
      if (!event.persisted) { return; }
      mode = read();
      apply(mode);
      show();
    });
    show();
    button.hidden = false;
  }
  if (document.readyState === "loading") { document.addEventListener("DOMContentLoaded", wire); } else { wire(); }
}());
