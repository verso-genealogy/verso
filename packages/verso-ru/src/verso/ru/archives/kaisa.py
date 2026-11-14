"""Client for **КАИСА-Архив** reading rooms — one protocol, several archives.

AltSoft's КАИСА runs the electronic reading rooms (ЭЧЗ) of many Russian regional
archives. Two of them matter here and they speak the *same* protocol:

    ГАТО (Тамбов)     kaisa.tambovarchiv.ru
    ГАВО (Владимир)   vladimir.kaisa.ru

What differs between them is **configuration, not logic**: the object-type and
attribute ids are per-instance, and so is the viewer's file attribute. Everything
else — the search call, the obfuscated viewer URLs, the image endpoint, the auth
header — is identical, which is why it lives here instead of being written twice.

⚠ ГАВО's vlarhiv.ru catalog is a *different* system (a bespoke PHP endpoint) and is
NOT covered here. `ais.arhivpnz.ru` (Penza) is ЭЛАР, also unrelated.

Access is **paid by the hour** and activated by hand in the personal cabinet. Until
an абонемент is active, `viewer_urls()` comes back empty with `success: true` — an
absent access reads as a successful empty answer, so callers must treat "no urls" as
"not activated", not as "no scans". The hour runs while you debug: resolve the дела
and листы you want BEFORE activating.
"""

from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import time
import urllib.parse
from collections.abc import Iterable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from verso.ru.messages import t


class KaisaError(RuntimeError):
    """The archive answered, but not with what we need."""


class LocateError(KaisaError):
    """This дело's filenames do not let us map листы to pages."""


@dataclass(frozen=True)
class Instance:
    """One КАИСА deployment. Ids are per-archive and must be re-derived, not guessed.

    To find them for a new archive: open its «Отсканированные документы» search with
    a request log attached and read the `/private_api/get-object-list` body it sends.
    """

    name: str
    host: str
    object_type: int
    attr_fund: int
    attr_delo: int
    attr_code: int
    attr_title: int
    attr_opis: int | None = None
    attr_folios: int | None = None
    attr_dates: int | None = None
    # («есть электронная копия») filters, applied with searchConditionId 10
    scanned_filters: tuple[tuple[int, int], ...] = ()
    viewer_attr: int = 0
    viewer_ext: str = ".jpg"
    # Seed for get-viewer-file-data. None ⇒ read the serial from groupRecordValues
    # (ГАТО does that; ГАВО returns an empty group and takes a fixed seed).
    viewer_serial_seed: int | None = None
    # ГАТО's token file holds the raw JWT; ГАВО's localStorage value already says "Bearer ".
    add_bearer_prefix: bool = False


GATO = Instance(
    name="ГАТО", host="https://kaisa.tambovarchiv.ru",  # i18n: content — the archives' names, shelfmarks and folio marks, as the archive writes them
    object_type=2790, attr_fund=3048, attr_delo=3184, attr_code=32484162,
    attr_title=3058, attr_folios=24716073, attr_dates=3350,
    scanned_filters=((4182, 413913598), (64836275, 413913598)),
    viewer_attr=3592, viewer_ext=".pdf", viewer_serial_seed=None,
    add_bearer_prefix=True,
)

GAVO = Instance(
    name="ГАВО", host="https://vladimir.kaisa.ru",  # i18n: content — the archives' names, shelfmarks and folio marks, as the archive writes them
    object_type=4220, attr_fund=4888, attr_delo=4892, attr_code=6725842,
    attr_title=4894, attr_opis=5193365, attr_folios=4952, attr_dates=4920,
    scanned_filters=((6958, 16150),),
    viewer_attr=5908, viewer_ext=".jpg", viewer_serial_seed=2,
    add_bearer_prefix=False,
)

INSTANCES = {"gato": GATO, "gavo": GAVO}


# ---------------------------------------------------------------- folio parsing

_FOLIO = r"\d+\s*а?\s*(?:об)?"  # i18n: content — the archives' names, shelfmarks and folio marks, as the archive writes them
_BODY = re.compile(rf"^{_FOLIO}(?:\s*[-,]\s*{_FOLIO})*$", re.I)
_TOKEN = re.compile(r"(\d+)\s*(а)?\s*(об)?", re.I)  # i18n: content — the archives' names, shelfmarks and folio marks, as the archive writes them
_PARENS = re.compile(r"\(([^)]*)\)")
_LMARK = re.compile(r"Л\s*0*(\d+)\s*(об)?", re.I)  # i18n: content — the archives' names, shelfmarks and folio marks, as the archive writes them
_PAGE_BODY = re.compile(r"^\d+\s*_\s*(.+)$")
_EXT = re.compile(r"\.(?:jpg|jpeg|tif|tiff|png)$", re.I)

