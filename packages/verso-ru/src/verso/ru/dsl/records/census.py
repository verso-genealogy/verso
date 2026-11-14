from __future__ import annotations

from calendar import Month
from copy import deepcopy
from enum import StrEnum
from typing import TYPE_CHECKING, TypedDict

from verso.ru.gender import Gender
from verso.ru.domain import Person, RecordDefaults
from verso.ru.naming import derive_patronymic, derive_old_patronymic, feminize_surname
from verso.core.written import captures_written

if TYPE_CHECKING:
    from verso.ru.exporters.base import RecordsExporter


class CensusRole(StrEnum):
    HEAD = "хозяин"
    WIFE = "жена"
    HUSBAND = "муж"
    SON = "сын"
    DAUGHTER = "дочь"
    BROTHER = "брат"
    UNCLE = "дядя"
    GRANDSON = "внук"
    GRANDDAUGHTER = "внучка"
    DAUGHTER_IN_LAW = "невестка"
    SON_IN_LAW = "зять"
    BROTHER_IN_LAW = "шурин"
    STEPSON = "пасынок"
    NEPHEW = "племянник"
    NIECE = "племянница"
    COUSIN = "двоюродный брат"
    MOTHER = "мать"
    FATHER = "отец"
    SISTER = "сестра"
    STEPDAUGHTER = "падчерица"
    LODGER = "прохожий"
    STEPBROTHER = "сводный брат"
    # Foster children (приёмыш): recorded in the household but NOT a biological
    # child of anyone in it (real parents unknown/elsewhere — the child's own
    # patronymic names the real father). The translator links them to HEAD's
    # union via `foster_children` (Geni "foster" relationship modifier), never
    # as a biological child. Distinct from STEPSON/STEPDAUGHTER, which ARE a
    # biological child of one spouse. Pass the child's own patronymic/surname
    # explicitly — nothing derives from the foster parent's given name.
    FOSTER_SON = "приёмный сын"
    FOSTER_DAUGHTER = "приёмная дочь"


# Roles that unambiguously imply a gender.
# HEAD and LODGER are omitted — both can be male or female.
ROLE_GENDER: dict[CensusRole, Gender] = {
    CensusRole.WIFE: Gender.FEMALE,
    CensusRole.HUSBAND: Gender.MALE,
    CensusRole.SON: Gender.MALE,
    CensusRole.DAUGHTER: Gender.FEMALE,
    CensusRole.BROTHER: Gender.MALE,
    CensusRole.UNCLE: Gender.MALE,
    CensusRole.GRANDSON: Gender.MALE,
    CensusRole.GRANDDAUGHTER: Gender.FEMALE,
    CensusRole.DAUGHTER_IN_LAW: Gender.FEMALE,
    CensusRole.SON_IN_LAW: Gender.MALE,
    CensusRole.BROTHER_IN_LAW: Gender.MALE,
    CensusRole.STEPSON: Gender.MALE,
    CensusRole.NEPHEW: Gender.MALE,
    CensusRole.NIECE: Gender.FEMALE,
    CensusRole.COUSIN: Gender.MALE,
    CensusRole.MOTHER: Gender.FEMALE,
    CensusRole.FATHER: Gender.MALE,
    CensusRole.SISTER: Gender.FEMALE,
    CensusRole.STEPDAUGHTER: Gender.FEMALE,
    CensusRole.FOSTER_SON: Gender.MALE,
    CensusRole.FOSTER_DAUGHTER: Gender.FEMALE,
}

# Foster-child roles (приёмыш): linked to HEAD via the union's `foster_children`
# (Geni "foster" modifier), never as a biological child. See CensusRole above.
_FOSTER_ROLES = {CensusRole.FOSTER_SON, CensusRole.FOSTER_DAUGHTER}

# Subset used for patronymic derivation (roles where the parent is in the household).
_CHILD_ROLES = {CensusRole.SON, CensusRole.DAUGHTER, CensusRole.GRANDSON, CensusRole.GRANDDAUGHTER}

