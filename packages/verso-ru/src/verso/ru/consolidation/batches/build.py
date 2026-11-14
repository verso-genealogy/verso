"""Split terraform plan 'update' actions into category-grouped review batches.

Clean format: summary table at top, per-resource diff sections below
(no HTML-inside-table-cell, which broke under stricter markdown checkers).
"""
import re
import shutil
from collections import defaultdict
from collections.abc import Callable
from typing import Any
from verso.ru.consolidation.plan import plan_paths

_paths = plan_paths()
ROOT = _paths.village_dir
BATCHES_DIR = ROOT / "batches"
BATCH_SIZE = 50

plan = _paths.load_json()
updates = [c for c in plan["resource_changes"] if c.get("change",{}).get("actions") == ["update"]]

text = _paths.load_text()
DIFF_RE = re.compile(
    r"^  # (geni_(?:profile|document|union)\.[\w-]+) will be (?:updated in-place|created|destroyed)\n"
    r"(.*?)^    \}\n",
    re.DOTALL | re.MULTILINE,
)
diff_by_addr = {}
for m in DIFF_RE.finditer(text):
    addr = m.group(1)
    diff_by_addr[addr] = "  # " + addr + " will be updated in-place\n" + m.group(2) + "    }"

def _only_about_diff(b, a):
    """True iff the only field that differs between before/after is `about`.

    Event fields (birth/death/baptism/burial/marriage) carry a server-
    recomputed `name` like "Birth of X" -> "(known after apply)" whenever
    anything on the profile changes, so a sub-diff where the only
    differing key is `name` is treated as unchanged. Any other sub-key
    difference (date, location, description) counts as a real change."""
    keys = set(b.keys()) | set(a.keys())
    EVENTS = {"birth", "death", "baptism", "burial", "marriage"}
    for k in keys:
        if k == "about":
            continue
        bv, av = b.get(k), a.get(k)
        if bv == av:
            continue
        if k in EVENTS and isinstance(bv, dict) and isinstance(av, dict):
            # Treat as unchanged iff every differing sub-key is `name`
            sub_keys = set(bv.keys()) | set(av.keys())
            for sk in sub_keys:
                if sk == "name":
                    continue
                if bv.get(sk) != av.get(sk):
                    return False
            continue
        return False
    return True


_NASELENNY_RE = re.compile(r"; Населенный пункт [^;\n]+?не указан")

# Residence-supplement note reformatting: legacy renders the
# 'Населенный пункт … не указан в МК, но <rationale>' note as a separate
# '>'-line plus a '; Населенный пункт … не указан' list-item inside Имена в
# МК; the new translator inlines both into '<name> - <annotation>'.
# Variants seen in the corpus:
#   • "все крестьяне этого помещика из <Village>"
#   • "обычно ясачные крестьяне в этом приходе"
#   • "сословие и населенный пункт не указаны"
# The strip below removes all 3 forms (legacy standalone line, legacy
# list-item, new inline suffix) so the remaining text compares cleanly.
_NASE_LEGACY_LIST_ITEM_RE = re.compile(
    # The "взято/взят/восстановлены/восстановлено" closing variants all
    # describe the same "not specified, recovered from another record"
    # caveat — accept all of them. "взят" (without -о) appears in the
    # corpus too (masculine short form).
    r"; (?:Населенный пункт|Сословие)[^;\n]+?не указан[а-я]*(?:, (?:взято|взят|восстановлены|восстановлено) из другой записи)?",
)
_NASE_LEGACY_LINE_RE = re.compile(
    r"^\s*>[^\n]*[Нн]аселенный пункт[^\n]*в МК, но[^\n]*\n?",
    re.MULTILINE,
)
_NASE_NEW_INLINE_RE = re.compile(
    # Stop at the next ';' so trailing names in the same `Имена в МК` list
    # aren't gobbled by the greedy trailing match.
    r" - [^;\n]*?(?:населённый пункт|сословие)[^;\n]*",
)


