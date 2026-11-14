"""DSL→familio mapping policy.

`project_kin` takes the geni translator's consolidated domain model (profiles +
unions, keyed by canonical res_name) and a curated kin registry, and returns the
familio resources to publish: one `FamilioPerson` per kin entry plus a
`FamilioMarriage` for every union whose BOTH partners are kin. Parent links are
derived from union membership and filtered to the kin set (a non-kin parent is
dropped, never left dangling).

This module owns ALL the geni→familio field-mapping decisions; the model module
only renders. Kept free of I/O so it is trivially unit-testable.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import NamedTuple

from verso.ru.familio.sources import MARRIAGE_ROLE, Appearance, in_about_order
from verso.ru.familio.model import (
    FamilioDate, FamilioMarriage, FamilioPerson, FamilioSource, is_uuid)
from verso.core import places
from verso.ru.naming.transliteration import generate_res_name
from verso.core.targets.geni.event import GeniEvent
from verso.core.targets.geni.profile import GeniProfile
from verso.core.targets.geni.about import strip_section_date_markers
from verso.core.targets.geni.union import GeniUnion



class KinResolutionError(ValueError):
    """Raised when a kin-registry res_name has no matching canonical profile —
    a typo, or a name left stale after a re-consolidation. Failing loudly stops
    the registry from silently dropping a relative."""

    def __init__(self, missing: list[str]):
        self.missing = missing
        super().__init__(
            "kin res_name(s) not found among canonical profiles: "
            + ", ".join(sorted(missing))
        )


def _identity(n: str) -> str:
    return n


# Russia switched Julian→Gregorian in 1918 (the day after 31 Jan 1918 Old Style
# was declared 14 Feb 1918 New Style). Dates in 1917 and earlier are transcribed
# Old Style from the metric books → stamped Julian; 1918-onward dates are already
# New Style and left at familio's gregorian default.
_GREGORIAN_REFORM_YEAR = 1918


def _calendar_for(year: int) -> str | None:
    """`"julian"` for a pre-reform (≤1917) date, else None (gregorian default)."""
    return "julian" if year < _GREGORIAN_REFORM_YEAR else None


def _familio_date(event: GeniEvent | None) -> FamilioDate | None:
    """A `FamilioDate` for a geni event, or None when the event is absent or
    has no year.

    familio (provider v0.5+) models the full complex date, so geni's `circa`
    and `date_range` qualifiers are published faithfully rather than dropped: a
    census "alive after 1897" lower bound becomes `range = "after"` (an honest
    death *bound*, not a false exact death), an approximate year becomes
    `circa = true`, and a `between` span carries its end_* endpoint. `circa` and
    `range` are mutually exclusive in familio, so a real range bound wins over
    circa; a malformed `between` without an endpoint degrades to a plain date.

    Pre-reform dates (≤1917) are additionally stamped `calendar = "julian"` (the
    metric books are Old Style); 1918-onward dates keep the gregorian default —
    see `_calendar_for`.
    """
    if event is None or event.date is None:
        return None
    d = event.date
    if d.year is None:
        return None
    cal = _calendar_for(d.year)
    if d.date_range == "between" and d.end_year is not None:
        # The provider supports a *definite* `between` span but rejects an
        # *approximate* one ("Approximate range not supported"), so a circa
        # endpoint (`end_circa`) is dropped — the span itself is kept as the
        # honest "born somewhere in this window" bound.
        return FamilioDate(
            year=d.year, month=d.month, day=d.day, date_range="between",
            end_year=d.end_year, end_month=d.end_month, end_day=d.end_day,
            calendar=cal,
        )
    if d.date_range in ("before", "after"):
        return FamilioDate(year=d.year, month=d.month, day=d.day,
                           date_range=d.date_range, calendar=cal)
    return FamilioDate(year=d.year, month=d.month, day=d.day, circa=d.circa,
                       calendar=cal)


def _about(gp) -> str | None:
    """A profile's about narrative with the internal `<!--sd:YYYY-MM-DD-->`
    section-sort markers removed.

    Those markers are an implementation detail of same-year About ordering and
    the geni renderer strips them on the way out; the familio projection has to
    do the same — the biography prints this text, and an appearance's section
    (`section_minted_for`, marker-free) is found in it by its exact text.

    Every read of `GeniProfile.about` in this module MUST go through here.
    """
    return strip_section_date_markers(gp.about)


def _about_plain(section: str) -> str:
    """Plain-text form of one geni about section: drop `<strong>` tags and the
    leading `>` quote markers, trim each line, drop blanks."""
    out: list[str] = []
    for raw in section.split("\n"):
        ln = raw.strip().replace("<strong>", "").replace("</strong>", "")
        if ln.startswith(">"):
            ln = ln[1:].strip()
        if ln:
            out.append(ln)
    return "\n".join(out)


def _about_biography(about: str | None) -> str:
    """Full plain-text biography from a geni `about`: every linked-source section
    in document order, markup stripped, blank lines collapsed to a single
    separator (unlike `_about_plain`, which drops all blanks). This is the whole
    combined summary — including the trailing memorial/«Книга памяти» appendix —
    NOT the per-event split `_event_comments` produces."""
    if not about:
        return ""
    out: list[str] = []
    prev_blank = False
    for raw in about.split("\n"):
        ln = raw.strip().replace("<strong>", "").replace("</strong>", "")
        if ln.startswith(">"):
            ln = ln[1:].strip()
        if not ln:
            if out and not prev_blank:
                out.append("")
                prev_blank = True
            continue
        out.append(ln)
        prev_blank = False
    return "\n".join(out).strip()


def _event_comments(appearances: Sequence[Appearance]) -> dict[str, str]:
    """Per-event familio comments from a person's appearances, in about order.

    Each event keeps the section(s) of the records documenting it for THIS
    person (`Appearance.event`):
      * birth — their own birth record (DIRECT), plus the INDIRECT sources that
        fix a circa birth year by recording an age: their marriage as groom or
        bride, their death, and every roll counting them. Direct first, then
        indirect in about order.
      * christening — their own birth record only (the baptism shares it).
      * death — their own burial section; with none, the rolls listing them
        dead since the last revision, which is where the circa year comes from.
    A wedding's comment is the union's (`project_kin`), which knows the spouse.
    A parent's, godparent's, witness's or relative's appearance, a list entry
    and a catalog card carry no event of this person and are dropped. Markup
    is stripped to plain text. Returns birth/christening/death."""
    birth_direct: list[str] = []
    birth_indirect: list[str] = []
    christening: list[str] = []
    death: list[str] = []
    roll_death: list[str] = []
    for a in appearances:
        text = _about_plain(a.text)
        if not text:
            continue
        if a.event == "birth":
            birth_direct.append(text)
            christening.append(text)
        elif a.event == "marriage":
            birth_indirect.append(text)   # age in the marriage ⇒ birth year
        elif a.event == "death":
            death.append(text)
            birth_indirect.append(text)   # age at death ⇒ birth year
        elif a.event == "census":
            birth_indirect.append(text)   # a roll's age ⇒ birth year
            if a.died:
                roll_death.append(text)   # «умер (1846)» ⇒ the circa death
    return {
        "birth": "\n\n".join(birth_direct + birth_indirect),
        "christening": "\n\n".join(christening),
        "death": "\n\n".join(death or roll_death),
    }


def _own_weddings(appearances: Sequence[Appearance], spouse: str,
                  year: int | None) -> list[Appearance]:
    """This person's own weddings to `spouse` — the record marries the two —
    or, for a union dated by its wedding, in that year: the union's own event,
    even where the fold left the record's bride a profile apart. A
    twice-married person's OTHER wedding is not this marriage's."""
    return [a for a in appearances if a.event == "marriage"
            and (a.spouse == spouse or (year is not None and a.year == year))]


def _children_weddings_comment(*partners: Sequence[Appearance], children: frozenset[str]) -> str:
    """The weddings of this union's children at which the record names a
    partner the groom's or bride's parent — for a couple whose own wedding the
    corpus lacks, the records that attest the family. Each record once, the
    first partner's sections first, each partner's in about order."""
    seen: set[tuple[object, ...]] = set()
    out: list[str] = []
    for appearances in partners:
        for a in appearances:
            if a.weds_children & children and a.record not in seen:
                seen.add(a.record)
                if text := _about_plain(a.text):
                    out.append(text)
    return "\n\n".join(out)


class _MarriageSection(NamedTuple):
    """The parts of one partner's marriage section that matter when combining
    both spouses into a shared Familio marriage comment."""

    header: str        # "МК <village> <year>" — the role word (жених/невеста) dropped
    title: str         # how the record styles the partner ("" when it does not)
    age: str           # the partner's age as the record states it ("" when absent)
    record_note: str   # shared tail: "Комментарий из МК:" + "Имена в МК: …" + any free note


def _marriage_section_parts(wedding: Appearance) -> _MarriageSection:
    """One partner's wedding appearance, split for the shared comment. The title
    and the age are the record's own statements (`Appearance.title/age`); the
    header is the section's first line less the role word the slot names; the
    note is every other line, which both spouses' sections share."""
    lines = _about_plain(wedding.text).split("\n")
    role = MARRIAGE_ROLE.get(wedding.slot, "")
    header = lines[0].removesuffix(role).rstrip().removesuffix(":").strip() if lines else ""
    said = {f"Возраст: {wedding.age}" if wedding.age else "",
            f"Титул/звание: {wedding.title}" if wedding.title else ""} - {""}
    note_lines: list[str] = []
    for ln in lines[1:]:
        if ln in said:
            said.discard(ln)
        else:
            note_lines.append(ln)
    return _MarriageSection(header, wedding.title, wedding.age, "\n".join(note_lines).strip())