Folio = tuple[int, int, int]        # (лист, литера «а», оборот)
Span = tuple[Folio, Folio]          # what one scan covers, first..last


def folio_span(name: str, bare_is_folio: bool = False) -> Span | None:
    """Which листы one scan covers, from the archive's own filename — or None.

    КАИСА returns a per-scan filename (see `Client.note`), and it is written in at
    least five shapes, batch by batch. A parser that knows one of them does not fail
    on the others — it silently points at the wrong листы:

        `0094_051.jpg`              page_лист, one SIDE per scan   (one фонд)
        `0050(037об-038).tif`       page(лист), a SPREAD: verso 37 + recto 38 (another)
        `049_(043об-044).jpg`       the same, with both separators  (a дело of it)
        `002об-003.jpg`             the лист ALONE, no page prefix  (another дело)
        `ГАВО_Ф2Оп1Д5Л017.tif`     лист behind a «Л» marker        (a third)

    Shapes carrying no лист — обложка, внутренняя опись, `(ОБЛ-1)`, лист-заверитель,
    and a bare sequence number like `0028.jpg` — return None. `bare_is_folio` is set
    by `Client.locate` once it has seen that a дело names files by лист alone;
    without that evidence a prefix-less number is a scan number, not a лист.
    """
    stem = _EXT.sub("", str(name))
    par = _PARENS.search(stem)
    if par and _BODY.match(par.group(1).strip()):
        body = par.group(1).strip()
    elif not par and (lm := _LMARK.search(stem)):
        one: Folio = (int(lm.group(1)), 0, 1 if lm.group(2) else 0)
        return (one, one)
    elif (m := _PAGE_BODY.match(stem)) and _BODY.match(m.group(1).strip()):
        body = m.group(1).strip()
    elif _BODY.match(stem) and (bare_is_folio or re.search(r"об|[-,]|а$", stem, re.I)):  # i18n: content — the archives' names, shelfmarks and folio marks, as the archive writes them
        body = stem
    else:
        return None
    toks: list[Folio] = [(int(n), 1 if a else 0, 1 if o else 0)
                         for n, a, o in _TOKEN.findall(body)]
    return (toks[0], toks[-1]) if toks else None


def parse_spec(spec: str) -> list[tuple[int, int]]:
    """`"51-119"` / `"51,53,60-64"` → inclusive лист ranges."""
    out: list[tuple[int, int]] = []
    for part in spec.split(","):
        m = re.fullmatch(r"\s*(\d+)\s*(?:-\s*(\d+))?\s*", part)
        if not m:
            raise LocateError(t("archives.kaisa.bad_range", part=repr(part)))
        out.append((int(m.group(1)), int(m.group(2) or m.group(1))))
    return out


def folio_index(notes: dict[int, str]) -> dict[str, list[int]]:
    """{лист → страницы}. A лист lands on two scans when the дело is shot as spreads."""
    idx: dict[str, list[int]] = {}
    for page, name in notes.items():
        span = folio_span(name)
        if not span:
            continue
        (lo, la, _), (hi, ha, _) = span
        for n in range(lo, hi + 1):
            key = f"{n}а" if (la and n == lo) or (ha and n == hi) else str(n)  # i18n: content — the archives' names, shelfmarks and folio marks, as the archive writes them
            idx.setdefault(key, []).append(int(page))
    return {k: sorted(set(v)) for k, v in idx.items()}


def pages_for(spec: str, notes: dict[int, str], total: int) -> list[int]:
    """Pages covering листы <spec>, from a COMPLETE note map."""
    if spec == "all":
        return list(range(1, total + 1))
    want: list[int] = []
    for lo, hi in parse_spec(spec):
        for page, name in notes.items():
            span = folio_span(name)
            if span and span[0][0] <= hi and span[1][0] >= lo:
                want.append(int(page))
    return sorted(set(want))


# ---------------------------------------------------------------------- client