def _strip_residence_supp(text):
    """Remove all variants of the residence-supplement annotation (legacy
    list-item, legacy standalone line, new inline form) so before/after
    texts can be compared for the rest of their content."""
    text = _NASE_NEW_INLINE_RE.sub("", text)
    text = _NASE_LEGACY_LINE_RE.sub("", text)
    text = _NASE_LEGACY_LIST_ITEM_RE.sub("", text)
    return text.rstrip()


def _about_residence_supp_only(b, a):
    """True iff the only about-text diff is residence-supplement reformat
    (legacy multi-line residence note + list-item → new compact inline
    suffix). Covers Sobakevichevo, other villages, and the 'обычно ясачные
    крестьяне в этом приходе' variant."""
    if not _only_about_diff(b, a):
        return False
    b_about = (b.get("about") or {})
    a_about = (a.get("about") or {})
    if b_about == a_about:
        return False
    if set(b_about.keys()) != set(a_about.keys()):
        return False
    has_diff = False
    for loc, b_text in b_about.items():
        a_text = a_about.get(loc, "")
        if b_text == a_text:
            continue
        has_diff = True
        if _strip_residence_supp(b_text) != _strip_residence_supp(a_text):
            return False
    return has_diff


def _normalize_naselenny(text):
    """Convert legacy ';Населенный пункт <qualifier> не указан' standalone-item
    format to the new translator's ' - населённый пункт не указан' merged
    suffix (attached to the preceding godparent name).

    Catches the diff pattern:
      before: 'Федосья Иванова; Населенный пункт восприемника не указан'
      after : 'Федосья Иванова - населённый пункт не указан'
    """
    return _NASELENNY_RE.sub(" - населённый пункт не указан", text)


def _about_naselenny_only(b, a):
    """True iff every locale's about diff is solely the naselенный→населённый
    reformat (godparent-residence-unknown note relocation). Same semantic
    content, just the new translator's compacter rendering.

    Order-insensitive across section reorder: normalize the BEFORE text
    (legacy semicolon-item form) into the new inline form, then compare."""
    return _about_only_after_normalize(b, a, _normalize_naselenny, lambda t: t)


def _about_imena_added_only(b, a):
    """True iff the only about-text diff is appending trailing names to one
    or more 'Имена в МК: …' lines (the new translator now includes relatives
    or other participants the legacy left out). Each new line is the old
    line plus one or more '; X' items at the end."""
    if not _only_about_diff(b, a):
        return False
    b_about = (b.get("about") or {})
    a_about = (a.get("about") or {})
    if b_about == a_about:
        return False
    if set(b_about.keys()) != set(a_about.keys()):
        return False
    has_diff = False
    for loc, b_text in b_about.items():
        a_text = a_about.get(loc, "")
        if b_text == a_text:
            continue
        has_diff = True
        b_lines = b_text.splitlines()
        a_lines = a_text.splitlines()
        if len(b_lines) != len(a_lines):
            return False
        for bl, al in zip(b_lines, a_lines, strict=True):
            if bl == al:
                continue
            if not (bl.lstrip().startswith(">Имена в МК")
                    and al.lstrip().startswith(">Имена в МК")):
                return False
            b_items = bl.split(":", 1)[1].strip().split("; ")
            a_items = al.split(":", 1)[1].strip().split("; ")
            if len(a_items) <= len(b_items):
                return False
            if a_items[:len(b_items)] != b_items:
                return False
    return has_diff