# Roles whose surname is the husband's married surname, feminized
# (e.g. WIFE "Индюшева" from head "Индюшев").
_MARRIED_WOMEN_ROLES = {CensusRole.WIFE, CensusRole.DAUGHTER_IN_LAW}
# Male child roles: inherit the father's surname verbatim.
_SON_ROLES = {CensusRole.SON, CensusRole.GRANDSON, CensusRole.FOSTER_SON}
# Female child roles: inherit the father's surname feminized, as maiden name.
_DAUGHTER_ROLES = {CensusRole.DAUGHTER, CensusRole.GRANDDAUGHTER, CensusRole.FOSTER_DAUGHTER}
# Roles whose actual parent/husband is one of HEAD's children, not HEAD
# himself — so they require an explicit `ref_member` (no HEAD fallback).
_REQUIRE_REF_MEMBER = {
    CensusRole.GRANDSON, CensusRole.GRANDDAUGHTER, CensusRole.DAUGHTER_IN_LAW,
}


def _resolve_relative_source(m, head, members_by_num):
    """Resolve the household member whose name `m` derives its patronymic /
    surname from (the father for children, the husband for wives).

    Uses the explicit `ref_member` when present; otherwise falls back to the
    household HEAD — except for roles in `_REQUIRE_REF_MEMBER` (grandchildren,
    daughters-in-law), whose parent/husband is a child of HEAD rather than
    HEAD himself, so falling back to HEAD would misrepresent the lineage.
    Returns the source `CensusMember` or `None` when it can't be identified.
    """
    if m.ref_member is not None:
        return members_by_num.get(m.ref_member)
    if m.role in _REQUIRE_REF_MEMBER:
        return None
    return head