@dataclass
class Delo:
    """A digitized дело and the viewer URLs of its scans."""

    code: str
    object_id: int
    title: str | None
    dates: str | None
    folios: str | int | None
    urls: list[str] = field(default_factory=list)

    @property
    def total_pages(self) -> int:
        return len(self.urls)


def scan_filename(note: str | None, page: int) -> str:
    """Имя файла для скана: номер листа из ноты, но расширение — по факту.

    The archive's own filename names its TIFF master (`0188(169).tif`), while the
    viewer serves JPEG. Saving JPEG bytes under a .tif name is not cosmetic: Apple
    Photos refuses the whole batch with «unrecognisable file format», and the modal
    it raises blocks every further write to the library.
    """
    stem = re.sub(r"\.(?:jpg|jpeg|tif|tiff|png)$", "", note or "", flags=re.I)
    return f"{stem}.jpg" if stem else f"{page:04d}.jpg"


def _attr(values: dict[str, object], attr: int | None) -> str | None:
    """Read one attributeValue as text (КАИСА wraps every value in a typed record)."""
    if not attr:
        return None
    holder = values.get(str(attr))
    if not isinstance(holder, dict):
        return None
    got = holder.get("string") or holder.get("decimal")
    return None if got is None else str(got)


def obfuscate(params: str) -> str:
    """Viewer URLs are base64 over the query string XORed with 0xFF."""
    return base64.b64encode(bytes(b ^ 0xFF for b in params.encode())).decode()


def deobfuscate(url: str) -> str:
    raw = base64.b64decode(urllib.parse.unquote(str(url).strip().strip("'")))
    return bytes(b ^ 0xFF for b in raw).decode()