def _about_orthography_only(b, a):
    """True iff the only about-text diff is pre-revolutionary orthography
    restoration on names in Имена в МК lines:
      • trailing 'ъ' appended to one or more words (Иван → Иванъ)
      • Latin I/i replaced with Cyrillic І/і
      • ѣ replaced with е
    Each changed line must be solely an orthography variation."""
    if not _only_about_diff(b, a):
        return False
    b_about = (b.get("about") or {})
    a_about = (a.get("about") or {})
    if b_about == a_about:
        return False
    if set(b_about.keys()) != set(a_about.keys()):
        return False
    has_diff = False

    def _normalize(s: str) -> str:
        s = re.sub(r"ъ(?=\s|$)", "", s)
        s = s.replace("І", "И").replace("і", "и").replace("ѣ", "е")
        return s

    for loc, b_text in b_about.items():
        a_text = a_about.get(loc, "")
        if b_text == a_text:
            continue
        has_diff = True
        b_lines = b_text.splitlines()
        a_lines = a_text.splitlines()
        if len(b_lines) != len(a_lines):
            return False
        for bl, al in zip(b_lines, a_lines, strict=True):
            if bl == al:
                continue
            if not (bl.lstrip().startswith(">Имена в МК")
                    and al.lstrip().startswith(">Имена в МК")):
                return False
            b_items = bl.split(":", 1)[1].strip().split("; ")
            a_items = al.split(":", 1)[1].strip().split("; ")
            if len(b_items) != len(a_items):
                return False
            for bi, ai in zip(b_items, a_items, strict=True):
                if bi == ai:
                    continue
                bi_core = bi.split(" - ")[0]
                ai_core = ai.split(" - ")[0]
                if _normalize(bi_core) != _normalize(ai_core):
                    return False
    return has_diff


def _about_imena_trim_only(b, a):
    """True iff the only about-text diff is trimming trailing names from one
    or more 'Имена в МК: …' lines (typically dropping a priest/deacon the
    new translator no longer lists). Same encounter, just a shorter name
    list — safe to auto-approve."""
    if not _only_about_diff(b, a):
        return False
    b_about = (b.get("about") or {})
    a_about = (a.get("about") or {})
    if b_about == a_about:
        return False
    if set(b_about.keys()) != set(a_about.keys()):
        return False
    has_diff = False
    for loc, b_text in b_about.items():
        a_text = a_about.get(loc, "")
        if b_text == a_text:
            continue
        has_diff = True
        b_lines = b_text.splitlines()
        a_lines = a_text.splitlines()
        if len(b_lines) != len(a_lines):
            return False
        for bl, al in zip(b_lines, a_lines, strict=True):
            if bl == al:
                continue
            if not (bl.lstrip().startswith(">Имена в МК") and
                    al.lstrip().startswith(">Имена в МК")):
                return False
            b_items = bl.split(":", 1)[1].strip().split("; ")
            a_items = al.split(":", 1)[1].strip().split("; ")
            if len(a_items) >= len(b_items):
                return False
            if b_items[:len(a_items)] != a_items:
                return False
    return has_diff


# Generator-emitted fact lines that only ever get ADDED to an about section as
# the translator learns to surface more of what the source already said — a
# parent's «Титул/звание» the legacy pipeline missed, and the «Роль в семье»
# household position, which restates the attached document's own table. Neither
# can contradict what is already there, so a diff consisting purely of these is
# safe to auto-approve. A census profile typically gains both at once, which is
# why they share one predicate rather than getting a category each.
_ADDED_FACT_LINE_RE = re.compile(r"\s*(Титул/звание|Роль в семье)")

# «Возраст: 16 лет» → «Возраст: 16 лет (2 года, в предыдущей ревизии)». The
# only in-place edit in the same family as the added lines above: the recorded
# age is untouched, the previous revision's is appended beside it. Stripping it
# has to leave the before-line intact, or the enrichment would be classified as
# an ordinary about rewrite and lose its auto-approval.
_PREV_AGE_SUFFIX_RE = re.compile(r" \([^()]*, в предыдущей ревизии\)$")


def _is_fact_enrichment(before: str, after: str) -> bool:
    """True iff `after` is `before` with a generator enrichment appended."""
    return _PREV_AGE_SUFFIX_RE.sub("", after) == before