class CensusMember:
    def __init__(self, number, person: Person, role: CensusRole | None, ref_member: int | None = None,
                 age: int | str | None = None, previous_age: int | str | None = None, marital_status: str | None = None,
                 occupation: str | None = None, origin: str | None = None, destination: str | None = None,
                 arrival_year: int | None = None, arrival_reason: str | None = None, departure_year: int | None = None,
                 departure_reason: str | None = None, record_number: int | None = None, birth_day: int | None = None,
                 birth_month: Month | None = None, birth_year: int | None = None, parent_member: int | None = None,
                 father_ref: str | None = None, secondary_role: CensusRole | None = None,
                 secondary_ref_member: int | None = None, hidden: bool = False,
                 comment: str | None = None, spouse_member: int | None = None,
                 source_age_error: str | None = None,
                 previous_age_error: str | None = None):
        self.number = number
        self.person = person
        self.role = role
        self.age = age
        self.ref_member = ref_member
        self.marital_status = marital_status
        self.occupation = occupation
        self.origin = origin
        self.comment = comment
        self.destination = destination
        self.arrival_year = arrival_year
        self.departure_year = departure_year
        self.arrival_reason = arrival_reason
        self.departure_reason = departure_reason
        self.previous_age = previous_age
        self.record_number = record_number
        self.birth_day = birth_day
        self.birth_month = birth_month
        self.birth_year = birth_year

        # Validate the (reconstructed) birth date, mirroring Birth.__init__.
        # `birth_month` is a `calendar.Month` constant (Month.JANUARY …
        # Month.DECEMBER) — raw integers are no longer accepted, so the enum
        # type itself guarantees a valid month and no range check is needed.
        if self.birth_day is not None and not (1 <= self.birth_day <= 31):
            raise ValueError(f"Invalid birth day: {self.birth_day}")
        if self.birth_year is not None and not (1500 <= self.birth_year <= 2000):
            raise ValueError(f"Invalid birth year: {self.birth_year}")
        # Upward parent link, separate from `ref_member` (which encodes
        # the CSV's primary `Номер внутри семьи с кем эта связь` —
        # downward for ascending roles like FATHER/MOTHER/UNCLE that
        # describe relationship TO the head). `parent_member` points at
        # this member's father/mother in the same household, used only
        # for sub-family union emission. Mirrors the CSV's secondary
        # `Номер внутри семьи с кем эта связь 2` column when that
        # column captured the upward link.
        self.parent_member = parent_member
        # What `ref_member` MEANS when the role cannot say it. A member
        # entered with `role=None` carries `ref_member=N`, and N is read as a
        # spouse by one branch of the generator and as a parent by another —
        # the DSL comment «первый муж Аксиньи» is the only place the intent is
        # written down, and a comment is not a link. `spouse_member=N` states
        # it: «this member is the husband/wife of member N».
        #
        # The TRANSLATOR DOES NOT READ IT. `_resolve_parent_ref` and the
        # household-union passes go on reading `ref_member` exactly as before,
        # so declaring it cannot move a `.tf` byte. It is read by
        # `verso.ru.facts.extract.census`, which must state SpouseOf or ParentOf
        # and may not guess which, and it is checked by CPL007 — a `role=None`
        # member whose `ref_member` is not also named on a typed axis
        # (`spouse_member`, `parent_member`, or `secondary_role` +
        # `secondary_ref_member`) is an instruction about the encoding rather
        # than a claim about a person.
        #
        # Not the same field as `secondary_role`/`secondary_ref_member` below,
        # which states the same kind of claim and additionally MINTS the union
        # for it. Use that one when the reconstructed marriage should reach
        # Geni; use this one to say what `ref_member` means and change nothing.
        self.spouse_member = spouse_member
        # Free text: the ages this line states have been re-read on the scan
        # and the transcription is faithful, but the scribe's figure cannot be
        # reconciled with the rest of the record trail — «47» for a man whose
        # christening, earlier roll and wedding all say 31. The census twin of
        # `death(source_age_error=)`: `verso.ru.facts` withdraws every age the line
        # states, and the birth year computed from them, so the checks stop
        # reading the slip as a claim; the translator derives no birth date
        # from the line either (since 2026-09-25 — no twin `ignore` entry is
        # needed). The document and the «Возраст» line still print what the
        # roll says.
        self.source_age_error = source_age_error
        # The narrow form: only the PREVIOUS revision's figure is wrong. A
        # roll copies that column forward from the last tale, so a slip made
        # in one revision reaches the next line intact while the later clerk's
        # own age and the birth date he took from the metric book are right — a
        # youth written «12» in the earlier tale (the metric book makes him 16)
        # stands at «12 → 33» with his exact birth date in the later one.
        # `verso.ru.facts` withdraws that one age and keeps
        # the rest of the line; the translator dates the birth by the current
        # age instead of the previous one (nothing, if the current column only
        # repeats it).
        self.previous_age_error = previous_age_error
        # Cross-household father reference: consolidated profile name
        # (e.g. `kallinik_jakovlevich`) of this member's father when
        # the father isn't in the same household. Use case: a WIFE
        # married into another household whose father lives elsewhere.
        # The generator emits a single-partner sub-family union linking
        # `father_ref` → this member's consolidated profile, restoring
        # the link that legacy inferred via patronymic-based name
        # matching across the corpus. The value MUST be a consolidated
        # profile name; per-record stub names will not be canonicalized.
        self.father_ref = father_ref
        # Secondary relationship: a member may stand in two relationships
        # at once (e.g. m12 is BROTHER of HEAD AND HUSBAND of m2). The
        # primary `role`/`ref_member` always describe the relationship
        # as recorded in the source document — preserving fidelity to
        # the original text. `secondary_role` + `secondary_ref_member`
        # describe an additional relationship reconstructed from cross-
        # document evidence (other censuses, MK records). Currently
        # used to encode HUSBAND/WIFE links so the translator emits a
        # marital union without rewriting the primary role.
        self.secondary_role = secondary_role
        self.secondary_ref_member = secondary_ref_member
        # Explicit "this member was added manually for the genealogy
        # chain — they are NOT in the actual revision book". Replaces
        # the implicit sentinels `record_number="X-Y"` (string overload)
        # and `comment` containing "Отсутствует в РС". Read everywhere
        # via the `is_hidden()` helper.
        self.hidden = hidden

        implied_gender = ROLE_GENDER.get(role)
        if implied_gender and person.gender and person.gender != implied_gender:
            raise ValueError(
                f"Gender mismatch: role '{role}' implies {implied_gender}, "
                f"but person '{person.name_modern}' has gender {person.gender}"
            )
        if (secondary_role is None) != (secondary_ref_member is None):
            raise ValueError(
                f"secondary_role and secondary_ref_member must be set "
                f"together (got role={secondary_role!r}, "
                f"ref_member={secondary_ref_member!r})"
            )
        secondary_implied = ROLE_GENDER.get(secondary_role) if secondary_role else None
        if (secondary_implied and person.gender
                and person.gender != secondary_implied):
            raise ValueError(
                f"Gender mismatch: secondary_role '{secondary_role}' "
                f"implies {secondary_implied}, but person "
                f"'{person.name_modern}' has gender {person.gender}"
            )

    def is_hidden(self) -> bool:
        """True when the member is a manually-added genealogy-chain
        placeholder, not an actual revision-book entry. The DSL
        signals this with `hidden=True` on `member()` / `CensusMember`."""
        return self.hidden


