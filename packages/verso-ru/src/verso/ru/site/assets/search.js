// verso site — the search of one settlement: its index is fetched from this site, once, when asked.
(function () {
  "use strict";
  var form = document.getElementById("search");
  var input = document.getElementById("q");
  var status = document.getElementById("status");
  var list = document.getElementById("results");
  if (!form || !input || !status || !list) { return; }
  var limit = parseInt(status.dataset.limit, 10) || 200;
  // What narrows a search: the page draws only those the site has a use for (more than one year, source, parish;
  // a record not yet read against its scan), hidden until wired here.
  var filters = document.getElementById("filters");
  var NARROW = ["from", "to", "source", "village", "reviewed"];
  var controls = {};
  NARROW.forEach(function (name) { controls[name] = document.getElementById(name); });
  var index = null;
  var turn = 0;    // the query on the page: an answer to an earlier one is dropped

  // As verso.ru.site.model.fold: the letters the 1918 reform dropped, the hard sign at a word's end.
  var OLD = { "ё": "е", "ѣ": "е", "і": "и", "ѳ": "ф", "ѵ": "и" }; // i18n: content
  function fold(text) {
    return text.normalize("NFC").toLowerCase()
      .replace(/[ёѣіѳѵ]/g, function (c) { return OLD[c]; }) // i18n: content
      .replace(/ъ(?![\p{L}\p{N}_])/gu, ""); // i18n: content
  }

  // As verso.ru.site.pages.grouped: from five figures on, the thousands set apart («31 245»).
  function grouped(count) {
    var text = String(count);
    if (count < 10000) { return text; }
    return text.replace(/\B(?=(\d{3})+$)/g, status.dataset.group || " ");
  }

  function bound(control) {    // a whole year, as the field holds it («1e3» is 1000); anything else bounds nothing
    var value = control && control.value !== "" ? Number(control.value) : NaN;
    return Number.isInteger(value) ? value : null;
  }

  // What the filters ask, as set now: years from and to (either way round), a source, a parish, read records only.
  function asked() {
    var low = bound(controls.from), high = bound(controls.to);
    if (low !== null && high !== null && low > high) { var swap = low; low = high; high = swap; }
    return {
      low: low, high: high,
      source: controls.source ? controls.source.value : "",
      village: controls.village ? controls.village.value : "",
      reviewed: controls.reviewed ? controls.reviewed.checked : false
    };
  }

  // A book is [path, title, year, source, parish]: a bound of years leaves out a book without one.
  function kept(want, book, row) {
    if (want.low !== null || want.high !== null) {
      if (typeof book[2] !== "number") { return false; }
      if (want.low !== null && book[2] < want.low) { return false; }
      if (want.high !== null && book[2] > want.high) { return false; }
    }
    if (want.source && book[3] !== want.source) { return false; }
    if (want.village && book[4] !== want.village) { return false; }
    return !(want.reviewed && row[6]);
  }

  function load() {
    if (index) { return Promise.resolve(index); }
    status.textContent = status.dataset.loading;
    return fetch("index.json").then(function (answer) {
      if (!answer.ok) { throw new Error(String(answer.status)); }
      return answer.json();
    }).then(function (data) { index = data; return data; });
  }

  function show(query) {
    var words = fold(query).split(/\s+/).filter(Boolean);
    var mine = ++turn;
    list.textContent = "";
    if (!words.length) { status.textContent = ""; return; }
    load().then(function (data) {
      if (mine !== turn) { return; }
      list.textContent = "";
      // A word that begins a name before one found inside another («Справкин» before «Насправкин»).
      var first = [], rest = [];
      data.rows.forEach(function (row) {
        if (!words.every(function (word) { return row[0].indexOf(word) !== -1; })) { return; }
        var begins = words.every(function (word) { return (" " + row[0]).indexOf(" " + word) !== -1; });
        (begins ? first : rest).push(row);
      });
      var matched = first.concat(rest);
      var want = asked();
      var found = matched.filter(function (row) { return kept(want, data.books[row[3]], row); });
      var parts = document.createDocumentFragment();
      found.slice(0, limit).forEach(function (row) {
        var book = data.books[row[3]];
        var item = document.createElement("li");
        var link = document.createElement("a");
        link.href = "../" + book[0] + "#" + encodeURIComponent(row[4]).replace(/%7E/g, "~");
        link.textContent = row[1];
        item.appendChild(link);
        if (row[2]) {
          var modern = document.createElement("span");
          modern.className = "modern d";
          modern.textContent = row[2];
          item.appendChild(document.createTextNode(" "));
          item.appendChild(modern);
        }
        if (row[6]) {
          var unread = document.createElement("span");
          unread.className = "badge";
          unread.textContent = status.dataset.unread;
          item.appendChild(document.createTextNode(" "));
          item.appendChild(unread);
        }
        item.appendChild(document.createTextNode(" — " + row[5] + ", " + book[1]));
        parts.appendChild(item);
      });
      list.appendChild(parts);
      var total = grouped(matched.length);
      if (!found.length) {
        status.textContent = matched.length ? status.dataset.noneOf.replace("{total}", total) : status.dataset.none;
        return;
      }
      status.textContent = (found.length < matched.length
        ? status.dataset.foundOf.replace("{count}", grouped(found.length)).replace("{total}", total)
        : status.dataset.found.replace("{count}", grouped(found.length))) +
        (found.length > limit ? " " + status.dataset.more.replace("{limit}", String(limit)) : "");
    }).catch(function () { if (mine === turn) { status.textContent = status.dataset.error; } });
  }

  // The address keeps the query and the filters set, so a search is a link to send.
  function address(query) {
    var params = new URLSearchParams();
    if (query) { params.set("q", query); }
    NARROW.forEach(function (name) {
      var control = controls[name];
      if (!control) { return; }
      if (control.type === "checkbox") {
        if (control.checked) { params.set(name, "1"); }
      } else if (control.value.trim()) {
        params.set(name, control.value.trim());
      }
    });
    var text = params.toString();
    return text ? "?" + text : window.location.pathname;
  }

  function run() {
    var query = input.value.trim();
    history.replaceState(null, "", address(query));
    show(query);
  }

  var given = new URLSearchParams(window.location.search);
  input.value = given.get("q") || "";
  NARROW.forEach(function (name) {
    var control = controls[name];
    var value = given.get(name);
    if (!control || value === null) { return; }
    if (control.type === "checkbox") { control.checked = value === "1"; } else { control.value = value; }
    if (control.selectedIndex === -1) { control.selectedIndex = 0; }    // a choice the page does not offer: any
  });
  form.addEventListener("submit", function (event) {
    event.preventDefault();
    run();
  });
  if (filters) {
    filters.addEventListener("change", run);
    filters.hidden = false;
  }
  if (input.value.trim()) { show(input.value.trim()); }
}());