def _about_title_added_only(b, a):
    """True iff the only about-text diff is generator fact lines being added
    (`_ADDED_FACT_LINE_RE`) or enriched in place (`_is_fact_enrichment`).
    Nothing the source already said is contradicted — safe to auto-approve."""
    if not _only_about_diff(b, a):
        return False
    b_about = (b.get("about") or {})
    a_about = (a.get("about") or {})
    if b_about == a_about:
        return False
    if set(b_about.keys()) != set(a_about.keys()):
        return False
    has_diff = False
    for loc, b_text in b_about.items():
        a_text = a_about.get(loc, "")
        if b_text == a_text:
            continue
        has_diff = True
        b_lines = b_text.splitlines()
        a_lines = a_text.splitlines()
        # Walk both lists. Every after-only line must be a generator fact
        # line; every line consumed from `before` must be unchanged or an
        # in-place enrichment of it.
        i = j = 0
        extras = []
        enriched = False
        while j < len(a_lines):
            if i < len(b_lines) and a_lines[j] == b_lines[i]:
                i += 1
                j += 1
            elif i < len(b_lines) and _is_fact_enrichment(b_lines[i], a_lines[j]):
                enriched = True
                i += 1
                j += 1
            else:
                extras.append(a_lines[j])
                j += 1
        if i != len(b_lines):
            return False
        # An enrichment alone is a real diff even with nothing added.
        if not extras and not enriched:
            return False
        if not all(_ADDED_FACT_LINE_RE.match(line) for line in extras):
            return False
    return has_diff


_YASAK_TO_KAZYONNY = {
    "ясачный": "казенный",
    "ясачная": "казенная",
    "ясачное": "казенное",
    "ясачные": "казенные",
    "ясачного": "казенного",
    "ясачному": "казенному",
    "ясачным": "казенным",
    "ясачном": "казенном",
    "ясачной": "казенной",
    "ясачных": "казенных",
    "ясачными": "казенными",
}
_YASAK_RE = re.compile(r"\b(" + "|".join(_YASAK_TO_KAZYONNY) + r")\b")


def _about_yasak_to_kazyonny_only(b, a):
    """True iff the only about-text diff is rewriting 'ясачн… крестьянин' as
    'казенн… крестьянин' on Титул/звание lines (the same legal class of
    state-owned peasant; the term changed over time but refers to the same
    group).

    Line-by-line check: every changed line must be a Титул/звание line and
    every yasak→kazyonny substitution on that line must yield the after.
    This prevents false positives on profiles where the older yasak term
    legitimately stays for an earlier-year section (e.g. an RS 1834 entry
    keeps 'ясачная крестьянка' while a sibling RS 1850 entry on the same
    profile becomes 'казенная крестьянка')."""
    if not _only_about_diff(b, a):
        return False
    b_about = (b.get("about") or {})
    a_about = (a.get("about") or {})
    if b_about == a_about:
        return False
    if set(b_about.keys()) != set(a_about.keys()):
        return False
    has_diff = False
    for loc, b_text in b_about.items():
        a_text = a_about.get(loc, "")
        if b_text == a_text:
            continue
        has_diff = True
        b_lines = b_text.splitlines()
        a_lines = a_text.splitlines()
        if len(b_lines) != len(a_lines):
            return False
        for bl, al in zip(b_lines, a_lines, strict=True):
            if bl == al:
                continue
            if not bl.lstrip().startswith("Титул/звание"):
                return False
            normalized = _YASAK_RE.sub(
                lambda m: _YASAK_TO_KAZYONNY[m.group(1)], bl,
            )
            if normalized != al:
                return False
    return has_diff


_IO_PREFIX_RE = re.compile(r"^(\s*>)ИО в документе:\s*", re.MULTILINE)


def _about_io_prefix_only(b, a):
    """True iff the only about-text diff is prepending 'ИО в документе: ' to
    bare-name `>` lines (the census-comment update). Same content, just an
    explicit signpost that the names are the source-document spelling.

    Order-insensitive: strip the ИО prefix on both sides so a section
    reorder doesn't break the classification."""
    def strip(t):
        return _IO_PREFIX_RE.sub(r"\1", t)
    return _about_only_after_normalize(b, a, strip)


_FAMILY_SUBID_RE = re.compile(r"(семья \d+)[а-я]+\b")


def _normalize_family_subid(text):
    """Strip the optional Cyrillic-letter sub-id from family numbers so
    'семья 1' and 'семья 1в' compare equal. Sub-id is the new translator's
    finer-grained read of the РС household where the legacy generator
    emitted only the parent family number."""
    return _FAMILY_SUBID_RE.sub(r"\1", text)


_SECTION_HEADER_RE = re.compile(r"^<strong>", re.MULTILINE)