class CensusHousehold:
    def __init__(self, family_id: str | None, members: list[CensusMember], page: str | None = None,
                 case: str | None = None, comment: str | None = None, record_day: int | None = None,
                 record_month: Month | None = None, reviewed: bool | None = None):
        self.page = page
        self.case = case
        self.comment = comment
        # Transcribed but not yet checked against the scan. Mirrors the
        # `reviewed` flag on births/marriages/deaths: an unreviewed household
        # emits NO profiles, document or union, so a half-read двор cannot
        # reach Geni. `None` means "inherit the file-level default" set on
        # `census_records(reviewed=…)`; CensusRecords resolves it at
        # construction, so the translator only ever sees True/False.
        self.reviewed = reviewed
        # Cat B1: per-page "Дата записи" (date of this census-page entry).
        # Populated by `page()` helper in genealogy.py when `day=/month=`
        # are supplied. Only 1816/1834 legacy census files carry explicit
        # dates in res_names; pre-1816 CSVs didn't have the column so the
        # translator uses 0/0 (rendered as `_00_00_`) for those.
        self.record_day = record_day
        self.record_month = record_month
        # Optional display family_id override (e.g. "1а" / "1b" for
        # legacy's Cyrillic-suffixed households). When set, the
        # translator uses this in res_names / doc titles instead of the
        # 1-based h_index. Defaults to None (use h_index).
        self.family_id = family_id
        # Deep copy to avoid mutating caller-owned Person objects
        self.members = deepcopy(list(members))

        _CHILD_ROLE_GENDER = {r: ROLE_GENDER[r] for r in _CHILD_ROLES}

        members_by_num = {m.number: m for m in self.members}
        head = next((m for m in self.members if m.role == CensusRole.HEAD), None)

        for m in self.members:
            child_gender = _CHILD_ROLE_GENDER.get(m.role)
            if child_gender is None:
                continue                          # not a child role
            if m.person.patr_orig:
                continue                          # patronymic already provided
            # Adopted children (роль в оригинале: приемная дочь /
            # приемный сын / приемыш): the listed `ref_member` is the
            # foster parent, not the biological father. Russian
            # patronymics derive from the biological father; deriving
            # from an adoptive parent misrepresents lineage. Skip.
            if m.comment and "приемн" in m.comment.lower():
                continue
            # Hidden members (`hidden=True`, or the legacy sentinels
            # recognised by `is_hidden()`) are placeholder ancestors
            # used for the genealogy chain, not actual revision-book
            # entries. Their CSV-relationship is often `сын [#]1` but
            # the role is just a chain marker — legacy emitted them
            # with `first_name` only. Skip patronymic derivation.
            if m.is_hidden():
                continue
            # GRANDSON/GRANDDAUGHTER's parent is one of HEAD's children,
            # not HEAD himself. `_resolve_relative_source` returns None for
            # them without an explicit `ref_member`, so we skip rather than
            # (mis)represent the grandchild as a direct child of HEAD.
            parent = _resolve_relative_source(m, head, members_by_num)
            if parent is None:
                continue
            # Russian patronymics derive from the FATHER's name. When
            # the resolved parent is female (e.g. a widowed female head
            # of household), the child's father is unknown — leave the
            # patronymic blank rather than fabricate a matronymic
            # ("Дарьична") that doesn't exist in the historical record.
            if parent.person.gender == Gender.FEMALE:
                continue
            derived = derive_patronymic(parent.person.name_modern, child_gender)
            if derived and derived != "?":
                m.person.patr_modern = derived
                old_form = derive_old_patronymic(parent.person.name_modern, child_gender)
                if old_form:
                    m.person.patr_orig = old_form
                    m.person.patr_old = old_form
                else:
                    m.person.patr_orig = derived
                    m.person.patr_old = derived

        # Surname inheritance from the household head/husband: census books
        # routinely omit a wife's or child's surname when the family surname
        # is recorded once on the head. Mirror the birth-/death-record rule
        # (births.py / deaths.py): a member with no surname of their own
        # inherits the resolved source's surname, gender-adjusted.
        #
        # Only the modern fields are populated — `last_name_modern` for
        # wives/sons, `birth_last_name_modern` for daughters — while
        # `last_name` (the as-written form) stays empty so the document-text
        # rendering keeps the original "no surname in book" appearance, yet
        # the profile still consolidates across records. A married woman's
        # inherited surname is her married name, so it routes to
        # `last_name_modern` with `last_name_in_book=False`; an unmarried
        # daughter's routes to `birth_last_name_modern` (Geni maiden_name).
        for m in self.members:
            role = m.role
            is_married_woman = role in _MARRIED_WOMEN_ROLES
            is_son = role in _SON_ROLES
            is_daughter = role in _DAUGHTER_ROLES
            if not (is_married_woman or is_son or is_daughter):
                continue
            p = m.person
            # A current surname already present → nothing to inherit. (A
            # married woman's known maiden name in `birth_last_name_modern`
            # does NOT block deriving her married surname — the two coexist.)
            if p.last_name or p.last_name_modern:
                continue
            # An unmarried daughter whose maiden name is already known is
            # complete; don't overwrite it.
            if is_daughter and p.birth_last_name_modern:
                continue
            if m.is_hidden():
                continue
            # Adopted members descend from another line — not the head's.
            if m.comment and "приемн" in m.comment.lower():
                continue
            source = _resolve_relative_source(m, head, members_by_num)
            if source is None or not source.person.last_name_modern:
                continue
            # Surnames derive from the male line. A female source (e.g. a
            # widowed female head) can't be masculinized for sons, and her
            # married surname isn't the source of a wife's, so skip.
            if source.person.gender == Gender.FEMALE:
                continue
            src_surname = source.person.last_name_modern
            if is_son:
                p.last_name_modern = src_surname
            elif is_married_woman:
                p.last_name_modern = feminize_surname(src_surname)
                p.last_name_in_book = False
            else:                                 # daughter → maiden name
                p.birth_last_name_modern = feminize_surname(src_surname)