def _full_modern_name(person: FamilioPerson, *, maiden: bool = False) -> str:
    """Modern-orthography full name «Имя Отчество Фамилия», empty parts skipped.
    `maiden=True` prefers the maiden surname (the bride at her wedding)."""
    surname = (person.birth_last_name or person.last_name) if maiden else person.last_name
    return " ".join(p for p in (person.first_name, person.patronymic, surname) if p)


def _marriage_role_line(label: str, name: str, title: str) -> str:
    """`<label>: <name>, <title>` — with `, <title>` dropped when there is no
    title, and a bare `<label>` when neither name nor title is known."""
    who = ", ".join(p for p in (name, title) if p)
    return f"{label}: {who}" if who else label


def _shared_marriage_comment(groom: Sequence[Appearance], bride: Sequence[Appearance], *,
                             groom_name: str, bride_name: str) -> str:
    """Combine both spouses' wedding sections into one shared-event comment naming
    both. Only when each partner has exactly one wedding that year; otherwise the
    single-partner text (an empty side, or a rare double entry that can't be
    safely merged)."""
    groom_text = "\n\n".join(t for a in groom if (t := _about_plain(a.text)))
    bride_text = "\n\n".join(t for a in bride if (t := _about_plain(a.text)))
    if not (len(groom) == 1 and len(bride) == 1 and groom_text and bride_text):
        return groom_text or bride_text
    g = _marriage_section_parts(groom[0])
    b = _marriage_section_parts(bride[0])
    lines = [
        g.header or b.header,
        _marriage_role_line("Жених", groom_name, g.title),
        _marriage_role_line("Невеста", bride_name, b.title),
    ]
    # Each spouse's «Возраст» stays attributed to them — an unlabeled shared
    # line after the Невеста row would read as the bride's age.
    if g.age:
        lines.append(f"Возраст жениха: {g.age}")
    if b.age:
        lines.append(f"Возраст невесты: {b.age}")
    note = g.record_note or b.record_note
    if note:
        lines.append(note)
    return "\n".join(lines)