def _split_about_sections(text):
    """Split an about-block into per-record sections keyed on `<strong>...`
    headers. Returns a list of (header, body) tuples preserving original
    document order. Leading material before the first <strong> is dropped
    (it's typically empty)."""
    parts = re.split(r"(?m)^(?=<strong>)", text)
    sections = []
    for part in parts:
        part = part.strip()
        if not part or not part.startswith("<strong>"):
            continue
        # Split header line from body
        header, _, body = part.partition("\n")
        sections.append((header.strip(), body.strip()))
    return sections


def _about_only_after_normalize(b: dict[str, Any], a: dict[str, Any], normalize_b: Callable[[str], str], normalize_a: Callable[[str], str] | None = None) -> bool:
    """Generic check: True iff every locale's about diff reduces to no-diff
    after applying `normalize_b` to the BEFORE text and `normalize_a` to
    the AFTER text. Tries byte-level comparison first, then section-
    reorder-aware comparison (sections compared as sorted multisets after
    normalization).

    When `normalize_a` is None, applies the same normalizer to both sides
    (use this when the change is symmetric — e.g. stripping a token that
    might appear on either side). Specify both when the change has a
    direction — e.g. `before → after` where the normalizer strips the
    NEW-only artifact from the after text to recover the before.
    """
    if normalize_a is None:
        normalize_a = normalize_b
    if not _only_about_diff(b, a):
        return False
    b_about = (b.get("about") or {})
    a_about = (a.get("about") or {})
    if b_about == a_about:
        return False
    if set(b_about.keys()) != set(a_about.keys()):
        return False
    has_diff = False
    for loc, b_text in b_about.items():
        a_text = a_about.get(loc, "")
        if b_text == a_text:
            continue
        has_diff = True
        b_norm = normalize_b(b_text)
        a_norm = normalize_a(a_text)
        # Byte-level comparison after normalization.
        if b_norm == a_norm:
            continue
        # Section-reorder fallback: compare sorted multisets of
        # normalized (header, body) tuples. Same-year section reorders
        # (РС-before-МК) collapse to equal.
        b_secs = sorted(
            (normalize_b(h), normalize_b(body))
            for h, body in _split_about_sections(b_text)
        )
        a_secs = sorted(
            (normalize_a(h), normalize_a(body))
            for h, body in _split_about_sections(a_text)
        )
        if b_secs != a_secs:
            return False
    return has_diff


def _about_family_subid_only(b, a):
    """True iff every locale's about diff is solely a family-id sub-id
    refinement ('семья 1' ↔ 'семья 1в'). Same household, finer-grained
    addressing in the DSL. Order-insensitive across section reorder."""
    return _about_only_after_normalize(b, a, _normalize_family_subid)


def _normalize_all_cosmetic(text):
    """Apply every cosmetic-only normalizer in sequence so two about-texts
    differing in any combination of (subid refinement, ИО prefix, naselенный
    inline, residence-supp reformat, yasak→kazyon, whitespace) collapse to
    the same form.

    The order of operations matters slightly: strip residence-supp
    annotation forms first (it overlaps with naselenny patterns), then
    naselenny, then the simpler token replacements."""
    # Yasak → kazyonny (oblique-case-aware)
    text = _YASAK_RE.sub(
        lambda m: _YASAK_TO_KAZYONNY[m.group(1)], text,
    )
    # Strip residence-supp annotation forms (legacy multi-line + list-item
    # + new inline) — covers the long "не указан, взято из другой записи"
    # and "не указан в МК, но …" variants.
    text = _strip_residence_supp(text)
    # Normalize naselенный note relocation to the inline form.
    text = _normalize_naselenny(text)
    # Strip ИО-prefix on bare-name comment lines.
    text = _IO_PREFIX_RE.sub(r"\1", text)
    # Strip family-id sub-id.
    text = _normalize_family_subid(text)
    # Case-normalize sentence-initial "Помещица" at start of `>`-comment
    # lines. The new translator's caveat-relocation step doesn't always
    # capitalize after moving a mid-list note to its own `>`-paragraph;
    # this glitch shows up as P→p drift between OLD and NEW for the
    # corpus's «Помещица указана как…» comment. Lowercase both sides so
    # the cosmetic_combo classifier still matches.
    text = re.sub(
        r"^(\s*>)[Пп](омещица указана как )",
        r"\1п\2",
        text,
        flags=re.MULTILINE,
    )
    # Collapse trailing whitespace per line and trim end-of-text.
    text = "\n".join(line.rstrip() for line in text.splitlines()).rstrip()
    return text