class CensusRecords:
    def __init__(
            self,
            archive: str,
            fund: str,
            inventory: str,
            case: str,
            village: str,
            year: int,
            households: list[CensusHousehold],
            record_day: int | None = None,
            record_month: Month | None = None,
            archive_suffix: str | None = None,
            suffix_in_res_names: bool = False,
            prev_revision_year: int | None = None,
            document_type: str | None = None,
            document_type_genitive: str | None = None,
            district: str | None = None,
            volost: str | None = None,
            reviewed: bool = True,
            household_label: str = "семья",
            household_number_label: str = "№ семьи / № Двора",
            file_prefix: str = "rs",
            doc_res_prefix: str = "census_of_the_family_number",
            single_age_column: bool = False,
            record_type: str = "ревизия",
            female_previous_age: bool | None = None,
    ):
        self.archive = archive
        self.fund = fund
        self.inventory = inventory
        self.case = case
        self.village = village
        self.year = year
        # Cat F: document-type label for the emitted census documents.
        # Defaults (None) to "Ревизская сказка" in the translator. Set it
        # for sources that are not revision tales — e.g. the 1897 First
        # General Census ("1-я всеобщая перепись"). `district` (счётный
        # участок) and `volost` add a descriptive line to the document
        # header block when present.
        self.document_type = document_type
        # Genitive form of `document_type`, used in the member-profile about
        # block's "Комментарий из {…} {year} года" line (Russian requires the
        # genitive after "из"). Falls back to `document_type` then "РС".
        self.document_type_genitive = document_type_genitive
        self.district = district
        self.volost = volost
        # When set, this RS has a known prior revision against which the
        # absence-from-prior heuristic for inferring birth.location is
        # sound: if a male member with current age has no `previous_age`
        # and no `origin`, they were born after the prior RS — and since
        # the family was present in the prior RS, born here. Default
        # None: no inference (safer for first-revision sources like 1717
        # where the heuristic doesn't apply).
        self.prev_revision_year = prev_revision_year
        # Cat B1: default "Дата записи" for the whole census file. Used when
        # a household's own `record_day`/`record_month` is unset. Most CSVs
        # have a single date for all pages, so setting it here is more
        # ergonomic than repeating `day=/month=` on every `page()` call.
        # Per-page `page(..., day=D, month=M)` still wins when present.
        self.record_day = record_day
        self.record_month = record_month
        # Cat D: archive-case suffix to identify this DSL's output file.
        # When set, the translator emits `rs_{year}_{archive_suffix}_1.tf`
        # (matching legacy's per-archive-case file split). When
        # `suffix_in_res_names` is also True, the suffix is appended to
        # every emitted profile's res_name (e.g.
        # `..._family_member_43-6-587-part-1`) so consolidation lookups
        # keyed on that shape match — legacy's rule for res_name suffix
        # inclusion is inconsistent across files, so it's opt-in here.
        self.archive_suffix = archive_suffix
        self.suffix_in_res_names = suffix_in_res_names
        # File-level default for the per-household `reviewed` flag. A
        # household that did not set it explicitly inherits this, so the
        # translator only ever sees a resolved True/False.
        self.reviewed = reviewed
        # ---- Household-source vocabulary -------------------------------
        # A ревизская сказка is not the only document shaped «household →
        # people, relationships stated against the head»: an исповедная
        # роспись is too, and counts «двор» where the revision counts
        # «семья». Rather than subclass, the handful of strings that differ
        # are parameters, and `CONFESSION_LIST` below bundles the ИР's set.
        #
        # EVERY default here is the exact string the translator used to
        # hardcode, because the census `.tf` tree is committed AND applied —
        # changing a rendered document's text force-replaces it on Geni.
        # Read `household_label` for «семья»/«двор» (document title, profile
        # about header, CSV column), `household_number_label` for the doc's
        # own numbering line.
        self.household_label = household_label
        self.household_number_label = household_number_label
        # Output filename (`rs_1834_1.tf` / `ir_1828_1.tf`) AND the document
        # token inside every member profile res_name — the two must agree or
        # the document references resources that were never declared, so
        # they are deliberately one knob rather than two.
        self.file_prefix = file_prefix
        # res_name of the `geni_document` itself.
        self.doc_res_prefix = doc_res_prefix
        # One «Возраст» column instead of the revision's «пред./текущей»
        # pair. Not inferred from "no member carries previous_age": the
        # committed census tree renders `-/56` for exactly that case (284
        # such rows in rs_1762_837-4-5247_1.tf alone), so inferring it would
        # rewrite live documents.
        self.single_age_column = single_age_column
        # Whether the roll writes the previous revision's age for women: from
        # the 1811 revision on it does not, and Verso then offers a new woman
        # no such field. None — the default — reads it off the members
        # (`states_female_previous_age`). Verso's only: the translator does not
        # read it, and it is not part of a record's ratchet fingerprint.
        self.female_previous_age = female_previous_age
        # The label `village.db` stores, which `find_person --type` filters on.
        self.record_type = record_type
        self.households = deepcopy(households)
        for _household in self.households:
            if _household.reviewed is None:
                _household.reviewed = reviewed
        # Auto-assign `record_number` to members in DSL order, matching
        # the legacy CSV's `№ п/п` column. Members may opt out by
        # passing an explicit integer `record_number=` kwarg, which
        # uses that value AND resets the counter to it (so subsequent
        # auto-increments continue from there).
        # Hidden members (`hidden=True`) are placeholders not recorded
        # in the actual revision book — they consume no `№ п/п` slot,
        # so the counter does not advance for them.
        # Without an explicit value, each non-hidden member receives
        # counter + 1.
        record_counter = 0
        for h in self.households:
            if h.record_day is None and record_day is not None:
                h.record_day = record_day
            if h.record_month is None and record_month is not None:
                h.record_month = record_month
            for m in h.members:
                if not m.person.residence:
                    m.person.residence = village
                # Derive gender from role when the person's gender is
                # unset, so RecordDefaults.status_male/status_female can
                # pick the correct default for this member.
                if m.person.gender is None and m.role is not None:
                    implied = ROLE_GENDER.get(m.role)
                    if implied is not None:
                        m.person.gender = implied
                rn = getattr(m, "record_number", None)
                if m.is_hidden():
                    # Hidden members are placeholders not actually in
                    # the revision book — they consume no `№ п/п` slot.
                    # Whatever `record_number` they carry (None or an
                    # explicit override) is preserved verbatim and the
                    # counter does not advance.
                    continue
                if rn is None:
                    record_counter += 1
                    m.record_number = record_counter
                elif isinstance(rn, int):
                    record_counter = rn

    def states_female_previous_age(self) -> bool:
        """Whether the roll writes the previous revision's age for women: as
        `female_previous_age=` says, else as its members do — any woman by
        role with one written. Measured 2026-10-12, that is Глуповы Горы 1782 and
        Горюхино 1795 alone; every roll from 1811 on writes none."""
        if self.female_previous_age is not None:
            return self.female_previous_age
        return any(m.previous_age is not None and ROLE_GENDER.get(m.role) == Gender.FEMALE
                   for h in self.households for m in h.members if m.role is not None)

    def export(self, exporter: RecordsExporter) -> str:
        return exporter.export(self)


