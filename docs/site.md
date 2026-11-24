# A village's site

**English** · [Русский](site.ru.md)

`verso site` writes a village's records as a static site: every book as the document it was read
from, record by record, with an index of the names and a search. Plain files — HTML, one
stylesheet, one script for the search — that any host of static pages serves and a browser opens
from disk (`verso.ru.site`).

```sh
verso site --village V --out _site
    [--records DIR] [--docs DIR] [--title T] [--summary S]
    [--repo-url U] [--site-url U] [--revision R]
    [--license NAME --license-url U] [--strict]
```

`--out` is a new or an empty directory. Exit 0; 1 with `--strict` when a DSL file did not import
or the built site holds a dead link; 2 for a refusal — a directory that holds something, two books
of one address, prose that links nowhere.

## What is drawn

The records are built as `verso export-records` builds them — or read from an export, `--records`
— and drawn by the interface's schema, `ui-v1.json`: a kind's dates, its people in the order of
the book's columns, the members of a household as a table, a card of an external catalog with the
link to it. So the site shows what the [records JSON](records-json.md) holds, and a field the
vocabulary gains reaches the page by itself.

- **What the record writes is the text; what the library derived stands beside it, marked.** A
  name is shown in the spelling of the source; a modern form, a surname a child takes from the
  father, an estate carried from a parent are set in another face. A value the book's defaults
  give every entry — the parish as the place, «крестьянин» — is said once, at the head of the book.
- **An unread record is shown and marked.** A record that is `reviewed=False` carries a mark, and
  its book and the front page count them ([the review ratchet](review-ratchet.md)).
- **A book of the civil registry says so**: its second date is a registration.
- **Not drawn**: the `#` comments of the DSL (`note`), a path to a scan (`scan_file`), the labels
  of a target, and nothing of Terraform or of a tree — the site reads records, not what was made
  of them. It folds nobody into a person either: the index of names lists mentions, a persona of
  one record each.

## The pages and their addresses

| Page | Address |
|---|---|
| the front page | `/` |
| the books by archive, fund and file | `books/` |
| a book and its records | `books/<village>/<fund>-<inventory>-<case>[_<part>]/[<year>/]<kind>/` |
| the cards of an external catalog | `cards/<village>/<kind>/` |
| the years, and the books of one | `years/`, `years/<year>/` |
| the surnames, and the mentions of one | `names/`, `names/<surname>/` |
| those written with no surname, by patronymic | `patronymics/`, `patronymics/<patronymic>/` |
| the search and its index | `search/`, `search/index.json` |
| the settlement's prose | `about/`, `<page>/` |

A record's address is rule `r1` of its id: the page of the book it is cited from — the id less its
token — and the token as the anchor (`…/1900/birth/#f4`, `#m12~2`, `#m_1`). A record that states a
shelfmark of its own stands on that book's page. The segments of a book's path are Latin, by the
workspace's transliteration of addresses (`[translit] address`), whose profile is frozen; a page of
names is named by the name itself. So an address moves when the id does — a corrected number, sex
or shelfmark — and never with a rebuild: the same records make the same bytes. Two books whose ids
make one path are refused, naming both.

Every link is relative, so the site opens the same from a project's path on a host, from a domain
of its own and from a directory. `--site-url` adds what needs the address: `sitemap.xml`, the
canonical links, and the links of `404.html`. Nothing is fetched from another host: no font, no
script, no counter.

## Finding a person

Without JavaScript: the index of surnames, a page for each with every mention of it in the order
of the years; a feminine form stands with its masculine one where the corpus has both. Those the
source writes with no surname are found by the patronymic in the book's form, and those written by
a name alone have a page of their own.

With it: the search reads `search/index.json` once and looks for every word of the query in the
modern and the written forms, folded — lower case, the letters the 1918 reform dropped as their
modern ones, no hard sign at a word's end — so «Феодор» finds «Ѳеодоръ».

## The settlement's prose

`<village>/docs/*.md` (`--docs`) become pages: `README.md` is the contents (`about/`), every other
file a page under its own name, in the order the contents links them. A link to another page of
the prose leads to that page; a link to a DSL file leads to its book on the site; any other link
into the workspace leads to the repository (`--repo-url`), and is refused where none is named. A
link out of the workspace, a link to nothing and an image are refused; raw HTML in the text is
shown as text. The front page's paragraph about the settlement is `--summary`, else the first
paragraph of `history.md`.

A heading's id is GitHub's — its text in lower case, everything but letters, digits, `_`, `-` and spaces
dropped, each space a hyphen, a heading met again numbered (`-1`) — so a link to a section
(`places.md#храмы`) reads the same in the repository and on the site; a link to a section the page
lacks fails a `--strict` build. A page may not take a name the site keeps for itself: `assets`,
`books`, `cards`, `years`, `names`, `patronymics`, `search`, `about` (`verso.ru.site.RESERVED`).

Markdown is read by markdown-it-py (CommonMark and tables), the extra `verso-ru[site]`; a village
without prose needs none.

## On GitHub Pages

A repository of a village's DSL builds its site on every push and deploys it from the default
branch; a pull request gets the same build as an artifact.

```yaml
jobs:
  site:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: actions/setup-python@v7
        with:
          python-version: '3.14'
      - run: pip install 'verso-ru[site]'
      - run: verso site --village Горюхино --out _site --strict
      - uses: actions/upload-pages-artifact@v5.0.0
        with:
          path: _site
  deploy:
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'
    needs: site
    runs-on: ubuntu-latest
    permissions:
      pages: write
      id-token: write
    environment:
      name: github-pages
    steps:
      - uses: actions/deploy-pages@v5.0.1
```

The repository's Pages are set to build from GitHub Actions (Settings → Pages → Source) before
the first push: the workflow's token cannot switch them on.

## In Python

```python
from verso.ru.site import build

built = build(files, out=out, village="Горюхино", site_url="https://example.org/gorjuhino/")
built.pages, built.bytes, built.unreviewed     # what was written
built.problems                                 # dead links and anchors, an id met twice: empty when sound
```

`files` are records-v1 file nodes of one village, in any order. `verso.ru.site.check.verify(out)`
judges any built directory the same way.