def _about_cosmetic_combo_only(b, a):
    """True iff every locale's about diff reduces to no-diff after applying
    the full chain of cosmetic normalizers (subid + io_prefix + naselенный
    + residence_supp + yasak2kazyon + whitespace). Catches profiles whose
    only changes are some COMBINATION of those cosmetic patterns — cases
    that no single classifier accepts because each pattern is mixed with
    another. Order-insensitive across section reorder."""
    return _about_only_after_normalize(b, a, _normalize_all_cosmetic)


def _about_whitespace_only(b, a):
    """True iff every locale's about text differs only in trailing whitespace
    per line (no content change). Catches cosmetic generator-side trim drift
    that would otherwise pollute about_text batches."""
    if not _only_about_diff(b, a):
        return False
    b_about = (b.get("about") or {})
    a_about = (a.get("about") or {})
    if b_about == a_about:
        return False
    if set(b_about.keys()) != set(a_about.keys()):
        return False
    has_any_diff = False
    for loc in b_about:
        b_text = b_about[loc] or ""
        a_text = a_about[loc] or ""
        if b_text == a_text:
            continue
        has_any_diff = True
        b_norm = "\n".join(line.rstrip() for line in b_text.splitlines())
        a_norm = "\n".join(line.rstrip() for line in a_text.splitlines())
        if b_norm != a_norm:
            return False
    return has_any_diff


def _about_override_appendix_only(b, a):
    """True iff DSL's only change is inserting paragraph-break newlines
    before override.about appendix paragraphs that already exist in
    state. Detection: stripping all `\\n` and whitespace from both sides
    yields identical text — i.e., the only diff is whitespace/newline
    re-flow around an existing override.about block. Pure formatting —
    safe to auto-approve.
    """
    if not _only_about_diff(b, a):
        return False
    b_about = (b.get("about") or {})
    a_about = (a.get("about") or {})
    if set(b_about.keys()) != set(a_about.keys()):
        return False
    has_any_diff = False
    for loc in b_about:
        b_text = b_about[loc] or ""
        a_text = a_about[loc] or ""
        if b_text == a_text:
            continue
        has_any_diff = True
        # Strip all whitespace — if the underlying content matches, the
        # diff is whitespace-only (e.g., blank-line insertion).
        b_collapsed = "".join(b_text.split())
        a_collapsed = "".join(a_text.split())
        if b_collapsed != a_collapsed:
            return False
    return has_any_diff