@captures_written
def member(number: int, person: Person, role: CensusRole | None, ref_member: int | None = None,
           age: int | str | None = None, previous_age: int | str | None = None, marital_status: str | None = None,
           occupation: str | None = None, origin: str | None = None, destination: str | None = None,
           arrival_year: int | None = None, arrival_reason: str | None = None, departure_year: int | None = None,
           departure_reason: str | None = None, record_number: int | None = None, birth_day: int | None = None,
           birth_month: Month | None = None, birth_year: int | None = None, parent_member: int | None = None,
           father_ref: str | None = None, secondary_role: CensusRole | None = None,
           secondary_ref_member: int | None = None, hidden: bool = False,
           comment: str | None = None, spouse_member: int | None = None,
           source_age_error: str | None = None,
           previous_age_error: str | None = None) -> CensusMember:
    return CensusMember(number, person, role, ref_member, age, previous_age=previous_age, marital_status=marital_status,
                        occupation=occupation, origin=origin, destination=destination, arrival_year=arrival_year,
                        arrival_reason=arrival_reason, departure_year=departure_year, departure_reason=departure_reason,
                        record_number=record_number, birth_day=birth_day, birth_month=birth_month,
                        birth_year=birth_year, parent_member=parent_member, father_ref=father_ref,
                        secondary_role=secondary_role, secondary_ref_member=secondary_ref_member, hidden=hidden,
                        comment=comment, spouse_member=spouse_member,
                        source_age_error=source_age_error,
                        previous_age_error=previous_age_error)


