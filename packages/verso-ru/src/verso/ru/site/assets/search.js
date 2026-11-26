// verso site — the search of one settlement: its index is fetched from this site, once, when asked.
(function () {
  "use strict";
  var form = document.getElementById("search");
  var input = document.getElementById("q");
  var status = document.getElementById("status");
  var list = document.getElementById("results");
  if (!form || !input || !status || !list) { return; }
  var limit = parseInt(status.dataset.limit, 10) || 200;
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
      var found = first.concat(rest);
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
      if (!found.length) { status.textContent = status.dataset.none; return; }
      status.textContent = status.dataset.found.replace("{count}", grouped(found.length)) +
        (found.length > limit ? " " + status.dataset.more.replace("{limit}", String(limit)) : "");
    }).catch(function () { if (mine === turn) { status.textContent = status.dataset.error; } });
  }

  var asked = new URLSearchParams(window.location.search).get("q") || "";
  input.value = asked;
  form.addEventListener("submit", function (event) {
    event.preventDefault();
    var query = input.value.trim();
    history.replaceState(null, "", query ? "?q=" + encodeURIComponent(query) : window.location.pathname);
    show(query);
  });
  if (asked) { show(asked); }
}());