class Client:
    """Talks to one КАИСА instance on behalf of a logged-in reader.

    Requests go through `curl`, not urllib: python's TLS stack fails against these
    hosts (no local issuer chain), while curl uses the system trust store.
    """

    def __init__(self, instance: Instance, token: str, timeout: int = 60) -> None:
        self.inst = instance
        tok = token.strip()
        if instance.add_bearer_prefix and not tok.lower().startswith("bearer "):
            tok = f"Bearer {tok}"
        self._auth = tok
        self.timeout = timeout

    @classmethod
    def from_token_file(cls, instance: Instance, path: str = "echz_token.txt") -> Client:
        if not os.path.exists(path):
            raise KaisaError(t("archives.kaisa.no_token", path=path))
        with open(path) as fh:
            return cls(instance, fh.read())

    # -- transport ---------------------------------------------------------

    def _curl(self, args: Sequence[str]) -> str:
        return subprocess.run(["curl", "-s", "--max-time", str(self.timeout), *args],
                              capture_output=True, text=True).stdout

    def api(self, endpoint: str, body: dict[str, object], tries: int = 4) -> dict[str, object]:
        """POST to /private_api, retrying the blank 202 the server emits under load.

        That empty 202 is indistinguishable from an expired session if you give up on
        the first one — it once killed a 44-дело run at дело 30 with «token expired?»
        while the абонемент still had 40 minutes left.
        """
        out = ""
        for n in range(tries):
            out = self._curl(["-X", "POST", f"{self.inst.host}/private_api/{endpoint}",
                              "-H", "Content-Type: application/json",
                              "-H", f"Authorization: {self._auth}",
                              "-d", json.dumps(body, ensure_ascii=False)])
            try:
                return json.loads(out)
            except json.JSONDecodeError:
                time.sleep(2 * (n + 1))
        raise KaisaError(t("archives.kaisa.not_json", endpoint=endpoint, tries=tries, out=out[:200]))

    # -- catalog -----------------------------------------------------------

    def find_delo(self, fund: str | int, delo: str | int,
                  opis: str | int | None = None, scanned_only: bool = True) -> Delo | None:
        """Resolve фонд/опись/дело to its digitized object, with the viewer URLs."""
        inst = self.inst
        params: list[dict[str, object]] = [
            {"attributeId": inst.attr_fund, "searchConditionId": 12, "value": str(fund)},
            {"attributeId": inst.attr_delo, "searchConditionId": 12, "value": str(delo)}]
        params = list(params)
        if opis is not None and inst.attr_opis:
            params.append({"attributeId": inst.attr_opis, "searchConditionId": 12,
                           "value": str(opis)})
        if scanned_only:
            for attr_id, wanted in inst.scanned_filters:
                params.append({"attributeId": attr_id, "searchConditionId": 10,
                               "value": wanted})
        attrs = [a for a in (inst.attr_code, inst.attr_fund, inst.attr_opis, inst.attr_title,
                             inst.attr_folios, inst.attr_dates) if a]
        reply = self.api("get-object-list", {
            "objectTypeId": inst.object_type, "languageId": 1,
            "pageSize": 30, "pageNumber": 1, "searchParams": params, "attributes": attrs})
        code = (f"Ф. {fund} Оп. {opis} Д. {delo}" if opis is not None  # i18n: content — the archives' names, shelfmarks and folio marks, as the archive writes them
                else f"Ф. {fund}. Оп. 1. Д. {delo}.")  # i18n: content — the archives' names, shelfmarks and folio marks, as the archive writes them
        # `value` is a bare list on the public API and {params, list} on the private
        # one — both shapes occur on the same host, so normalise before iterating.
        value = reply.get("value")
        raw: object = value.get("list") if isinstance(value, dict) else value
        listed: list[object] = list(raw) if isinstance(raw, list) else []
        items: list[dict[str, object]] = [o for o in listed if isinstance(o, dict)]
        for obj in items:
            av = obj.get("attributeValues")
            av = av if isinstance(av, dict) else {}
            shown = (_attr(av, inst.attr_code) or "").strip()
            if shown != code and not str(obj.get("name") or "").startswith(code):
                continue
            found = Delo(code=code, object_id=int(str(obj["id"])),
                         title=_attr(av, inst.attr_title), dates=_attr(av, inst.attr_dates),
                         folios=_attr(av, inst.attr_folios))
            found.urls = self.viewer_urls(obj)
            return found
        return None

    def viewer_urls(self, obj: dict[str, object]) -> list[str]:
        """One obfuscated URL per scan. EMPTY means no active абонемент, not no scans."""
        serial = self.inst.viewer_serial_seed
        if serial is None:                       # ГАТО keys the file group per дело
            groups = obj.get("groupRecordValues") or {}
            if isinstance(groups, dict) and groups:
                inner = next(iter(groups.values()))
                if isinstance(inner, dict) and inner:
                    serial = int(next(iter(inner.keys())))
        reply = self.api("get-viewer-file-data", {
            "objectIds": [obj["id"]], "attributes": [self.inst.viewer_attr],
            "ext": self.inst.viewer_ext, "serialNum": serial or 1, "text": ""})
        value = reply.get("value")
        urls = value.get("urls") if isinstance(value, dict) else None
        return [str(u).strip().strip("'") for u in (urls or [])]

    # -- scans -------------------------------------------------------------

    def note(self, url: str, tries: int = 4) -> str:
        """The archive's own filename for one scan — the only source of its лист.

        Empty replies are common enough that one unretried probe derails a binary
        search: a blank note looks exactly like "no лист on this page".
        """
        for _ in range(tries):
            out = self._curl(["-G", f"{self.inst.host}/private_api/image-note",
                              "--data-urlencode", f"url={url}",
                              "-H", f"Authorization: {self._auth}"])
            try:
                value = json.loads(out).get("value")
            except json.JSONDecodeError:
                value = None
            if value:
                return str(value)
        return ""

    def notes(self, urls: Sequence[str], workers: int = 12,
              known: dict[int, str] | None = None) -> dict[int, str]:
        """Harvest every scan's filename → the дело's exact лист index. Resumable."""
        done = dict(known or {})
        todo = [p for p in range(1, len(urls) + 1) if not done.get(p)]

        def one(page: int) -> tuple[int, str]:
            return page, self.note(urls[page - 1])

        if todo:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                for page, name in pool.map(one, todo):
                    if name:
                        done[page] = name
        return done

    #: Below this a JPEG is truncated rather than merely empty. A BLANK лист — one
    #: carrying nothing but its folio number — compresses to ~8 KB, so the old 10 KB
    #: floor silently rejected real pages and reported them as download failures.
    MIN_IMAGE_BYTES = 1500

    def image(self, url: str, path: str, tries: int = 3) -> bool:
        """Save one scan, verifying it is really an image."""
        for _ in range(tries):
            self._curl(["-G", f"{self.inst.host}/site/private/imageViewer/image",
                        "--data-urlencode", f"url={url}",
                        "-H", f"Authorization: {self._auth}", "-o", path])
            # 302 (session gone) and 402 (paid quota spent) arrive as HTML written
            # under a .jpg name, so the magic bytes are the honest check — the status
            # line says 200 either way.
            try:
                if os.path.getsize(path) > self.MIN_IMAGE_BYTES:
                    with open(path, "rb") as fh:
                        if fh.read(2) == b"\xff\xd8":
                            return True
            except OSError:
                pass
            if os.path.exists(path):
                os.remove(path)
        return False

    def locate(self, spec: str, delo: Delo,
               cache: dict[int, str] | None = None) -> tuple[list[int], dict[int, str]]:
        """Pages holding листы <spec>, found by BINARY SEARCH over the notes.

        A уездное дело runs 300–2000 scans while our parish holds 10–40 листы of it,
        so harvesting every note to download 30 images is the wrong trade: folio order
        is monotonic, so ~log2(N) probes find the start and the walk stops one scan
        past the end — ~30 requests per дело instead of ~600.
        """
        notes = {} if cache is None else cache
        urls, total = delo.urls, delo.total_pages
        if not total:
            raise LocateError(t("archives.kaisa.no_pages", code=delo.code))
        mode = {"bare": False, "known": False}

        def fetch(page: int) -> str:
            if not notes.get(page):
                notes[page] = self.note(urls[page - 1])
            return notes[page]

        def detect() -> None:
            """Does this дело name files by лист alone? Then a bare `001.jpg` beside
            `002об-003.jpg` is лист 1 — but only when such neighbours exist.

            The evidence has to be an «об» or a hyphen BETWEEN NUMBERS. Accepting any
            punctuation lets the dot of `0028.jpg` pass, and then every scan number is
            read as a лист — the quietest possible way to download the wrong листы.
            """
            probes = {1, max(1, total // 4), max(1, total // 2), max(1, 3 * total // 4), total}
            def _is_bare(name: str) -> bool:
                stem = _EXT.sub("", name)
                return bool(_BODY.match(stem)) and bool(re.search(r"об|-", stem, re.I))  # i18n: content — the archives' names, shelfmarks and folio marks, as the archive writes them
            mode["bare"] = any(_is_bare(fetch(p)) for p in probes)
            mode["known"] = True

        def span(page: int) -> tuple[int, int]:
            if not mode["known"]:
                detect()
            got = folio_span(fetch(page), bare_is_folio=mode["bare"])
            if got is None:                     # обложка / опись / заверитель
                return (-1, total * 10) if page <= total // 2 else (10**9, 10**9)
            return (got[0][0], got[1][0])

        pages: list[int] = []
        for lo, hi in parse_spec(spec):
            low, high = 1, total                # first page whose span reaches лист lo
            while low < high:
                mid = (low + high) // 2
                if span(mid)[1] < lo:
                    low = mid + 1
                else:
                    high = mid
            page, hits = low, 0
            cap = 4 * (hi - lo + 1) + 20        # a sane scans-per-лист ratio
            while page <= total and span(page)[0] <= hi:
                if span(page)[1] >= lo:
                    pages.append(page)
                    hits += 1
                    if hits > cap:
                        raise LocateError(
                            t("archives.kaisa.walk_diverges", code=delo.code, lo=lo, hi=hi, hits=hits))
                page += 1
        if not pages:
            raise LocateError(t("archives.kaisa.nothing_matched", code=delo.code))
        return sorted(set(pages)), notes

    def download(self, delo: Delo, pages: Iterable[int], outdir: str,
                 names: dict[int, str] | None = None, workers: int = 6) -> tuple[int, list[int]]:
        """Fetch the given pages into `outdir`, named by лист. Skips what is there."""
        names = names or {}
        os.makedirs(outdir, exist_ok=True)
        wanted = list(pages)

        def one(page: int) -> tuple[int, bool]:
            path = os.path.join(outdir, scan_filename(names.get(page), page))
            try:
                if os.path.exists(path) and os.path.getsize(path) > self.MIN_IMAGE_BYTES:
                    return page, True
            except OSError:
                pass
            return page, self.image(delo.urls[page - 1], path)

        failed: list[int] = []
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for page, ok in pool.map(one, wanted):
                if not ok:
                    failed.append(page)
        return len(wanted) - len(failed), sorted(failed)
