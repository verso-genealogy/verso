"""Where a record stands on the site: rule `r1` turned into a path and an anchor.

    r1:<village>/<fund>-<inventory>-<case>[;<part>][/<year>]/<kind>/<token>
        → books/<village>/<fund>-<inventory>-<case>[_<part>]/[<year>/]<kind>/#<token>
    r1:<village>/card/<kind>/<key>
        → cards/<village>/<kind>/#<key>

A book's page is the book its records are cited from — the id less its token — so a record that
states a shelfmark of its own stands on that book's page. The segments of a path are Latin: the
village and the letters of a shelfmark by the workspace's transliteration of addresses, whose
profile is frozen, so an address moves only when the id does. Two books of one path are the model's
to refuse (`verso.ru.site.model.DuplicatePath`), never told apart by a counter.
"""
from __future__ import annotations

import re
from urllib.parse import quote

from verso.core import plugins
from verso.core.records import ids
from verso.ru.messages import t

BOOKS = "books"
CARDS = "cards"
CARD = "card"            # a card's "shelfmark" in its id (verso.ru.records.cite.CARD)
UNKNOWN = "unknown"      # a shelfmark of question marks alone


def slug(text: str) -> str:
    """`text` as one Latin segment of a path; refuses a text no letter or digit of which survives."""
    latin = plugins.transliterator()(text).lower().replace("'", "")
    out = re.sub(r"[^a-z0-9]+", "-", latin).strip("-")
    if not out:
        raise ValueError(str(t("site.urls.no_slug", text=text)))
    return out


def _shelf(text: str) -> str:
    try:
        return slug(text)
    except ValueError:
        return UNKNOWN


def book_of(record_id: str) -> str:
    """The book a record is cited from: its id less the token."""
    return record_id.rsplit("/", 1)[0]


def book_path(book_id: str) -> str:
    """The directory of a book's page, with its final slash."""
    parsed = ids.parse(book_id)
    if parsed.shelfmark == CARD:
        return f"{CARDS}/{slug(parsed.village)}/{slug(parsed.kind)}/"
    shelf = _shelf(parsed.shelfmark) + (f"_{_shelf(parsed.part)}" if parsed.part else "")
    year = [] if parsed.year is None else [str(parsed.year)]
    return "/".join([BOOKS, slug(parsed.village), shelf, *year, slug(parsed.kind)]) + "/"


def anchor(record_id: str) -> str:
    """A record's anchor on its book's page: its token as the id spells it, spaces closed."""
    return re.sub(r"\s", "_", record_id.rsplit("/", 1)[1])


def fragment(anchor_: str) -> str:
    """An anchor as the fragment of a link."""
    return quote(anchor_, safe="~")


def record_href(record_id: str) -> str:
    """A record's address from the site's root."""
    return f"{book_path(book_of(record_id))}#{fragment(anchor(record_id))}"