def _latest_source_comment(appearances: Sequence[Appearance]) -> str:
    """Plain text of the LATEST record naming the person (the greatest year; the
    last in about order on a tie) — the source of an 'after'-bounded death,
    which has no burial record of its own: the bound comes from a roll counting
    the person or a parent role in someone else's record. '' when none."""
    best: Appearance | None = None
    for a in appearances:
        if a.year is not None and (best is None or best.year is None or a.year >= best.year):
            best = a
    return _about_plain(best.text) if best is not None else ""


def _has_own_birth_record(appearances: Sequence[Appearance]) -> bool:
    """True when the person has their OWN birth record — a birth or christening
    entry naming them as the child, not a roll or a parent role. Gates
    birth_place so a residence-derived location isn't asserted as a
    birthplace for married-in or roll-only people."""
    return any(a.event == "birth" for a in appearances)


def _settlement_local_name(key: str) -> str:
    """The terraform local name for a settlement key, e.g.
    'Нижняя Яичница' → 'settlement_nizhnjaja_jaichnitsa' (res_name transliteration)."""
    return f"settlement_{generate_res_name(key)}"


def _settlement_place(event: GeniEvent | None) -> str:
    """A terraform `local.settlement_*` reference for a geni event's location,
    or "" when the event has no location or the place isn't mapped in
    `familio_settlements`. The UUID itself lives in the generated `locals` block
    (see `settlement_locals_hcl`), so place fields reference it by name rather
    than repeating the opaque id inline."""
    if event is None or not event.location:
        return ""
    current = places.current()
    key = current.key_for_body(event.location)
    if not key or key not in current.attributes.get("familio", {}):
        return ""
    return f"local.{_settlement_local_name(key)}"


