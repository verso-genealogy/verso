"""Union/MK comment and name-line helpers."""
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    pass
from verso.core.targets.geni.union import GeniUnion




def _comment_for_union(union: GeniUnion) -> str:
    """Format a single source union for the consolidated-union
    documentation comment. Verbatim transcription of the earlier generator's format:

        `{res_name} (partners: {p1}[, {p2}][; children: {c1}, {c2}, ...])`

    Children are sorted alphabetically by res_name; partners are
    listed in `partner_1, partner_2` order with no sort.
    """
    partners: list[str] = []
    if union.partner_1:
        partners.append(union.partner_1)
    if union.partner_2:
        partners.append(union.partner_2)
    partners_str = ", ".join(partners)
    children_str = (
        f"; children: {', '.join(sorted(union.children))}"
        if union.children else ""
    )
    return f"{union.res_name} (partners: {partners_str}{children_str})"



def _comment_for_unions(merged: list[GeniUnion]) -> str:
    """Build the multi-line merged-unions comment block. Format mirrors
    the earlier generator's:

        # Consolidated union with merged unions:
        # - {src1}
        # - {src2}
        ...

    Trailing newline is included so the caller can splice the block
    directly before the resource declaration.
    """
    body = "\n# - ".join(_comment_for_union(u) for u in merged)
    return f"# Consolidated union with merged unions:\n# - {body}\n"



def _name_in_mk(p):
    """Render a person's name as it appeared in the metric book: original
    name + original patronymic + last_name (e.g., `Денис Иванов`). Any
    piece the DSL doesn't carry is skipped.

    `last_name` only — NOT `last_name_modern`. The latter may have been
    auto-populated by inheritance (e.g. `Birth.__init__` filling in the
    father's surname on a child) even though the source book didn't
    write it; the "Имена в МК" transcription must reflect what was
    actually recorded.

    When the DSL marks `last_name_in_book=False`, the surname is known
    genealogically (from a separate Фамилия column or deduced) but was
    NOT in the book's ФИО — drop it from this transcription so the
    output matches what a human reading the book would have seen.
    """
    if p is None:
        return None
    parts = [
        p.name_orig or p.name_modern,
        p.patr_orig or p.patr_old,
    ]
    if getattr(p, "last_name_in_book", True):
        parts.append(p.last_name)
    joined = " ".join(x for x in parts if x)
    if not joined:
        return None
    # Per-name annotation (e.g. "имя неразбочиво написано") — render
    # inline as `{name} - {comment}` to match the legacy CSV's
    # `авторский комментарий` form for annotations bound to a single name.
    person_comment = getattr(p, "comment", None)
    if person_comment:
        joined = f"{joined} - {person_comment}"
    return joined



def _name_in_document(p, *, surname_first: bool = False):
    """Render the census "name as written in the document" note, labeled by
    which components the document carried:

        ФИО в документе: {name} {patr} {surname}   (name + patronymic + surname)
        ИО в документе:  {name} {patr}             (name + patronymic, no surname)
        Имя в документе: {name}                    (name only)

    Uses the original-orthography fields (mirrors `_name_in_mk`): `name_orig`
    (falling back to `name_modern`), `patr_orig` (falling back to `patr_old`),
    and `last_name` — the surname only when `last_name_in_book` is True (it was
    actually written in the document's ФИО). Returns `None` when there is no
    name to render. Replaces the old hand-written `comment="ФИО в документе:…"`.

    `surname_first=True` renders the ФИО case as `{surname} {name} {patr}`
    (Фамилия-Имя-Отчество) — matching sources written surname-first (e.g. the
    1917 voter lists «Телятникова Анастасия Васильева»), so the «ФИО» label
    agrees with the token order. Default (False) keeps the census `{name}
    {patr} {surname}` order.
    """
    if p is None:
        return None
    name = p.name_orig or p.name_modern
    patr = p.patr_orig or p.patr_old
    surname = p.last_name if getattr(p, "last_name_in_book", True) else None
    if patr and surname:
        label = "ФИО"
        ordered = (surname, name, patr) if surname_first else (name, patr, surname)
    elif patr:
        label = "ИО"
        ordered = (name, patr)
    else:
        label = "Имя"
        ordered = (name,)
    parts = [x for x in ordered if x]
    if not parts:
        return None
    return f"{label} в документе: {' '.join(parts)}"



def _mk_doc_name_line(dsl_person, emitted_profile, *,
                      respect_last_name_in_book: bool = True) -> str:
    """Render a `{status} {first} {patronymic} [{last_name}]` line for the
    birth document's role positions (`Отец`, `Мать`, `Воспреемник N`).

    The surname is included only when the source actually wrote it.
    `last_name_in_book=False` — set explicitly by the DSL or auto-set on
    a mother whose surname was deduced from the father — suppresses the
    surname in the document text, matching the way the book itself read.
    Callers that need legacy "always include surname" behavior pass
    `respect_last_name_in_book=False`.
    """
    parts = [dsl_person.status, emitted_profile.first_name, emitted_profile.middle_name]
    include_last = (
        not respect_last_name_in_book
        or getattr(dsl_person, "last_name_in_book", True)
    )
    if include_last:
        parts.append(emitted_profile.last_name)
    return " ".join(str(x) for x in parts if x)



def _shallow_person_without_patr(p):
    """Return a lightweight view of `p` with `patr_orig` and `patr_old`
    suppressed. Used for `Имена в МК:` rendering on death records where
    `Death.__init__` auto-derived a patronymic from the FATHER relative:
    the book itself usually wrote only the deceased's given name in that
    case, so the derived value shouldn't surface in the book-faithful
    transcription.

    The original Person object is left untouched — downstream profile
    emission still uses the derived patr_modern for res_names.
    """
    if p is None:
        return None
    import types
    ns = types.SimpleNamespace(
        name_orig=getattr(p, "name_orig", None),
        name_modern=getattr(p, "name_modern", None),
        patr_orig=None,
        patr_old=None,
        last_name=getattr(p, "last_name", None),
        last_name_in_book=getattr(p, "last_name_in_book", True),
        comment=getattr(p, "comment", None),
    )
    return ns



def _names_in_mk(*persons):
    """Semicolon-joined names-as-in-book for every person supplied. Legacy
    format: `<child_name>; <father_name>` etc., omitting empty slots."""
    rendered = [_name_in_mk(p) for p in persons]
    return "; ".join(x for x in rendered if x)