@captures_written
def household(family_id: str | None, *members: CensusMember, page: str | None = None, comment: str | None = None,
              record_day: int | None = None, record_month: Month | None = None,
              reviewed: bool | None = None) -> CensusHousehold:
    return CensusHousehold(family_id=family_id, members=list(members), page=page, comment=comment,
                           record_day=record_day, record_month=record_month, reviewed=reviewed)


@captures_written
def census_records(
        archive: str,
        fund: str,
        inventory: str,
        case: str,
        village: str,
        year: int,
        *households: CensusHousehold,
        record_day: int | None = None,
        record_month: Month | None = None,
        archive_suffix: str | None = None,
        suffix_in_res_names: bool = False,
        prev_revision_year: int | None = None,
        document_type: str | None = None,
        document_type_genitive: str | None = None,
        district: str | None = None,
        volost: str | None = None,
        reviewed: bool = True,
        household_label: str = "семья",
        household_number_label: str = "№ семьи / № Двора",
        file_prefix: str = "rs",
        doc_res_prefix: str = "census_of_the_family_number",
        single_age_column: bool = False,
        record_type: str = "ревизия",
        defaults: RecordDefaults | None = None,
        female_previous_age: bool | None = None,
) -> CensusRecords:
    records = CensusRecords(
        archive, fund, inventory, case, village, year, list(households),
        record_day=record_day, record_month=record_month,
        archive_suffix=archive_suffix, suffix_in_res_names=suffix_in_res_names,
        prev_revision_year=prev_revision_year,
        document_type=document_type,
        document_type_genitive=document_type_genitive,
        district=district, volost=volost, reviewed=reviewed,
        household_label=household_label,
        household_number_label=household_number_label,
        file_prefix=file_prefix, doc_res_prefix=doc_res_prefix,
        single_age_column=single_age_column, record_type=record_type,
        female_previous_age=female_previous_age,
    )
    if defaults is not None:
        for h in records.households:
            for m in h.members:
                defaults.apply_to_person(m.person)
    return records