def settlement_locals_hcl() -> str:
    """A terraform `locals` block mapping each familio settlement's local name
    to its UUID — the single place the settlement ids are spelled out; person
    `place` fields reference them as `local.settlement_*`."""
    settlements = places.current().attributes.get("familio", {})
    lines = ["locals {"]
    for key in sorted(settlements):
        lines.append(f'  {_settlement_local_name(key)} = "{settlements[key]}"  # {key}')
    lines.append("}")
    return "\n".join(lines) + "\n"


_SOURCE_TYPES = ("case", "catalog_person")


def parse_sources(
    raw: Mapping[str, Sequence[Mapping[str, str]]],
) -> dict[str, tuple[FamilioSource, ...]]:
    """Validate + convert a raw FAMILIO_SOURCES registry (res_name → list of
    citation dicts) into FamilioSource tuples. A `catalog_person` source requires
    a `catalog_key`; a `case` must not carry one (the дело is fully identified by
    its uuid)."""
    out: dict[str, tuple[FamilioSource, ...]] = {}
    for res, entries in raw.items():
        built: list[FamilioSource] = []
        for e in entries:
            typ = e.get("type", "")
            if typ not in _SOURCE_TYPES:
                raise ValueError(
                    f"{res}: source type must be one of {_SOURCE_TYPES}, got {typ!r}")
            ref = e.get("reference_uuid", "")
            if not ref:
                raise ValueError(f"{res}: source missing reference_uuid")
            key = e.get("catalog_key", "")
            if typ == "catalog_person" and not key:
                raise ValueError(f"{res}: catalog_person source needs a catalog_key")
            if typ == "case" and key:
                raise ValueError(f"{res}: case source must not carry a catalog_key")
            built.append(FamilioSource(
                reference_uuid=ref, type=typ, catalog_key=key,
                comment=e.get("comment", "")))
        out[res] = tuple(built)
    return out


def _is_local_res_name(ref: str | None) -> bool:
    """True for a plain local resource res_name. False for empty refs and for
    the external forms a union may carry — `data.geni_profile.*` data sources
    and raw `profile-NNNN` Geni ids — which can never be local kin."""
    if not ref:
        return False
    return not ref.startswith("data.geni_profile.") and "profile-" not in ref