CATEGORY_PRIORITY: list[tuple[str, Callable[[dict[str, Any], dict[str, Any]], bool]]] = [
    ("about_override_appendix", lambda b,a: _about_override_appendix_only(b, a)),
    ("about_whitespace",     lambda b,a: _about_whitespace_only(b, a)),
    ("about_naselenny",      lambda b,a: _about_naselenny_only(b, a)),
    ("about_residence_supp", lambda b,a: _about_residence_supp_only(b, a)),
    ("about_io_prefix",      lambda b,a: _about_io_prefix_only(b, a)),
    ("about_yasak2kazyon", lambda b,a: _about_yasak_to_kazyonny_only(b, a)),
    ("about_imena_trim",   lambda b,a: _about_imena_trim_only(b, a)),
    ("about_imena_added",  lambda b,a: _about_imena_added_only(b, a)),
    ("about_orthography",  lambda b,a: _about_orthography_only(b, a)),
    ("about_title_added",  lambda b,a: _about_title_added_only(b, a)),
    ("about_family_subid", lambda b,a: _about_family_subid_only(b, a)),
    ("about_cosmetic_combo", lambda b,a: _about_cosmetic_combo_only(b, a)),
    ("about_text",        lambda b,a: bool((b.get("about") or {}).get("ru") != (a.get("about") or {}).get("ru"))),
    ("name_locale",       lambda b,a: b.get("names") != a.get("names")),
    ("event_date",        lambda b,a: any(
        (b.get(e) or {}).get("date") != (a.get(e) or {}).get("date")
        for e in ("birth","death","baptism","marriage","burial"))),
    ("union_children",    lambda b,a: b.get("children") != a.get("children")),
    ("event_location",    lambda b,a: any(
        (b.get(e) or {}).get("location") != (a.get(e) or {}).get("location")
        for e in ("birth","death","baptism","marriage","burial"))),
    ("current_residence", lambda b,a: b.get("current_residence") != a.get("current_residence")),
    ("union_partners",    lambda b,a: b.get("partners") != a.get("partners")),
    ("cause_of_death",    lambda b,a: b.get("cause_of_death") != a.get("cause_of_death")),
    ("gender",            lambda b,a: b.get("gender") != a.get("gender")),
    ("projects",          lambda b,a: b.get("projects") != a.get("projects")),
    ("other",             lambda b,a: True),
]
def _doc_desc_change_kinds(b, a):
    """Classify how `description` changed. Returns a set drawn from
    {'header', 'folio'} — line 0 is the generated header line, a 'Лист:' line
    is an archive folio reference; both are safe. Returns None if any other
    line changed (a factual archive / record-body change), or an empty set if
    `description` did not change."""
    bd = (b.get("description") or "").splitlines()
    ad = (a.get("description") or "").splitlines()
    if bd == ad:
        return set()
    if not bd or len(bd) != len(ad):
        return None
    kinds = set()
    for i, (bl, al) in enumerate(zip(bd, ad, strict=False)):
        if bl == al:
            continue
        if i == 0:
            kinds.add("header")
        elif bl.lstrip().startswith("Лист:") and al.lstrip().startswith("Лист:"):
            kinds.add("folio")
        else:
            return None
    return kinds


def _doc_location_set(b, a):
    """True iff `location` is unchanged, or set to a non-empty value (added or
    corrected). A location *removal* is not safe."""
    if b.get("location") == a.get("location"):
        return True
    return bool(a.get("location"))


def _doc_review_category(b, a):
    """A manual-review geni_document change. A wholesale tagged-profile
    replacement — `profiles` changed with no original tag kept — stays in
    `documents` (the document's subject changed; needs scrutiny). A partial /
    additive re-tag, or a change with no `profiles` delta, goes to
    `documents_partial`."""
    bp = set(b.get("profiles") or [])
    ap = set(a.get("profiles") or [])
    if bp != ap and not (bp & ap):
        return "documents"
    return "documents_partial"


def _doc_category(b, a):
    """Classify a geni_document update. Pre-approved safe changes: the
    generated header (`title` / first-line `description`), an archive `Лист:`
    folio correction, and `location` being set — a single kind routes to
    documents_header / documents_folio / documents_location, a mix to
    documents_combo. A `date`-only change goes to documents_date. Other
    factual changes split between documents (wholesale profile-tag
    replacement) and documents_partial (partial re-tag) — all manual review."""
    real = {k for k in (set(b) | set(a))
            if k != "content_type" and b.get(k) != a.get(k)}
    if real == {"date"}:
        return "documents_date"
    if real - {"title", "description", "location"}:
        return _doc_review_category(b, a)
    kinds = set()
    if "description" in real:
        dk = _doc_desc_change_kinds(b, a)
        if dk is None:
            return "documents"
        kinds |= dk
    if "title" in real:
        kinds.add("header")
    if "location" in real:
        if not _doc_location_set(b, a):
            return "documents"
        kinds.add("location")
    if not kinds:
        return "documents"
    if len(kinds) > 1:
        return "documents_combo"
    return {"header": "documents_header", "folio": "documents_folio",
            "location": "documents_location"}[next(iter(kinds))]