class ConfessionListVocabulary(TypedDict):
    """The parameter set that turns `census_records()` into an исповедная
    роспись. Spelled as a TypedDict so `**CONFESSION_LIST` type-checks at the
    call site instead of degrading to `Any`."""

    document_type: str
    document_type_genitive: str
    household_label: str
    household_number_label: str
    file_prefix: str
    doc_res_prefix: str
    single_age_column: bool
    record_type: str


# Исповедная роспись — the parish's own yearly census: every двор, everybody
# in it, and an age stated fresh each year rather than carried forward from a
# previous revision. Structurally identical to a ревизская сказка, so it is
# the same `census_records()` under a different vocabulary:
#
#     census = census_records(
#         "ГАРО", "735", "265", "53", "Заманиловка", 1828,
#         *page("80", household("94", ...)),
#         **CONFESSION_LIST,
#         record_month=Month.MARCH,      # ИР is taken during Great Lent
#     )
#
# `file_prefix="ir"` is what keeps an ИР and a ревизская сказка of the same
# year from colliding — separate output file and separate profile res_names.
#
# ⚠ An ИР age is evidence, not arithmetic. A revision tale copies ages
# forward so the two columns cross-check; a priest wrote the ИР age down each
# spring and it drifts by years. Never correct a metric-book birth year
# against an ИР.
CONFESSION_LIST: ConfessionListVocabulary = {
    "document_type": "Исповедная роспись",
    "document_type_genitive": "исповедной росписи",
    "household_label": "двор",
    "household_number_label": "№ двора",
    "file_prefix": "ir",
    "doc_res_prefix": "confession_of_the_household_number",
    "single_age_column": True,
    "record_type": "исповедная роспись",
}