def project_kin(
    profiles: Mapping[str, GeniProfile],
    unions: Mapping[str, GeniUnion],
    kin: Mapping[str, str | None],
    *,
    resolve: Callable[[str], str] | None = None,
    parent_overrides: Mapping[str, tuple[str, ...]] | None = None,
    sources_by_res: Mapping[str, Sequence[FamilioSource]] | None = None,
    appearances: Mapping[str, Sequence[Appearance]] | None = None,
) -> tuple[list[FamilioPerson], list[FamilioMarriage]]:
    """Project the kin subset of `profiles`/`unions` onto familio resources.

    Args:
        profiles: canonical `GeniProfile`s by res_name
            (`TerraformGenerator.canonical_profiles()`).
        unions:   canonical `GeniUnion`s by res_name (`canonical_unions()`).
        kin:      registry mapping a canonical res_name → familio UUID to import
            (or None to create). Order is preserved in the returned persons.
        resolve:  optional normaliser mapping a union partner/child ref to its
            canonical res_name (e.g. `TerraformGenerator.resolve_canonical`);
            defaults to identity.
        appearances: each canonical's records, with the about section minted
            for each (`verso.ru.familio.sources.appearances_by_canonical`) — what
            every event comment cites. Without them no comment is written.

    Returns `(persons, marriages)`. Raises `KinResolutionError` if any kin
    res_name is unknown, and `ValueError` if a kin profile lacks the
    provider-required gender.
    """
    norm: Callable[[str], str] = resolve if resolve is not None else _identity

    missing = [k for k in kin if k not in profiles]
    if missing:
        raise KinResolutionError(missing)

    # Each kin person's records, in the order their sections stand in the about,
    # and the per-event comments cited from them — once, reused for the person
    # and (for the wedding) its union.
    cited: dict[str, list[Appearance]] = {
        res: in_about_order(list((appearances or {}).get(res, ())), _about(profiles[res]))
        for res in kin
    }
    comments: dict[str, dict[str, str]] = {
        res: _event_comments(cited[res]) for res in kin
    }

    persons: dict[str, FamilioPerson] = {}
    for res, uuid in kin.items():
        gp = profiles[res]
        if not gp.gender:
            raise ValueError(f"familio_person '{res}': gender is required")
        # Maiden surname only when it genuinely differs from the current/married
        # surname — otherwise Geni's two-field split falsely implies a rename.
        maiden = gp.birth_last_name if gp.birth_last_name != gp.last_name else ""
        cm = comments[res]
        # An "after"-bounded death has no burial record, so cm["death"] is empty;
        # cite the latest record that mentions the person (the source of the bound).
        death_comment = cm["death"]
        if not death_comment and gp.death and gp.death.date and gp.death.date.date_range == "after":
            death_comment = _latest_source_comment(cited[res])
        # Birth place only for a real own birth record — a residence-derived
        # location must not be asserted as a birthplace (see _has_own_birth_record).
        birth_place = (
            _settlement_place(gp.birth) if _has_own_birth_record(cited[res]) else ""
        )
        # IaC: biography + event comments are declared desired state — always
        # emit them (for imports AND creates) so the terraform config fully owns
        # each person's prose. (Provider ≥0.14 preserve-on-omit is thus inert here;
        # to keep a familio-only note, add it in the config via additional_info.)
        persons[res] = FamilioPerson(
            res_name=res,
            gender=gp.gender,
            first_name=gp.first_name,
            last_name=gp.last_name,
            patronymic=gp.middle_name,   # отчество
            birth_last_name=maiden,
            birth_date=_familio_date(gp.birth),
            death_date=_familio_date(gp.death),
            christening_date=_familio_date(gp.baptism),
            birth_comment=cm["birth"],
            death_comment=death_comment,
            # the whole combined all-sources narrative (geni `about`) → familio's
            # free-text biography «tab=2»; overlaps the filtered per-event comments
            biography=_about_biography(_about(gp)),
            # only when the person actually has a baptism event (else the comment
            # would mint a spurious christening event)
            christening_comment=cm["christening"] if gp.baptism else "",
            birth_place=birth_place,
            # baptism happened at the birth place (same record)
            christening_place=birth_place if gp.baptism else "",
            # death place only from a real death record: derived deaths
            # ("after"-bounds, spouse/witness bounds) carry no location,
            # so the event's own location presence is the gate.
            death_place=_settlement_place(gp.death),
            uuid=uuid,
        )

    def kin_ref(ref: str | None) -> str | None:
        """Canonical kin res_name for a union ref, or None if not local kin."""
        if not _is_local_res_name(ref):
            return None
        canon = norm(ref)  # type: ignore[arg-type]  # _is_local_res_name guards None
        return canon if canon in kin else None

    marriages: list[FamilioMarriage] = []
    seen_pairs: set[frozenset[str]] = set()
    for union in unions.values():
        p1 = kin_ref(union.partner_1)
        p2 = kin_ref(union.partner_2)

        # Parent links: each kin child of this union gets the union's kin
        # partners as parents (deduped, capped at familio's max of 2).
        kin_parents = [p for p in (p1, p2) if p]
        if kin_parents:
            for child in union.children:
                cres = kin_ref(child)
                if cres is None:
                    continue
                merged = list(dict.fromkeys((*persons[cres].parents, *kin_parents)))
                persons[cres].parents = tuple(merged[:2])

        # Marriage: only when both partners are kin (a marriage to a non-kin
        # spouse has no familio_person to point at).
        if p1 and p2:
            pair = frozenset((p1, p2))
            if pair not in seen_pairs:
                seen_pairs.add(pair)
                # Groom-first: partner_1 is the жених (comments.py lists the
                # marriage narrative in partner_1, partner_2 order). Ordering by
                # role — not by res_name sort — keeps the resource address, the
                # partners array, and the comment citation stable no matter how a
                # partner's res_name string sorts (e.g. when a partner is renamed).
                a, b = p1, p2
                m_year = (union.marriage.date.year
                          if union.marriage and union.marriage.date else None)
                # A Familio marriage is a shared event: combine BOTH spouses'
                # sections of their own wedding (each partner's own about is
                # per-person on geni) into one comment naming both. Without
                # one, the weddings of their children that name them parents.
                children = frozenset(norm(c) for c in union.children
                                     if _is_local_res_name(c))
                m_comment = (
                    _shared_marriage_comment(
                        _own_weddings(cited[a], b, m_year), _own_weddings(cited[b], a, m_year),
                        groom_name=_full_modern_name(persons[a]),
                        bride_name=_full_modern_name(persons[b], maiden=True))
                    or _children_weddings_comment(cited[a], cited[b], children=children)
                )
                marriages.append(
                    FamilioMarriage(
                        res_name=f"{a}_and_{b}",
                        partner_1=a,
                        partner_2=b,
                        marriage_date=_familio_date(union.marriage),
                        comment=m_comment,
                        # Wedding place — the parish where the marriage was
                        # recorded, from the geni union's marriage location.
                        place=_settlement_place(union.marriage),
                    )
                )

    # Explicit parent overrides win over union-derived parents — for a child the
    # census wrongly groups under the head's *current* spouse (e.g. a son from a
    # first marriage placed under the second wife). Refs are filtered to kin.
    # A parent ref is kept when it's a kin res_name we manage, OR a bare familio
    # UUID (a parent that lives only on the user's familio tree — e.g. a married-in
    # spouse's father, or an ancestor beyond our records — pinned to restore a link
    # our union-derived parents can't express).
    for child, parent_res in (parent_overrides or {}).items():
        if child in persons:
            persons[child].parents = tuple(
                p for p in parent_res if p in kin or is_uuid(p)
            )[:2]

    # «Источники» citations — a curated per-person set (familio catalog UUIDs
    # aren't in the geni model, so they live in the familio kin registry).
    for res, srcs in (sources_by_res or {}).items():
        if res in persons:
            persons[res].sources = tuple(srcs)

    return list(persons.values()), marriages