by_category = defaultdict(list)
for c in updates:
    # geni_document updates are classified into their own categories; header
    # (title / header-line description) and location-set changes are
    # pre-approved, alone or combined.
    if c.get("type") == "geni_document":
        b = c.get("change", {}).get("before") or {}
        a = c.get("change", {}).get("after") or {}
        by_category[_doc_category(b, a)].append(c["address"])
        continue
    b = c.get("change",{}).get("before") or {}
    a = c.get("change",{}).get("after") or {}
    for cat, pred in CATEGORY_PRIORITY:
        if pred(b, a):
            by_category[cat].append(c["address"])
            break

AUTO_APPROVE_CATEGORIES = {
    "about_override_appendix", # appended free-form note (override.about)
    "about_whitespace",     # cosmetic trailing-space drift
    "about_naselenny",      # godparent-residence note relocation
    "about_residence_supp", # residence-supplement note multi-line → inline
    "about_yasak2kazyon",   # ясачный X крестьянин → казенный X крестьянин
    "about_imena_trim",     # trailing priest/deacon dropped from Имена в МК
    "about_imena_added",    # trailing relative/priest added to Имена в МК
    "about_orthography",    # ъ-restored, ie→іе, ѣ→е in source-spelling names
    "about_title_added",    # Титул/звание, Роль в семье, prev-revision Возраст
    "about_io_prefix",      # '>Foo Bar' → '>ИО в документе: Foo Bar'
    "about_family_subid",   # 'семья 1' → 'семья 1в' (finer-grained household)
    "about_cosmetic_combo", # multiple of the above patterns in same profile
    "documents_header",     # document title/description header fix
    "documents_location",   # document location set to a parish/village
    "documents_folio",      # document archive Лист (folio) correction
    "documents_combo",      # a mix of the safe document changes above
    "documents_date",       # legacy day=1 placeholder dropped from a date
}


def render_batch(category, batch_num, total_batches, addrs, village):
    out = []
    out.append(f"# `{category}` batch {batch_num:03d} of {total_batches:03d} ({len(addrs)} resources)")
    out.append("")
    if category in AUTO_APPROVE_CATEGORIES:
        out.append("**Pre-approved** (cosmetic-only category): all rows marked `[x]` by the batch builder.")
        out.append("Review the diffs and uncheck any row you want to skip, then run")
    else:
        out.append("**Review**: change `[ ]` to `[x]` next to each row to approve. After saving, run")
    out.append(f"`{village}/batches/apply_approved.sh {village}/batches/{category}/batch_{batch_num:03d}.md` to apply only approved rows.")
    out.append("")
    out.append("## Summary")
    out.append("")
    out.append("| # | Approve | Resource | Action |")
    out.append("|---|---------|----------|--------|")
    approval = "[x]" if category in AUTO_APPROVE_CATEGORIES else "[ ]"
    for i, addr in enumerate(addrs, 1):
        addr_disp = addr.replace("|", r"\|")
        out.append(f"| {i} | {approval} | [`{addr_disp}`](#diff-{i}) | change |")
    out.append("")
    out.append("## Diffs")
    out.append("")
    for i, addr in enumerate(addrs, 1):
        diff = diff_by_addr.get(addr) or "(diff not found)"
        out.append(f"### {i}. `{addr}` <a id=\"diff-{i}\"></a>")
        out.append("")
        out.append("```")
        out.append(diff)
        out.append("```")
        out.append("")
    return "\n".join(out)

# Wipe old per-category dirs before regenerating
BATCHES_DIR.mkdir(exist_ok=True)
for sub in BATCHES_DIR.iterdir():
    if sub.is_dir():
        shutil.rmtree(sub)

written = 0
for category, addrs in by_category.items():
    if not addrs: continue
    cat_dir = BATCHES_DIR / category
    cat_dir.mkdir(exist_ok=True)
    addrs.sort()
    batches = [addrs[i:i+BATCH_SIZE] for i in range(0, len(addrs), BATCH_SIZE)]
    for n, batch in enumerate(batches, 1):
        p = cat_dir / f"batch_{n:03d}.md"
        p.write_text(render_batch(category, n, len(batches), batch, ROOT.name), encoding="utf-8")
        written += 1
print(f"Wrote {written} batch files (clean format)")
