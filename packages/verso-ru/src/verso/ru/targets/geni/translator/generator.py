"""TerraformGenerator: the DSL-record to Terraform-resource engine."""
import copy
import re
from calendar import Month
from collections import defaultdict
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any
if TYPE_CHECKING:
    pass
from verso.ru.ages import birth_notes, format_age, parent_age_prose
from verso.ru.domain.event_date import EventDate
from verso.ru.dsl.records.reviewed import admitted
from verso.ru.naming.transliteration import generate_res_name
from verso.ru.gender import Gender
from verso.core.targets.geni.date import GeniDate
from verso.core.targets.geni.consolidation_conflicts import detect_consolidation_conflicts
from verso.core.targets.geni.event import GeniEvent
from verso.core.targets.geni.profile import GeniProfile
from verso.core.targets.geni.redundant_ignores import (
    collect_redundant_ignores, matches_ignore)
from verso.core.targets.geni.redundant_additional_info import (
    RedundantAdditionalInfo, detect_redundant_additional_info, snapshot as snapshot_additional_info_fields)
from verso.core.targets.geni.redundant_overrides import (
    OVERRIDE_TRACKED_FIELDS, detect_redundant_overrides)
from verso.core.targets.geni.redundant_preferences import (
    PREFERENCE_PINNED_FIELDS, RedundantPreference, collect_redundant_preferences, pin_is_dead)
from verso.core.targets.geni.union import GeniUnion, UnionOrigin
from verso.core import places
from verso.ru.naming import feminize_surname, genitive_person_name
from verso.ru.relationship import Relationship
from verso.core.targets.geni.about import strip_section_date_markers
from verso.ru.targets.geni.translator.about_sections import _sort_about_sections, inject_section_date_marker
from verso.ru.targets.geni.translator.birth_estimates import PARENT_RELATIONSHIP_GENDER, adult_birth_window, is_parent_relationship, parent_birth_estimate
from verso.ru.targets.geni.translator.census_resolvers import _age_to_years, _birth_date_from_age, _resolve_arrival_reason, _resolve_arrival_year, _resolve_departure_reason, _resolve_departure_year, _resolve_destination, _resolve_parent_ref, resolve_display_role, resolve_previous_age_raw
from verso.ru.targets.geni.translator.member_birth import member_birth as derive_member_birth, withheld_member_birth
from verso.ru.targets.geni.translator.comments import _comment_for_unions, _mk_doc_name_line, _name_in_document, _names_in_mk, _shallow_person_without_patr
from verso.ru.targets.geni.translator.consolidation import Consolidation
from verso.ru.targets.geni.translator.res_names import _build_subfamily_union_res_name, _location, generate_res_name_2, location_label
from verso.ru.targets.geni.translator.resources import CONSOLIDATED_PROFILES_CHUNK, GENDER_TF, _document_resource, _event
from verso.ru.targets.geni.translator.sorting import _chronological_key, _month_num


def _format_event_date(ev: EventDate | None) -> str:
    """Render an EventDate as a compact `D.M.YYYY` string for display in a
    document description; range bounds are joined with an en-dash. Returns ""
    when no date is set."""
    if ev is None:
        return ""

    def _point(d: int | None, m: Month | None, y: int | None) -> str:
        return ".".join(str(x) for x in (d, m.value if m else None, y) if x)

    start = _point(ev.day, ev.month, ev.year)
    if ev.has_range:
        end = _point(ev.day_end, ev.month_end, ev.year_end)
        if end:
            return f"{start}–{end}"
    return start


# Scan file extension → geni_document content_type. The provider regex accepts
# image/jpg|png|tif and application/pdf (note: image/jpg, NOT image/jpeg).
_SCAN_CONTENT_TYPES = {
    "jpg": "image/jpg", "jpeg": "image/jpg",
    "png": "image/png",
    "tif": "image/tif", "tiff": "image/tif",
    "pdf": "application/pdf",
}


def _scan_content_type(path: str) -> str:
    """Derive a geni_document content_type from a scan file's extension,
    defaulting to image/jpg for unknown/extensionless paths."""
    ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
    return _SCAN_CONTENT_TYPES.get(ext, "image/jpg")


def _is_civil(records) -> bool:
    """A book of the civil registry (ЗАГС, `civil=True`): its entries register an event —
    the second date of a birth or a death is the registration, never a christening or a
    burial, and a marriage is its registration."""
    return bool(getattr(records, "civil", False))


def _book_title(records) -> str:
    """What a document calls its book: a parish metric book, or a civil registry's."""
    return "Книга ЗАГС" if _is_civil(records) else "Метрическая книга"


def _book_tag(records) -> str:
    """The short form an about section opens with: «МК», or «ЗАГС» for a civil book."""
    return "ЗАГС" if _is_civil(records) else "МК"


def _burial_event(d, *, year: int | None, death_month: int | None,
                  location) -> GeniEvent | None:
    """The burial a часть-3 entry records beside the death, as a profile event.

    `b_day`/`b_month` are the BURIAL in a death record, and until 2026-09-25
    they reached nothing but the CSV exporters: 3198 of the corpus's 3466
    burials differ from the death date. The day must be written — a month the
    `death_month` section filled in alone dates nothing the death does not.
    A burial the author withdrew (`death(source_date_error=)` — «погребёнъ 8,
    умеръ 9 — так в подлиннике») is not emitted, as `verso.ru.facts` withdraws
    it. The one crossing a book writes without a year is a December death
    buried in January: the burial belongs to the next year. Placed at the
    parish, whose cemetery it was.
    """
    if d.b_day is None or year is None or getattr(d, "source_date_error", None):
        return None
    month = _month_num(d.b_month)
    if month is None:
        month = death_month
    if month is None:
        return None
    burial_year = year + 1 if death_month == 12 and month == 1 else year
    return _event(day=d.b_day, month=month, year=burial_year, location=location)


#: How a death record's named relative positions the DECEASED.
#:
#: A часть-3 entry names one relative to identify the dead person — «жена
#: Гавриила», «дочь Ивана» — so that phrase is the entire evidence for the
#: link. The rule used to be a single bit (`rel_type == "муж"`: spouse,
#: everything else: the relative is the deceased's PARENT), which turned a
#: мачеха into a mother, a приемный отец into a father, a свекор into a father
#: and a зять into his own parent-in-law's father.
#:
#: A kinship absent here yields NO union. That is the asymmetry that decides
#: it: a missing edge is recoverable from any other record naming the same
#: people, while a false one has to be noticed first — and it looks exactly
#: like a true one. Geni's own parent modifiers are bio/adopt/foster, so a
#: мачеха has nowhere to go: she is her stepchild's father's wife, and the
#: child belongs in that father's union, which the death record does not name.
_DEATH_EDGE: dict[Relationship, str] = {
    Relationship.HUSBAND: "spouse",
    Relationship.WIFE: "spouse",
    Relationship.FATHER: "child",
    Relationship.MOTHER: "child",
    Relationship.FOSTER_FATHER: "foster",
    Relationship.FOSTER_MOTHER: "foster",
}


class TerraformGenerator:
    def __init__(self, village_dir=None, consolidation: Consolidation | None = None,
                 projects: list[str] | None = None,
                 extra_project_rules: dict[str, str] | None = None,
                 prev_revision: Mapping[int, int | None] | None = None):
        self.village_dir = village_dir
        # The village's exceptions to the revision chain a roll's previous ages are
        # dated by (village.toml `[census] prev_revision`, `census_revisions`).
        self.prev_revision: Mapping[int, int | None] = prev_revision or {}
        self.consolidation = consolidation or Consolidation()
        self.projects = projects or []
        # Substring → project-id rules applied to emitted profiles (and
        # geni_document resources) based on the subject's residence / event
        # location. Matches the earlier generator's pattern where
        # `'Неелов' in location` appended `data.geni_project.neelovo.id`.
        self.extra_project_rules = extra_project_rules or {}
        self._outputs: dict[str, str] = defaultdict(str)
        # Domain-object registries: every profile/union emitted DIRECTLY (i.e.
        # not diverted into the consolidated bucket) is also retained here as
        # its `GeniProfile` / `GeniUnion` object, keyed by res_name. This lets
        # downstream projections (e.g. the familio translator) read the
        # translated domain model instead of re-parsing the DSL or scraping the
        # rendered HCL. Purely additive — it does NOT affect `_outputs`, so the
        # geni `.tf` output stays byte-identical. Consolidated canonicals live
        # in `_consolidated_profiles` / `_consolidated_unions`; `canonical_*()`
        # exposes the merged view.
        self._profile_registry: dict[str, GeniProfile] = {}
        self._union_registry: dict[str, GeniUnion] = {}
        # Which res_name this run minted for each DSL `Person` OBJECT, keyed by
        # identity (Person is a plain class, so two same-named people are two
        # keys). Additive in the same sense as the registries above: written
        # beside the res_name, read by nobody in this module, and it cannot move
        # a byte of `_outputs`.
        #
        # It exists so `verso.ru.facts` can answer «which consolidated person is
        # this appearance» without either of the two bad options: reconstructing
        # a res_name duplicates the naming policy in `_profile_from_person`
        # (which of `last_name` / `birth_last_name` goes in depends on the
        # role), and parsing one back would be the sixth such parser in this
        # repository. The object that both sides already hold is the join key,
        # and it needs no vocabulary at all.
        #
        # `_minted_twice` counts the appearances that got a SECOND profile, so a
        # bridge built on this can report its own ambiguity instead of silently
        # taking the last write.
        self._minted_for_person: dict[object, str] = {}
        self._minted_twice: list[tuple[str, str]] = []
        # Every res_name minted for one appearance — what a per-record stub
        # is, until a fold names it a canonical (`_add_to_consolidated_unions`).
        self._minted_res_names: set[str] = set()
        # The about SECTION each appearance's profile was minted with, by the
        # same DSL `Person` object — the text a canonical's about is folded
        # together from. Once folded it survives only inside that joined
        # string, so a reader holding the appearance (the familio projection,
        # through the facts bridge) would have to cut the narrative apart
        # again to find it. Additive like `_minted_for_person`: nothing reads
        # it here, and no generated byte depends on it.
        self._section_for_person: dict[object, str] = {}
        # The geni_document each record emitted, by the DSL record OBJECT —
        # what the review ratchet seeds from (`verso.ru.cli.review_ratchet`): a
        # record is on Geni when its document is in terraform state, and a
        # document is never folded, so it names its record alone. Additive
        # like `_minted_for_person`: nothing here reads it.
        self._document_for_record: dict[object, str] = {}
        # The birth date each emitted profile carried INTO the fold, by the
        # res_name it was emitted under, one entry per emission — the value a
        # `birth.date` ignore entry is compared with in `_emit_profile` and
        # `_merge_consolidated`. Additive like `_minted_for_person`: read by
        # nobody in this module. A snapshot rather than a reference, because a
        # canonical seeded from a profile shares that profile's event objects,
        # so a later merge could otherwise change what the record is said to
        # have derived.
        self._emitted_births: dict[str, list[GeniDate | None]] = {}
        # Dates a retraction (`source_age_error` / `previous_age_error`)
        # withheld, by the res_name that would have carried them, with the
        # kwarg that did it — RIG001 names an `ignore` that repeats one.
        self._withheld_births: dict[str, list[tuple[GeniDate, str]]] = {}
        # The DSL containers this run was fed, in feed order, as
        # (source filename, records object). A caller that wants to read the
        # SAME objects the translation read — which is what makes the
        # appearance a join key at all — must be handed them rather than
        # rediscover them, because a second discovery builds a second set of
        # objects that are equal and not identical.
        self.fed_sources: list[tuple[str, object]] = []
        # Which output file each registered union was written into, so
        # `_route_union` can merge a second build of the same union
        # instead of appending a duplicate `resource` block.
        self._union_files: dict[str, str] = {}
        self._consolidated_profiles: dict[str, GeniProfile] = {}
        # Field values silently dropped while folding per-record profiles into
        # a consolidated canonical (see `consolidation_conflicts`). Surfaced as
        # warnings by `generate_tf.py`.
        self.consolidation_conflicts = []
        # ROV001: `override` fields that set a value the profile already had.
        # Recorded by `_apply_profile_overrides`; surfaced by generate_tf.
        self.redundant_overrides = []
        # RIG001: `(canonical, index)` of every ignore entry actually
        # consulted-and-matched. Entries missing from this set never fired.
        self._ignore_seen: set[tuple[str, int]] = set()
        self.redundant_ignores = []
        # RPF001: `(canonical, field)` of every preference pin that did work
        # no other layer would have done — today only the `birth_last_name`
        # conflict-silencing path. The seed pin is judged separately, by
        # comparing against the value the field would hold WITHOUT it.
        self._preference_seen: set[tuple[str, str]] = set()
        # `(canonical, field)` -> the value the seeding record carried BEFORE
        # any pin, for every pinnable name field whether pinned or not. A pin
        # equal to it wrote nothing at all, which is the whole of RPF001's
        # claim: the seed profile is then identical with and without the pin,
        # so nothing computed from it can differ. The unpinned fields are what
        # lets the conflict report's suggestion leave out a pin RPF001 would
        # reject (`preference_pin_is_dead`).
        self._preference_seed_before: dict[tuple[str, str], Any] = {}
        # Canonicals a record actually seeded. A preference on a canonical no
        # record reaches never ran at all; that is CST001's finding, not
        # RPF001's, so it must not be reported twice.
        self._seeded_canonicals: set[str] = set()
        self.redundant_preferences: list[RedundantPreference] = []
        # RAI001: `additional_info` entries whose merge changed no field.
        self.redundant_additional_info: list[RedundantAdditionalInfo] = []
        # canonical -> override fields that SILENCED a consolidation conflict
        # (`resolved_by_override`). Such an override is load-bearing even when
        # its value is a no-op, so ROV001 must not report it.
        self._override_suppressed_fields: dict[str, set[str]] = defaultdict(set)
        # Per-target list of source res_names that fold into each
        # consolidated profile. Populated during `_emit_profile`. Drives
        # the `# Consolidated profile with merged profiles:` header
        # emitted above each profile in `consolidated_profiles_*.tf`.
        self._consolidated_profiles_sources: dict[str, list[str]] = {}
        # Fix #1: unions whose participant is consolidated get routed here
        # and emitted to `consolidated_unions.tf` in `finalize()`. Keyed by
        # the target consolidated res_name; entries are `GeniUnion` with
        # children-sets merged across source unions.
        self._consolidated_unions: dict[str, GeniUnion] = {}
        # Partner-profile name → target consolidated-union res_name. Used so
        # a later union sharing a partner with an already-consolidated union
        # finds the same target and merges in (legacy
        # `partner_profile_to_union_map` behavior).
        self._partner_to_consolidated_union: dict[str, str] = {}
        # Per-target list of source unions (snapshots taken at the moment
        # the union was passed to `_add_to_consolidated_unions`). Used in
        # `finalize()` to emit the legacy
        # `# Consolidated union with merged unions:\n# - {src} (...)`
        # documentation header above each consolidated union resource.
        self._consolidated_unions_sources: dict[str, list[GeniUnion]] = {}

    def _is_other_parish(self, records) -> bool:
        """Cat A1: True when these records belong to a non-main parish and
        should land in `mk_YEAR_other_*.tf` instead of `mk_YEAR_*.tf`.
        The flag is set by the caller (e.g. `generate_tf.py` based on
        DSL filename prefix `other_`) — explicit marker rather than
        inferred from village/church, because records from secondary
        villages in the SAME parish (the parish's other villages) must stay
        in the main per-year file."""
        return bool(getattr(records, "_other_parish", False))

    def _projects_for_location(self, location_name: str | None) -> list[str]:
        """Return the project list for a profile whose associated location
        is `location_name`. Starts from the base `self.projects` and adds
        any `extra_project_rules` whose substring key is found in the name
        OR in the expanded location string (legacy checks the full
        `locations[key]` body, which contains county/state with e.g.
        'Нееловская волость').

        Returns the union sorted alphabetically — matches the earlier generator's
        consolidator output (`sorted(list(set(...)))`) and keeps non-consolidator
        emit sites consistent with consolidator-merged profiles (which already
        sort)."""
        if not location_name:
            return sorted(set(self.projects))
        expanded = places.current().bodies.get(location_name, "")
        haystack = f"{location_name} {expanded}"
        extras = [pid for key, pid in self.extra_project_rules.items() if key in haystack]
        return sorted(set(self.projects) | set(extras))

    def _emit_profile(self, filename: str, profile: GeniProfile,
                      consolidated_enrichment: dict[str, Any] | None = None) -> None:
        """Emit a profile. If its res_name is in the consolidation move list,
        divert it into the consolidated bucket (keyed by the target name) and
        apply any `consolidated_enrichment` — role-specific fields (about,
        death range, residence) that the legacy pipeline attaches on
        consolidation but not on per-record profiles.

        On the first encounter of a consolidated name, a fresh copy of the
        profile (with enrichment applied) is stored. On subsequent encounters,
        the new profile's fields are MERGED into the stored one — matching the
        legacy `add_to_consolidated_profiles` aggregation semantics:
          * `death.date.year` (for `date_range="after"`) takes the max;
          * `about` text is appended, separated by a blank line;
          * `current_residence` is last-write-wins.
        """
        self._emitted_births.setdefault(profile.res_name, []).append(
            copy.deepcopy(profile.birth.date) if profile.birth is not None else None)
        if self.consolidation.in_profile_move_list(profile.res_name):
            new_name = self.consolidation.move_to_new_name(profile.res_name)
            incoming = copy.copy(profile)
            incoming.res_name = new_name
            if consolidated_enrichment:
                for attr, value in consolidated_enrichment.items():
                    setattr(incoming, attr, value)
            pref = self.consolidation.profile_preferences.get(new_name)
            ignore = self.consolidation.profile_ignores.get(new_name)
            if profile.res_name != new_name:
                self._consolidated_profiles_sources.setdefault(
                    new_name, [],
                ).append(profile.res_name)
            if new_name not in self._consolidated_profiles:
                self._seeded_canonicals.add(new_name)
                for key in PREFERENCE_PINNED_FIELDS:
                    self._preference_seed_before[(new_name, key)] = getattr(
                        incoming, key, None)
                if pref:
                    self._apply_preference(incoming, pref)
                # When seeding the consolidated entry, scrub any
                # attribute whose value matches an ignore entry — so a
                # later non-ignored variant can fill it in. Otherwise a
                # per-record stub processed first (e.g. ivan_petrovich
                # <year>) would pin the ignored value forever.
                if ignore:
                    for attr in ("first_name", "middle_name", "last_name",
                                 "birth_last_name"):
                        val = getattr(incoming, attr, None)
                        if val and matches_ignore(
                                attr, val, ignore,
                                seen=self._ignore_seen, canonical=new_name):
                            setattr(incoming, attr, "")
                    # The same for an event date: a seed whose date the
                    # config declares wrong would otherwise stand as the
                    # canonical's date no merge can remove.
                    for event_name in ("birth", "death", "baptism", "burial"):
                        event = getattr(incoming, event_name, None)
                        if (event is not None and event.date is not None
                                and matches_ignore(
                                    f"{event_name}.date", event.date, ignore,
                                    seen=self._ignore_seen, canonical=new_name)):
                            setattr(incoming, event_name,
                                    GeniEvent(location=event.location)
                                    if event.location else None)
                # Sort projects alphabetically. The earlier generator
                # always wrapped the
                # merged list in `sorted(list(set(...)))`. The seed
                # profile's per-record order would otherwise survive
                # untouched when no merge fires.
                if incoming.projects:
                    incoming.projects = sorted(set(incoming.projects))
                self._consolidated_profiles[new_name] = incoming
            else:
                existing_consolidated = self._consolidated_profiles[new_name]
                # Detect (pure query) before merging (command): record any
                # value the merge is about to silently drop.
                override = self.consolidation.profile_overrides.get(new_name)
                conflicts = detect_consolidation_conflicts(
                    existing_consolidated, incoming,
                    canonical=new_name, source=profile.res_name,
                    preference=pref, ignore=ignore, override=override,
                    ignore_seen=self._ignore_seen,
                    preference_seen=self._preference_seen,
                )
                self.consolidation_conflicts.extend(conflicts)
                if override is not None:
                    # Which conflicts does the override silence? Re-running the
                    # same pure query without it is cheap and is the only
                    # honest way to tell a dead override from one whose whole
                    # job is marking a source disagreement resolved (ROV001).
                    unresolved = detect_consolidation_conflicts(
                        existing_consolidated, incoming,
                        canonical=new_name, source=profile.res_name,
                        preference=pref, ignore=ignore, override=None,
                        ignore_seen=self._ignore_seen,
                    )
                    silenced = ({c.field for c in unresolved}
                                - {c.field for c in conflicts})
                    # Conflict fields are dotted ("birth.date"); override
                    # fields are their roots ("birth").
                    self._override_suppressed_fields[new_name].update(
                        field.split(".")[0] for field in silenced)
                self._merge_consolidated(existing_consolidated, incoming,
                                         preference=pref, ignore=ignore,
                                         ignore_seen=self._ignore_seen,
                                         canonical=new_name)
            return
        self._profile_registry[profile.res_name] = profile
        self._outputs[filename] += profile.to_terraform()

    def _apply_profile_overrides(self) -> None:
        """Apply per-target `override` hints to consolidated profiles.

        Overrides UNCONDITIONALLY replace fields on the consolidated
        profile (unlike preference, which only pins on conflict).
        Mirrors the earlier generator:
        - first_name / middle_name / last_name / birth_last_name /
          current_residence / occupation: set to override value when
          override carries one.
        - nicknames: REPLACE existing.nicknames with override.nicknames
          (the earlier generator's `existing.nicknames = override.nicknames`).
          Append-and-sort would let merge-time leakage of the canonical
          name persist as a self-referential nickname.
        - birth / death / baptism / burial: replace whole event.
        """
        for target, override in self.consolidation.profile_overrides.items():
            profile = self._consolidated_profiles.get(target)
            if profile is None:
                continue
            # Deep copy: events are mutated IN PLACE below, so a shallow
            # snapshot would compare an object with itself and never report.
            before = {
                field: copy.deepcopy(getattr(profile, field, None))
                for field in OVERRIDE_TRACKED_FIELDS
                if getattr(override, field, None)
            }
            for key in ("first_name", "middle_name", "last_name",
                        "birth_last_name", "current_residence", "occupation"):
                value = getattr(override, key, None)
                if value:
                    setattr(profile, key, value)
            override_nicknames = getattr(override, "nicknames", None)
            if override_nicknames:
                profile.nicknames = list(override_nicknames)
            # Strip self-referential nicknames — values matching the
            # canonical first_name / middle_name / last_name (whether
            # set by override or seeded from the per-record). Mirrors
            # legacy: it never emitted a nickname equal to the
            # canonical name field.
            if profile.nicknames:
                canonicals = {
                    profile.first_name,
                    profile.middle_name,
                    profile.last_name,
                    profile.birth_last_name,
                }
                profile.nicknames = [
                    n for n in profile.nicknames
                    if n and n not in canonicals
                ]
            # Event overrides: the earlier generator only replaces the existing event's
            # `.date` and `.location` separately when override carries
            # them — preserving the other side. So `override.birth =
            # GeniEvent(date=...)` (no location) keeps the previously-
            # merged location intact rather than wiping the whole event.
            for event_name in ("birth", "death", "baptism", "burial"):
                override_event = getattr(override, event_name, None)
                if override_event is None:
                    continue
                existing_event = getattr(profile, event_name, None)
                if existing_event is None:
                    setattr(profile, event_name, override_event)
                    continue
                if override_event.date is not None:
                    existing_event.date = override_event.date
                if override_event.location is not None:
                    existing_event.location = override_event.location
            # about: APPEND override.about to existing.about with a
            # `\n        ` separator (as the earlier generator did). Used to attach
            # genealogical metadata like rgfond.ru links and free-form
            # date estimates. Previously dropped on the floor.
            override_about = getattr(override, "about", None)
            if override_about:
                if profile.about:
                    # Blank line separates the override appendix from the
                    # merged RS/MK sections; matches how Geni renders the
                    # existing notes as a distinct paragraph. Strip any
                    # trailing whitespace from the merged about first so
                    # multi-section profiles (whose last section ends in
                    # `\n`) get exactly one blank line, not two.
                    profile.about = profile.about.rstrip() + "\n\n        " + override_about
                else:
                    profile.about = override_about
            # ROV001: compare each override-touched field against its
            # pre-application snapshot. Runs last so every mutation above
            # (including the self-referential nickname strip) is accounted for.
            self.redundant_overrides.extend(detect_redundant_overrides(
                target, before,
                {field: getattr(profile, field, None) for field in before},
                suppressed_fields=self._override_suppressed_fields.get(
                    target, frozenset()),
            ))

    @staticmethod
    def _apply_preference(profile: GeniProfile, pref: dict[str, Any]) -> None:
        """Pin `profile`'s preference-tracked fields to the configured
        canonical values, and pre-populate `nicknames` with all declared
        preference variants. Pre-populating is a deliberate config-level
        decision: declared variants are historical aliases worth
        preserving even when not encountered in the current corpus
        (e.g. ivan_ilich_sidorov's `Ильинич` only shows up
        in source CSV columns the per-record importer normalizes away).

        Whether a pin changes anything is decided by the value the seed
        carried before it, which `_emit_profile` records for RPF001 — see
        `verso.core.targets.geni.redundant_preferences`.
        """
        for key in PREFERENCE_PINNED_FIELDS:
            if pref.get(key):
                setattr(profile, key, pref[key])
        if pref.get("nicknames"):
            existing_nicks = list(profile.nicknames or [])
            for nick in pref["nicknames"]:
                if nick and nick not in existing_nicks:
                    existing_nicks.append(nick)
            # Legacy sorts nicknames alphabetically via
            # `sorted(list(set(existing.nicknames + [...])))`.
            profile.nicknames = sorted(existing_nicks)

    @staticmethod
    def _merge_consolidated(existing: GeniProfile, incoming: GeniProfile,
                            *, preference: dict[str, Any] | None = None,
                            ignore: list[dict[str, Any]] | None = None,
                            ignore_seen: set[tuple[str, int]] | None = None,
                            canonical: str | None = None) -> None:
        """Merge `incoming` into `existing` in place, mirroring the subset of
        legacy `add_to_consolidated_profiles` aggregation that per-record
        profiles exercise today: fill-in-if-missing for name fields,
        cause_of_death, and projects; event dates picked by precedence
        (specific > circa > range); event locations filled when missing;
        about → blank-line-separated concatenation; current_residence →
        last-write-wins.

        When `preference` is supplied, the consolidated target's canonical
        first_name / middle_name / last_name stays pinned and any
        incoming variant that matches a declared nickname is added to
        `existing.nicknames` instead of overwriting.
        """
        # A source's own date inconsistency belongs to whichever record
        # carried it, so it must survive consolidation — otherwise folding the
        # record into a canonical makes `verso date-order` start reporting an
        # already-acknowledged scribal slip again.
        if not existing.source_date_error and incoming.source_date_error:
            existing.source_date_error = incoming.source_date_error

        # birth / death / baptism / burial: merge event-by-event via
        # shared helper. Legacy `compare_events` covers all four;
        # previously only
        # birth+death were merged here, silently dropping baptism and
        # burial events from incoming per-records (e.g. the baptism
        # from an early birth record disappearing when the child was
        # consolidated with a later RS family-member encounter).
        for event_name in ("birth", "death", "baptism", "burial"):
            incoming_event = getattr(incoming, event_name, None)
            # An ignored date is dropped from the merge, as an ignored name
            # is — not merely left out of the conflict report. Otherwise a
            # date the config has declared wrong still widens the canonical's
            # range through `_pick_best_date`, and the only way to keep it out
            # was an `override`, which also silences every later conflict.
            if (incoming_event is not None and incoming_event.date is not None
                    and matches_ignore(f"{event_name}.date", incoming_event.date,
                                       ignore, seen=ignore_seen,
                                       canonical=canonical)):
                incoming_event = (GeniEvent(location=incoming_event.location)
                                  if incoming_event.location else None)
            if incoming_event is not None:
                merged = TerraformGenerator._merge_event(
                    getattr(existing, event_name, None), incoming_event,
                )
                setattr(existing, event_name, merged)

        # about: concatenate across records, separated by a blank line,
        # with a trailing newline on each section. Legacy appends '\n'
        # at the end of every merged about section, which produces a
        # blank line before `EOT` on the last one. Skip if incoming
        # text is already present (idempotent on repeats).
        if incoming.about:
            if not existing.about:
                existing.about = incoming.about + "\n"
            elif incoming.about not in existing.about:
                # Subsequent about-sections need the same 8-space indent
                # that `GeniProfile.to_terraform` prefixes on the first
                # line inside the `trimspace(<<-EOT ...)` block so the
                # merged output stays aligned when rendered.
                existing.about = (
                    existing.about.rstrip("\n")
                    + "\n\n" + " " * 8 + incoming.about + "\n"
                )

        # current_residence: last-write-wins (the most recent record's
        # residence is the freshest datum).
        if incoming.current_residence:
            existing.current_residence = incoming.current_residence

        # occupation: fill-in-if-missing. Only a card or a roll states one,
        # and the canonical is seeded by whichever record folds first — often
        # a birth record, which has none.
        if not existing.occupation and incoming.occupation:
            existing.occupation = incoming.occupation

        # Fill-in-if-missing for name fields. Legacy's
        # `add_to_consolidated_profiles` accepts the first non-empty value
        # as the consolidated value.
        # When DSL records disagree between records (e.g. only the later
        # encounter has `last_name_modern`), carry the non-empty variant.
        # First-name variants that differ from the canonical form land in
        # `nicknames` — legacy tracks every orthographic/canonical variant
        # seen across a person's records and emits them as nicknames. With
        # a preference entry pinning the canonical form, the pinned value
        # stays as first_name and the incoming variant is added to
        # nicknames (matching legacy's `in_preference_nicknames` path).
        pref_first = (preference or {}).get("first_name")
        pref_nicknames = (preference or {}).get("nicknames") or []
        # `ignore` is a list of dicts with attr→value entries declared
        # in the consolidation config (`profiles_to_consolidate[target]
        # ['ignore']`). When an incoming attribute matches an ignored
        # value, the merge silently drops the variant — neither overwrites
        # the canonical nor adds it to nicknames. Mirrors the earlier generator.
        ignore = ignore or []

        def _is_ignored(attr: str, value) -> bool:
            return matches_ignore(attr, value, ignore,
                                  seen=ignore_seen, canonical=canonical)

        def _add_nickname_if_in_preference(value):
            """Add `value` to existing.nicknames iff it's one of the
            preference's declared nickname variants. Mirrors the earlier
            generator — preference nicknames
            are only realized when an incoming per-record actually
            carries them. Returns True if added (to skip "differs from
            canonical" error paths)."""
            if value and value in pref_nicknames:
                existing_nicks = list(existing.nicknames or [])
                if value not in existing_nicks:
                    existing_nicks.append(value)
                    existing.nicknames = sorted(existing_nicks)
                return True
            return False

        # `"?"` is the DSL's placeholder for an unknown / unreadable name
        # (e.g. damaged page rendered as `person("?", ...)`). Legacy
        # promotes the non-"?"
        # name unconditionally and never adds "?" to nicknames.
        if (incoming.first_name
                and not _is_ignored("first_name", incoming.first_name)
                and existing.first_name
                and incoming.first_name != existing.first_name):
            if existing.first_name == "?" and incoming.first_name != "?":
                existing.first_name = incoming.first_name
            elif incoming.first_name == "?":
                pass  # keep existing real name; don't add "?" to nicknames
            else:
                existing_nicks = list(existing.nicknames or [])
                if incoming.first_name not in existing_nicks:
                    existing_nicks.append(incoming.first_name)
                    existing.nicknames = sorted(existing_nicks)
                # Keep pinned canonical: if we have a preference and
                # existing already matches it, don't overwrite with the
                # incoming variant.
                if pref_first and existing.first_name == pref_first:
                    pass  # leave existing untouched; incoming was the alt

        # middle_name: skip incoming when ignored, OR add to nicknames
        # when it matches a declared preference nickname.
        if (incoming.middle_name and existing.middle_name
                and incoming.middle_name != existing.middle_name):
            if _is_ignored("middle_name", incoming.middle_name):
                pass  # honor ignore: drop the variant
            else:
                _add_nickname_if_in_preference(incoming.middle_name)

        # last_name: when existing.last_name == incoming.birth_last_name,
        # the existing value is the maiden form and incoming is the married
        # form — adopt the married name, as the earlier generator did.
        # Otherwise: when an incoming
        # variant matches a declared preference nickname, add it to
        # nicknames.
        if (incoming.last_name
                and not _is_ignored("last_name", incoming.last_name)
                and existing.last_name
                and existing.last_name != incoming.last_name):
            if existing.last_name == incoming.birth_last_name:
                existing.last_name = incoming.last_name
            else:
                _add_nickname_if_in_preference(incoming.last_name)

        # birth_last_name variants → nicknames if in preference.
        if (incoming.birth_last_name
                and not _is_ignored("birth_last_name", incoming.birth_last_name)
                and existing.birth_last_name
                and incoming.birth_last_name != existing.birth_last_name):
            _add_nickname_if_in_preference(incoming.birth_last_name)

        # Explicit incoming.nicknames — merge into existing as a sorted, deduped
        # union. Mirrors the earlier generator. The
        # path that picks up `profiles_to_consolidate[*]['additional_info']`
        # entries like `GeniProfile(nicknames=["Сундукина"])`. Without this,
        # explicit nicknames declared in additional_info are silently dropped
        # and Geni-side nicknames get cleared on next apply.
        if incoming.nicknames:
            existing_nicks = list(existing.nicknames or [])
            added = False
            for n in incoming.nicknames:
                if n not in existing_nicks:
                    existing_nicks.append(n)
                    added = True
            if added:
                existing.nicknames = sorted(existing_nicks)
            elif not existing.nicknames:
                existing.nicknames = list(incoming.nicknames)

        for attr in ("first_name", "middle_name", "last_name",
                     "birth_last_name", "cause_of_death"):
            if (getattr(incoming, attr, None)
                    and not getattr(existing, attr, None)
                    and not _is_ignored(attr, getattr(incoming, attr))):
                setattr(existing, attr, getattr(incoming, attr))

        # projects: union across encounters — any per-record project rule
        # that matched on one encounter applies to the consolidated profile.
        # Legacy sorts the merged union when the two source lists differ
        # (`sorted(list(set(existing.projects + profile.projects)))`); apply
        # the same sort here only when the merge actually adds a new
        # project, preserving the unsorted source order on no-op merges.
        if incoming.projects:
            existing_projs = list(existing.projects or [])
            added = False
            for p in incoming.projects:
                if p not in existing_projs:
                    existing_projs.append(p)
                    added = True
            if added:
                existing_projs = sorted(set(existing_projs))
            existing.projects = existing_projs

    @staticmethod
    def _merge_event(existing: GeniEvent | None,
                     incoming: GeniEvent | None) -> GeniEvent | None:
        """Merge two event records into one. Picks the more informative
        date via `_pick_best_date` and fills in missing location.

        Used for birth/death/baptism/burial during consolidation.

        Returns a fresh GeniEvent so we never mutate `existing` in place
        — partners of a marriage record share one `partner_death`
        GeniEvent by reference, and mutating it would leak the wife's
        later death event into the husband's profile (and vice versa).
        """
        if incoming is None:
            return existing
        if existing is None:
            return incoming
        from verso.core.targets.geni.event import GeniEvent as _GeniEvent
        # A synthetic bound (the parent-birth estimate) is DERIVED from a
        # relative's date, not read off a record. It exists to give an
        # otherwise dateless per-record stub something for Geni to match on —
        # so as soon as ANY other dated birth is in play it drops out entirely
        # and never reaches `_pick_best_date`. Letting it in would make the
        # consolidated date depend on merge order: the estimate can absorb a
        # real year through the range-extension branches and then be preferred
        # over it. Dropping it keeps every already-consolidated date
        # bit-for-bit what it was before estimates existed.
        ex_syn = existing.date is not None and existing.date.synthetic
        in_syn = incoming.date is not None and incoming.date.synthetic
        if ex_syn != in_syn:
            keep, drop = ((incoming, existing) if ex_syn else (existing, incoming))
            if keep.date is not None:
                return _GeniEvent(date=keep.date,
                                  location=keep.location or drop.location)
        merged = _GeniEvent(date=existing.date, location=existing.location)
        # Date: resolve via precedence helper. `_pick_best_date` may
        # mutate the date object it returns (legacy semantics), so feed
        # it a copy of the existing date when we're keeping it.
        if merged.date is None:
            merged.date = incoming.date
        elif incoming.date is not None:
            merged.date = TerraformGenerator._pick_best_date(
                copy.copy(existing.date), incoming.date,
            )
        # Location: fill in if missing. Specific dates typically carry a
        # location; range markers (census 'after', godparent-estimate
        # 'between') typically don't. Preserve the location we have.
        if incoming.location and not merged.location:
            merged.location = incoming.location
        return merged

    @staticmethod
    def _pick_best_date(existing: GeniDate, incoming: GeniDate) -> GeniDate:
        """Pick the more informative date between two `GeniDate` instances.

        Faithful port of legacy `compare_events` date-merge logic
        Mutates `existing` in
        place when narrowing or extending a between-range, and returns
        the merged date (which may be `existing` or `incoming`).

        Branch order mirrors legacy verbatim — re-ordering will change
        semantics for overlapping conditions.

        Both arguments are non-None: the sole caller (`_merge_event`) only
        reaches here once it has established `existing.date is not None` and
        `incoming.date is not None`. The legacy port carried `existing is
        None` / `incoming is None` disjuncts in branches 1 and 2, but the
        unconditional `.date_range` reads below already dereference both —
        those guards were unreachable and have been dropped. Branch order and
        every branch body are otherwise untouched.
        """
        from datetime import timedelta

        # Equal dates → keep existing.
        if existing == incoming:
            return existing

        ex_range = existing.date_range
        in_range = incoming.date_range

        # 1) Incoming is more precise (specific, no circa, no range)
        #    than existing (which is circa or empty year).
        if (
            not incoming.circa and not in_range
            and existing.circa
        ):
            return incoming

        # 2) Existing is more precise (specific, no circa, range not
        #    in [after, before]) than incoming. Keep existing.
        if (
            not existing.circa
            and incoming.circa
            and ex_range not in ("after", "before")
        ):
            return existing

        # 3) Both circa, no range — fill / collapse / between.
        if (
            existing.circa and not ex_range
            and incoming.circa and not in_range
        ):
            if existing.year == incoming.year:
                # Same year: fill in missing month/day from incoming.
                if not existing.month or incoming.month:
                    existing.month = incoming.month
                    existing.day = incoming.day
                elif not existing.day or incoming.day:
                    existing.day = incoming.day
                return existing
            # Different years → promote to a between range.
            existing.date_range = "between"
            existing.end_circa = True
            ex_dt = existing.to_datetime()
            in_dt = incoming.to_datetime()
            if ex_dt is not None and in_dt is not None and ex_dt < in_dt:
                existing.end_day = incoming.day
                existing.end_month = incoming.month
                existing.end_year = incoming.year
            else:
                existing.end_day = existing.day
                existing.end_month = existing.month
                existing.end_year = existing.year
                existing.day = incoming.day
                existing.month = incoming.month
                existing.year = incoming.year
            return existing

        # 4) Existing is a between-range >50 weeks wide AND incoming
        #    is a circa-no-range date that falls inside the range →
        #    collapse to the more precise incoming.
        #
        # From here down each branch hoists its `to_datetime()` /
        # `to_end_datetime()` results into locals. The methods are pure and
        # `existing` is only mutated inside branch bodies (after the condition
        # has been evaluated), so this is exactly equivalent to re-calling them
        # — it just lets the `is not None` guards narrow.
        ex_dt = existing.to_datetime()
        ex_end = existing.to_end_datetime()
        in_dt = incoming.to_datetime()
        in_end = incoming.to_end_datetime()

        if (
            existing.circa and existing.end_circa
            and ex_range == "between"
            and ex_end is not None
            and ex_dt is not None
            and (ex_end - ex_dt) > timedelta(weeks=50)
            and incoming.circa and not in_range
            and in_dt is not None
            and ex_dt <= in_dt <= ex_end
        ):
            return incoming

        # 5) Existing between-range; incoming is circa-no-range AFTER
        #    the end but within 2 years → extend end.
        if (
            existing.circa and existing.end_circa
            and ex_range == "between"
            and incoming.circa and not in_range
            and ex_end is not None
            and in_dt is not None
            and ex_end <= in_dt
            and (in_dt - ex_end) < timedelta(weeks=100)
        ):
            existing.end_year = incoming.year
            existing.end_month = incoming.month
            existing.end_day = incoming.day
            return existing

        # 6) Existing between-range; incoming is circa-no-range BEFORE
        #    the start but within 2 years → extend start.
        if (
            existing.circa and existing.end_circa
            and ex_range == "between"
            and incoming.circa and not in_range
            and in_dt is not None
            and ex_dt is not None
            and in_dt < ex_dt
            and (in_dt - ex_dt) < timedelta(weeks=100)
        ):
            existing.year = incoming.year
            existing.month = incoming.month
            existing.day = incoming.day
            return existing

        # 7) Both are between-ranges with any overlap → narrow.
        if (
            existing.circa and existing.end_circa
            and ex_range == "between"
            and incoming.circa and incoming.end_circa
            and in_range == "between"
            and ex_dt is not None and ex_end is not None
            and in_dt is not None and in_end is not None
            and (ex_end > in_dt or ex_dt < in_end)
        ):
            if ex_end > in_end:
                existing.end_day = incoming.end_day
                existing.end_month = incoming.end_month
                existing.end_year = incoming.end_year
            if ex_dt < in_dt:
                existing.day = incoming.day
                existing.month = incoming.month
                existing.year = incoming.year
            return existing

        # 8) Existing "after", incoming later than existing.
        if (
            ex_range == "after"
            and in_dt is not None
            and ex_dt is not None
            and in_dt > ex_dt
        ):
            if in_range != "before":
                return incoming
            existing.date_range = "between"
            existing.end_circa = incoming.circa
            existing.end_day = incoming.day
            existing.end_month = incoming.month
            existing.end_year = incoming.year
            return existing

        # 9) Existing "after"+circa, incoming circa-no-range within 2
        #    years before existing → keep existing.
        if (
            ex_range == "after" and existing.circa
            and incoming.circa and not in_range
            and in_dt is not None
            and ex_dt is not None
            and in_dt < ex_dt
            and (in_dt - ex_dt) < timedelta(weeks=100)
        ):
            return existing

        # 10) Incoming "after", existing more precise than the marker
        #     → keep existing.
        if (
            in_range == "after"
            and ex_dt is not None
            and in_dt is not None
            and ex_dt > in_dt
        ):
            return existing

        # 11) Existing is a bare "before" upper bound (the parent-birth
        #     estimate emitted when a record states no age for the child);
        #     incoming is an actual date that satisfies that bound → the
        #     real date wins. Without this the fallback below would keep
        #     the coarse marker and DISCARD e.g. a census circa birth year.
        #     Legacy never emitted a "before" birth, so it has no such case.
        if (
            ex_range == "before"
            and in_range not in ("before", "after")
            and in_dt is not None
            and ex_dt is not None
            and in_dt <= ex_dt
        ):
            return incoming

        # 12) Mirror of 11: the incoming "before" marker adds nothing over an
        #     existing date that already satisfies it.
        if (
            in_range == "before"
            and ex_range not in ("before", "after")
            and ex_dt is not None
            and in_dt is not None
            and ex_dt <= in_dt
        ):
            return existing

        # Fallback: keep existing (legacy raises here, but new generator
        # is more permissive — silent first-wins is safer for live data).
        return existing

    def _any_in_move_list(self, *res_names: str | None) -> bool:
        """True iff any of `res_names` is in `profile_move_list`. Skips
        `None` and empty strings. Used by census-union routing to fold
        children into the consolidation check (the earlier generator's
        `at_least_one_consolidated_profile`).
        """
        return any(
            rn and self.consolidation.in_profile_move_list(rn)
            for rn in res_names
        )

    def _route_union(self, union: GeniUnion, *, filename: str,
                     is_consolidated: bool) -> None:
        """Either emit `union` into the per-year `filename` or route it into
        the `consolidated_unions.tf` bucket. The caller decides: a union
        where any participant is in `profile_move_list` (or whose own
        res_name is overridden by `union_move_list_v2`) must be consolidated.
        """
        # union_move_list_v2 override forces consolidation regardless of
        # whether the participants are individually in profile_move_list —
        # legacy explicitly routes those unions there (union_move_list_v2 is
        # populated from `unions_to_consolidate`'s `union_names` lists).
        if (
            not is_consolidated
            and self.consolidation.union_redirect_target(union.res_name) is not None
        ):
            is_consolidated = True
        if not is_consolidated:
            # Two passes can legitimately build the SAME union: the
            # secondary-relationship pass emits the marital pair
            # (`secondary_role=HUSBAND/WIFE`), and the sub-family pass emits
            # the same man with his children. Both key the res_name on the
            # husband, so appending blindly would write two `resource
            # "geni_union"` blocks under one name — a terraform duplicate.
            # The consolidated path has always merged (see
            # `_add_to_consolidated_unions`); this makes the per-year path
            # agree, taking the union of partners and children.
            prev = self._union_registry.get(union.res_name)
            prev_file = self._union_files.get(union.res_name)
            if prev is not None and prev_file == filename:
                merged = GeniUnion(
                    res_name=union.res_name,
                    partner_1=prev.partner_1 or union.partner_1,
                    partner_2=prev.partner_2 or union.partner_2,
                    children=set(prev.children) | set(union.children),
                    partner_1_profile=(prev.partner_1_profile
                                       or union.partner_1_profile),
                    partner_2_profile=(prev.partner_2_profile
                                       or union.partner_2_profile),
                    children_profiles=(set(prev.children_profiles)
                                       | set(union.children_profiles)),
                    marriage=prev.marriage or union.marriage,
                    foster_children=(set(prev.foster_children)
                                     | set(union.foster_children)),
                    origin=prev.origin or union.origin,
                )
                self._outputs[filename] = self._outputs[filename].replace(
                    prev.to_terraform(), merged.to_terraform(), 1,
                )
                self._union_registry[union.res_name] = merged
                return
            self._union_registry[union.res_name] = union
            self._union_files[union.res_name] = filename
            self._outputs[filename] += union.to_terraform()
            return
        self._add_to_consolidated_unions(union)

    def _add_to_consolidated_unions(self, union: GeniUnion) -> None:
        """Simplified mirror of the earlier generator's union consolidation: pick a
        target res_name (from `union_move_list_v2` when present, else
        `{p1}_and_{p2}`-style); merge children into an existing entry keyed
        by that target OR by a partner already seen; apply post-merge hints
        from `unions_to_consolidate`.
        """
        # Compute target res_name.
        v2 = self.consolidation.union_move_list_v2
        v2_targets = set(v2.values())
        redirected = self.consolidation.union_redirect_target(union.res_name)
        v2_redirect = redirected is not None
        if redirected is not None:
            target = redirected
        else:
            p1, p2 = union.partner_1, union.partner_2
            raw = ""
            if p1:
                raw = p1
            if p2:
                raw = f"{raw} and {p2}" if raw else p2
            target = generate_res_name(raw) if raw else union.res_name

        # Snapshot the source union (pre-merge) so the documentation
        # comment in finalize() can list its original res_name + partners
        # + children. Take a deep copy because the merge below mutates
        # `existing` in place.
        source_snapshot = copy.deepcopy(union)

        # Find-or-create.
        existing = self._consolidated_unions.get(target)
        # Partner-lookup fallback only fires when v2 didn't explicitly
        # redirect this union. Otherwise a same-partner union previously
        # consolidated to a different target would override the v2
        # redirect — corrupting splits like `egor_ilich_vidopljasov`'s
        # children-by-wife (an early marriage with Татьяна → tatjana
        # target; the later children explicitly redirected to the
        # olga_pavlovna target via v2 — partner lookup must not override that).
        # Illegitimate-birth unions (a birth record naming no father) must
        # NOT fold via partner-lookup into the mother's marital union with a
        # DIFFERENT husband. The MK record explicitly marked the child
        # as незаконнорожденная; attaching her to the husband+mother
        # bucket implies the husband is the father, contradicting the
        # source. Legacy held these in a separate single-mother bucket
        # (e.g. `darja_semenovna` standalone, distinct from her
        # `semen_ilich_and_darja_semenovna` marital union).
        is_illegit_birth = (union.origin is UnionOrigin.BIRTH
                            and union.partner_1 is None)
        # Child-lookup pre-tier for death-record unions (the deceased
        # and the relative the burial names): when the
        # deceased child is already a child of an existing consolidated
        # union AND that union shares a partner with the incoming source,
        # route there directly (skipping the generic partner-lookup that
        # registers only one bucket per partner). Without this, a multi-
        # wife father's death record for a child of his SECOND wife is
        # routed to his first-wife bucket — the partner-lookup map only
        # remembers one target per partner.
        #
        # Concrete regression shape: a birth record attests a girl as the
        # daughter of a man and his SECOND wife; the girl's death record
        # (`<girl>_and_<father>_d<N>_<year>` — partner_1=father, no
        # partner_2) names the father alone. Routing via partner-lookup on
        # the father goes to his FIRST wife's bucket; the earlier generator
        # correctly filed her in the second wife's bucket, where she is
        # already a child.
        is_death_source = union.origin is UnionOrigin.DEATH
        if (existing is None and not v2_redirect and is_death_source
                and union.children):
            for cand_target, cand in self._consolidated_unions.items():
                if not cand.children:
                    continue
                if not (union.children & cand.children):
                    continue
                # Require partner overlap so we don't fold across
                # unrelated families that happen to share a child name.
                u_partners = {p for p in (union.partner_1, union.partner_2) if p}
                c_partners = {p for p in (cand.partner_1, cand.partner_2) if p}
                if u_partners & c_partners:
                    existing = cand
                    target = cand_target
                    break
        if existing is None and not v2_redirect and not is_illegit_birth:
            for p in (union.partner_1, union.partner_2):
                if p and p in self._partner_to_consolidated_union:
                    alt_target = self._partner_to_consolidated_union[p]
                    candidate = self._consolidated_unions.get(alt_target)
                    if candidate is None:
                        continue
                    # Spouse-conflict guard: when the incoming union has
                    # both partners and the candidate target's partner_2
                    # is a DIFFERENT person, this is a different spouse
                    # — split into a new bucket. Mirrors the earlier
                    # generator's behavior: when
                    # `union.partner_2` differs from existing's partner_2,
                    # legacy creates a NEW consolidated_union for the
                    # incoming and APPENDs it to existing_unions list
                    # (rather than folding into the existing).
                    #
                    # Affects children-by-wife splits (e.g. a roll household
                    # with a second wife should NOT fold into the first
                    # wife's bucket; a later roll with a placeholder wife
                    # should NOT fold into the bucket of an earlier
                    # marriage with another wife).
                    if (union.partner_1 == candidate.partner_1
                            and union.partner_2
                            and candidate.partner_2
                            and union.partner_2 != candidate.partner_2
                            and union.partner_2 != candidate.partner_1):
                        continue
                    # Spouse-conflict guard, deferred-wife variant: the
                    # candidate bucket's NAME may already encode a
                    # specific partner_2 (via v2 redirect targeting
                    # `<husband>_and_<wife>`) while no source has yet
                    # populated `candidate.partner_2`. Treat the bucket
                    # name's `_and_<wife>` suffix as authoritative:
                    # when the bucket name encodes a different couple
                    # than the incoming union's `<p1>_and_<p2>` target,
                    # skip — it's a different wife.
                    #
                    # Skip ONLY when the candidate bucket name already
                    # has a `_and_<wife>` shape; if the bucket is keyed
                    # under a husband-only name (e.g. just `petr`),
                    # fall through to fold the marriage record's
                    # partner_2 in normally.
                    #
                    # Concrete regression shape: a later birth
                    # `petr_..._and_anna_..._18_<year>` was being
                    # folded into `petr_..._and_maria_...`
                    # because that bucket — created from an earlier
                    # single-father birth via v2 redirect — had
                    # `partner_2=None` at the moment the later source
                    # arrived, so the previous guard short-circuited.
                    expected_target = (
                        generate_res_name(
                            f"{union.partner_1} and {union.partner_2}",
                        )
                        if union.partner_1 and union.partner_2 else None
                    )
                    if (union.partner_1 == candidate.partner_1
                            and union.partner_2
                            and not candidate.partner_2
                            and expected_target is not None
                            and alt_target != expected_target
                            and "_and_" in alt_target
                            and expected_target in v2_targets
                            and union.partner_2 != candidate.partner_1):
                        continue
                    # Symmetric partner_1-conflict guard: same mother,
                    # different fathers (e.g. two births, the one with father
                    # `_<date>_makar_ivanovich_mk_births_6_father`
                    # and the other with father `_<date>_makar_
                    # petrovich_mk_births_32_father` — same mother
                    # `maria_petrovna_2`, but the per-record-stub
                    # fathers carry different patronymics so they
                    # remain distinct profiles in TF). Legacy emitted
                    # them as separate consolidated unions; new code's
                    # partner-lookup via the shared mother folded the
                    # later child into the earlier bucket. Whether the two
                    # fathers are genealogically the same person is a
                    # DSL/consolidation decision, not a routing one —
                    # without an explicit `profiles_to_consolidate`
                    # entry merging the per-record stubs into one
                    # canonical Makar, treat them as different and
                    # keep the buckets separate.
                    if (union.partner_2 == candidate.partner_2
                            and union.partner_1
                            and candidate.partner_1
                            and union.partner_1 != candidate.partner_1
                            and union.partner_1 != candidate.partner_2):
                        continue
                    existing = candidate
                    target = alt_target
                    break

        if existing is None:
            consolidated = copy.deepcopy(union)
            consolidated.res_name = target
            self._consolidated_unions[target] = consolidated
            existing = consolidated
            # When a v2-redirected union creates a new consolidated
            # target, fold any pre-existing single-partner placeholder
            # consolidated unions for the same partner into this target.
            # The earlier generator did this implicitly via the rename-on-partner_2-
            # discovery path: a
            # `foma_petrovich` consolidated union (created by an
            # earlier birth record, no partner_2) gets renamed into
            # `foma_petrovich_and_agafja_ivanovna` once a union
            # with partner_2 arrives. Without this, MK children attested
            # before the v2-redirected union arrives are stranded in the
            # placeholder.
            if v2_redirect:
                # Compatibility: when the v2 target name encodes a
                # specific spouse (`<husband>_and_<wife>`), only fold
                # in old unions whose partner_2 matches that spouse
                # (or is None, i.e. placeholder). Spouse-agnostic v2
                # targets (no `_and_`) fold any same-partner old union.
                v2_has_and = "_and_" in target
                for p in (union.partner_1, union.partner_2):
                    if not p:
                        continue
                    old_target = self._partner_to_consolidated_union.get(p)
                    if not old_target or old_target == target:
                        continue
                    old = self._consolidated_unions.get(old_target)
                    if old is None:
                        continue
                    # A different explicit v2 destination is not a
                    # generic single-partner placeholder. It may only be
                    # missing partner_2 because the spouse source has not
                    # arrived yet (e.g. Foma+Maria vs Foma+Agafja).
                    if old_target in v2_targets:
                        continue
                    if old.partner_1 != p:
                        continue
                    # Spouse-conflict check for `_and_<spouse>` v2 targets.
                    # If the old union has a different partner_2 than
                    # what the v2 target name implies, skip (e.g. egor_
                    # ilich_and_tatjana_X must NOT fold into
                    # egor_ilich_and_olga_pavlovna).
                    if (v2_has_and
                            and old.partner_2 is not None
                            and target.endswith(f"_and_{old.partner_2}") is False
                            and f"_and_{old.partner_2}_" not in target):
                        continue
                    # Fold old INTO existing (the new v2 target).
                    existing.children = (existing.children or set()) | (old.children or set())
                    existing.foster_children = (
                        (existing.foster_children or set())
                        | (getattr(old, "foster_children", None) or set()))
                    if (old.partner_2 is not None
                            and existing.partner_2 is None
                            and old.partner_2 != existing.partner_1):
                        existing.partner_2 = old.partner_2
                        existing.partner_2_profile = old.partner_2_profile
                    if old.marriage is not None and existing.marriage is None:
                        existing.marriage = old.marriage
                    # Move the old target's source-merge log into the
                    # new target so the manifest comment lists every
                    # merged source.
                    old_sources = self._consolidated_unions_sources.pop(
                        old_target, [],
                    )
                    self._consolidated_unions_sources.setdefault(
                        target, [],
                    ).extend(old_sources)
                    # Delete the old.
                    del self._consolidated_unions[old_target]
                    # Repoint partner-lookup entries from old_target to
                    # the new target.
                    for k, v in list(self._partner_to_consolidated_union.items()):
                        if v == old_target:
                            self._partner_to_consolidated_union[k] = target
        else:
            # Merge: fold children, promote missing partner_2, merge
            # marriage event. The earlier generator
            # calls
            # `compare_events(consolidated_union, union, ..., "marriage")`
            # to fold the source union's marriage event into the
            # consolidated entry. Without this, a consolidated union
            # seeded from a non-marriage record (e.g. a birth-record
            # union) loses the marriage event of any later marriage
            # record that gets merged in.
            existing.children = (existing.children or set()) | (union.children or set())
            existing.foster_children = (
                (existing.foster_children or set())
                | (getattr(union, "foster_children", None) or set()))
            # Partner_2 fill-in: allow when v2 explicitly redirects, OR
            # when the incoming union itself is a "real spouse" source —
            # a marriage record's couple or a household roll's family.
            # Godparent-spouse merge unions (a father and the godparent
            # the birth record names beside him) pollute partner_2 with
            # the godparent rather than the actual spouse — block those.
            # Until 2026-09-28 this was read off the res_name
            # (`_m<N>_<year>`, `_rs<N>_<year>`), which a marriage entered
            # without a number and a household numbered «1а» defeated.
            partner_2_authoritative = (
                v2_redirect
                or union.origin in (UnionOrigin.MARRIAGE, UnionOrigin.ROLL)
            )
            # Don't fold partner_2 if it equals existing.partner_1 —
            # that creates a degenerate "self-married" union (e.g.
            # death record `anna_and_maria_ivanovna_d12_1850`
            # has partner_1=unknown-father, partner_2=maria; when
            # the consolidated `maria_ivanovna` already has
            # partner_1=maria, folding partner_2 in produces
            # partners=[maria, maria]).
            if (union.partner_2
                    and not existing.partner_2
                    and partner_2_authoritative
                    and union.partner_2 != existing.partner_1):
                existing.partner_2 = union.partner_2
                existing.partner_2_profile = union.partner_2_profile
                # Rename-on-partner_2-discovery: mirrors the earlier
                # generator. When an
                # earlier single-partner source created the bucket
                # under target `<p1>` (e.g. `pavel_ilich_2` from
                # a birth record with no mother), and a later source
                # discovers partner_2 (e.g. a roll household attests
                # a wife), legacy renames the bucket to
                # `<p1>_and_<p2>` — UNLESS the existing target is a
                # v2-redirect destination (`union_move_list_v2.values()`)
                # OR the incoming source is v2-redirected. Without this
                # rename, new code keeps single-token target while
                # legacy uses `_and_<wife>` form for ~94 unions.
                if (not v2_redirect
                        and target not in v2_targets
                        and union.partner_1):
                    new_target = generate_res_name(
                        f"{union.partner_1} and {union.partner_2}"
                    )
                    if new_target != target:
                        # Rename bucket in place: preserve dict insertion
                        # order so the rendered file keeps the bucket at
                        # its original position (matches legacy).
                        # Rebuild dicts with renamed key.
                        bucket = self._consolidated_unions[target]
                        bucket.res_name = new_target
                        new_unions = {}
                        for k, v in self._consolidated_unions.items():
                            if k == target:
                                new_unions[new_target] = bucket
                            else:
                                new_unions[k] = v
                        self._consolidated_unions = new_unions
                        # Migrate sources merge log preserving order.
                        new_sources = {}
                        for k, v in self._consolidated_unions_sources.items():
                            if k == target:
                                new_sources[new_target] = v
                            else:
                                new_sources[k] = v
                        self._consolidated_unions_sources = new_sources
                        # Repoint partner-lookup entries from old
                        # target to the new target.
                        for k, v in list(
                            self._partner_to_consolidated_union.items()
                        ):
                            if v == target:
                                self._partner_to_consolidated_union[k] = new_target
                        existing = bucket
                        target = new_target
            # Target-name override: when v2 redirects a multi-wife
            # source like `pavel_ivanovich_rs12_1850` (legacy emits
            # this name twice — once per wife of one household — and
            # both emissions land in the same consolidated bucket),
            # the first emission seeds existing.partner_2 with the
            # 1st-wife per-record stub. The second emission's partner_2
            # is the consolidated wife profile that the target name
            # actually implies (e.g. `pavel_ivanovich_and_sofja_
            # petrovna` → spouse=sofja_petrovna). Override so the
            # bucket's partner_2 matches its res_name.
            elif (v2_redirect
                  and union.partner_2
                  and existing.partner_2
                  and union.partner_2 != existing.partner_2
                  and target.endswith(f"_and_{union.partner_2}")
                  and not target.endswith(f"_and_{existing.partner_2}")
                  and union.partner_2 != existing.partner_1):
                existing.partner_2 = union.partner_2
                existing.partner_2_profile = union.partner_2_profile
            # Don't fold partner_1 if it equals existing.partner_2 —
            # mirrors the partner_2 guard above. Triggered when a
            # single-mother union (father=None, partner_2=mother)
            # gets a later source where the same mother arrives as
            # partner_1 (e.g. she appears again as the only partner
            # in a different record), which would produce
            # partners=[mother, mother].
            if (union.partner_1
                    and not existing.partner_1
                    and union.partner_1 != existing.partner_2):
                existing.partner_1 = union.partner_1
                existing.partner_1_profile = union.partner_1_profile
            # Single-partner incoming → promote partner_1 to existing's
            # partner_2 when existing already has a different partner_1.
            # Use case: ascending-role census unions like
            # `tatjana_sergeevna_rs12_1850` (parent_1=Татьяна only,
            # no spouse) merging into `nikolaj_and_tatjana_sergeevna`
            # (existing parent_1=Николай) — without this, Татьяна's
            # profile is dropped from the consolidated union's partners.
            elif (union.partner_1
                  and not union.partner_2
                  and not existing.partner_2
                  and existing.partner_1
                  and existing.partner_1 != union.partner_1
                  and partner_2_authoritative):
                existing.partner_2 = union.partner_1
                existing.partner_2_profile = union.partner_1_profile
            if union.marriage is not None:
                existing.marriage = TerraformGenerator._merge_event(
                    existing.marriage, union.marriage,
                )

        # Record partner → target so same-partner unions converge.
        # When v2 explicitly redirects this union to a target, OVERWRITE
        # any prior auto-derived registration for the same partner —
        # later v2 targets win, so a non-v2 union (e.g. an RS family
        # member union) processed after the v2 mappings lands in the
        # most recently declared target. Without this, iteration order
        # decides which wife a non-v2 union gets attached to (e.g. a
        # man's union from an early roll household processed before a
        # later birth would pin him to his first wife, diverting his
        # later roll union — actually with a second wife — to the
        # wrong target).
        # Helper: detect a per-record stub partner — a profile minted for
        # one MK/RS appearance that no fold made a canonical (until
        # 2026-09-28 read off a `_YYYY_MM_DD_` res_name prefix, which took a
        # Заманиловка canonical named after its first record for a stub and
        # missed a stub whose record date lacks a month). When a
        # partner is registered to a target whose OTHER partner is such
        # a per-record stub, a later target with a CONSOLIDATED other
        # partner is genealogically "more canonical" and should win for
        # partner-lookup. Without this, a man's first marriage registers
        # man → man+<wife>_<year>_bride first; his later marriage to a
        # consolidated wife doesn't overwrite via setdefault; subsequent
        # partner-only sources like a later birth route to the first
        # marriage's stub bucket. Legacy routed them to the consolidated
        # wife.
        def _is_stub(p):
            return (p in self._minted_res_names
                    and not self.consolidation.is_target(p))

        def _other(union, partner):
            if union.partner_1 == partner:
                return union.partner_2
            if union.partner_2 == partner:
                return union.partner_1
            return None

        def _register(partner):
            if not partner:
                return
            prev_target = self._partner_to_consolidated_union.get(partner)
            if v2_redirect:
                self._partner_to_consolidated_union[partner] = target
                return
            if prev_target is None:
                self._partner_to_consolidated_union[partner] = target
                return
            if prev_target == target:
                return
            prev_union = self._consolidated_unions.get(prev_target)
            if prev_union is None:
                self._partner_to_consolidated_union[partner] = target
                return
            prev_other = _other(prev_union, partner)
            cur_other = _other(existing, partner)
            # Overwrite when prev's other partner is a per-record stub
            # AND current's other partner is consolidated (not a stub).
            if (prev_other is not None
                    and cur_other is not None
                    and _is_stub(prev_other)
                    and not _is_stub(cur_other)):
                self._partner_to_consolidated_union[partner] = target

        _register(existing.partner_1)
        _register(existing.partner_2)

        # Append the source-union snapshot to the merge log under the
        # FINAL target (which may have been remapped via the partner-
        # lookup above). Preserves insertion order so the comment block
        # in finalize() lists merged unions in the order they arrived.
        self._consolidated_unions_sources.setdefault(
            target, [],
        ).append(source_snapshot)

        # Apply `unions_to_consolidate` hints (undocumented_partner,
        # undocumented_children, exclude_children, override).
        hint = self.consolidation.unions_to_consolidate.get(target, {})
        undoc_partner = hint.get("undocumented_partner")
        if undoc_partner:
            # When the consolidated target name has the form
            # `<husband>_and_<wife>` and `undoc_partner` matches the
            # husband part (the prefix before `_and_`), assign it to
            # partner_1 — otherwise the rendered union ends up with
            # `partners = [<wife>, <husband>]` instead of legacy's
            # `[<husband>, <wife>]`. Concrete case: target
            # `petr_ivanovich_and_anna_petrovna` absorbs
            # legacy `anna_petrovna_rs12_1850` (single-partner
            # source: partner_1=anna_petrovna_rs_53_1) and then
            # appends `undocumented_partner=petr_ivanovich`. With
            # the elif fallback below, petr landed in partner_2;
            # legacy had petr as partner_1.
            husband_implied = None
            if "_and_" in (target or ""):
                # Take the LAST `_and_` so multi-token husband names
                # (e.g. `ivan_petrovich_and_maria_ivanovna`) parse
                # correctly.
                husband_implied = target.rsplit("_and_", 1)[0]
            if (husband_implied is not None
                    and undoc_partner == husband_implied
                    and existing.partner_1 is not None
                    and existing.partner_1 != undoc_partner):
                # Demote existing partner_1 to partner_2 (if free) and
                # promote undoc to partner_1.
                if not existing.partner_2:
                    existing.partner_2 = existing.partner_1
                    existing.partner_2_profile = existing.partner_1_profile
                existing.partner_1 = undoc_partner
                existing.partner_1_profile = None
            elif not existing.partner_1:
                existing.partner_1 = undoc_partner
                existing.partner_1_profile = None
            elif (not existing.partner_2
                  and existing.partner_1 != undoc_partner):
                existing.partner_2 = undoc_partner
                existing.partner_2_profile = None
        if "undocumented_children" in hint:
            # Route through the move list like every other child reference:
            # these are hand-written res_names, and consolidating one of them
            # later would otherwise leave a dangling `geni_profile.<record>`
            # reference in consolidated_unions.tf ("Reference to undeclared
            # resource" at plan time). move_to_new_name is a no-op for names
            # that are not consolidated.
            existing.children = (existing.children or set()) | {
                self.consolidation.move_to_new_name(name)
                for name in hint["undocumented_children"]
            }
        if "exclude_children" in hint:
            # Same reasoning as undocumented_children: the exclusion has to be
            # expressed in the same namespace as `existing.children`, which
            # holds canonical names after consolidation.
            existing.children = (existing.children or set()) - {
                self.consolidation.move_to_new_name(name)
                for name in hint["exclude_children"]
            } - set(hint["exclude_children"])
        # Union override: legacy `compare_events(consolidated_union, union,
        # override, [], "marriage")`
        # unconditionally replaces the union's marriage `.date` and/or
        # `.location` with override values. Mirrors profile-override
        # event semantics in `_apply_profile_overrides`.
        override = hint.get("override")
        if override is not None:
            override_marriage = getattr(override, "marriage", None)
            if override_marriage is not None:
                if existing.marriage is None:
                    existing.marriage = override_marriage
                else:
                    if override_marriage.date is not None:
                        existing.marriage.date = override_marriage.date
                    if override_marriage.location is not None:
                        existing.marriage.location = override_marriage.location

    def finalize(self) -> None:
        # Self-as-child guard: a union never lists its own partner_1 /
        # partner_2 among its children. Written for a roll union
        # (`<wife>_rs56_<year>`, one household), which made a wife the
        # mother of her husband and folded into
        # `<husband>_and_<wife>`. The
        # ascending-role pass no longer claims the head's siblings for a
        # parent of someone else (2026-10-12), and since then nothing in
        # the five villages reaches this strip; it stays as a guard.
        for union in self._consolidated_unions.values():
            if not union.children:
                continue
            self_refs = {p for p in (union.partner_1, union.partner_2) if p}
            if self_refs:
                union.children = union.children - self_refs

        # Apply `additional_info` supplementary profiles BEFORE overrides
        # so that overrides (which replace unconditionally) still win.
        # Each additional_info GeniProfile is merged into the consolidated
        # profile using the same fill-in-if-missing semantics as
        # per-record merges — legacy seeded consolidated_profiles with
        # these before any per-record merge; applying them late here is
        # equivalent because `_merge_consolidated` is order-insensitive
        # for the fields additional_info typically carries (last_name,
        # birth_last_name, supplementary birth/death events).
        for target, add_infos in self.consolidation.profile_additional_info.items():
            profile = self._consolidated_profiles.get(target)
            if profile is None:
                continue
            for index, add_info in enumerate(add_infos):
                # RAI001: an entry whose merge changes nothing had every value
                # it declares already present, and lost them silently.
                before = snapshot_additional_info_fields(profile)
                self._merge_consolidated(profile, add_info)
                finding = detect_redundant_additional_info(
                    target, index, add_info, before,
                    snapshot_additional_info_fields(profile))
                if finding is not None:
                    self.redundant_additional_info.append(finding)

        # `lifecycle_ignore_changes` hints — emit a terraform lifecycle block
        # on the canonical (e.g. ignore co-author location-derived `projects`
        # drift that can neither be replaced nor pinned).
        for target, attrs in self.consolidation.profile_lifecycle_ignores.items():
            profile = self._consolidated_profiles.get(target)
            if profile is not None and attrs:
                profile.lifecycle_ignore_changes = list(attrs)

        self._apply_profile_overrides()

        # RIG001: ignore entries never consulted-and-matched anywhere.
        self.redundant_ignores = collect_redundant_ignores(
            self.consolidation.profile_ignores, self._ignore_seen,
            explain=self._explain_dead_ignore)

        # RPF001: preference pins that never changed anything.
        self.redundant_preferences = collect_redundant_preferences(
            self.consolidation.profile_preferences, self._preference_seen,
            seeded=self._seeded_canonicals,
            seed_before=self._preference_seed_before)

        # Suppress redundant `last_name` when it equals `birth_last_name`
        # on the consolidated profile — same rule the per-record emitter
        # applies in `_profile_from_person`. Reaches the consolidated
        # case where per-records with explicit last_name merge with
        # per-records or additional_info that supply birth_last_name and
        # both end up holding the same maiden surname. Geni renders both
        # fields, which falsely implies a distinct current/married name.
        for profile in self._consolidated_profiles.values():
            if (profile.last_name and profile.birth_last_name
                    and profile.last_name == profile.birth_last_name):
                profile.last_name = ""

        # Sort each consolidated profile's about-block sections by year
        # ascending. Mirrors the earlier generator, which sorted the fragments
        # by their source date. Done at finalize so the sort
        # sees the fully-merged about content (after overrides), not
        # mid-merge fragments.
        for profile in self._consolidated_profiles.values():
            if profile.about:
                profile.about = _sort_about_sections(profile.about)

        # Partition consolidated profiles into shard files: sort by
        # res_name and chunk. Deterministic between runs. Profiles
        # built from multiple source records get a
        # `# Consolidated profile with merged profiles:` header above
        # them listing the sources alphabetically (informational only —
        # comments aren't part of terraform state).
        def render_profile_with_header(profile: GeniProfile) -> str:
            sources = self._consolidated_profiles_sources.get(profile.res_name)
            if not sources:
                return profile.to_terraform()
            lines = ["# Consolidated profile with merged profiles:\n"]
            lines.append("# - " + "\n# - ".join(sorted(set(sources))) + "\n")
            return "".join(lines) + profile.to_terraform()

        profiles = sorted(
            self._consolidated_profiles.values(), key=lambda p: p.res_name,
        )
        for i in range(0, len(profiles), CONSOLIDATED_PROFILES_CHUNK):
            shard_idx = 1 + i // CONSOLIDATED_PROFILES_CHUNK
            filename = f"consolidated_profiles_{shard_idx}.tf"
            chunk = profiles[i:i + CONSOLIDATED_PROFILES_CHUNK]
            self._outputs[filename] = "".join(
                render_profile_with_header(p) for p in chunk
            )

        if self._consolidated_unions:
            # Emit unions in translator-natural insertion order.
            chunks: list[str] = []
            for u in self._consolidated_unions.values():
                merged = self._consolidated_unions_sources.get(
                    u.res_name, [u],
                )
                chunks.append(_comment_for_unions(merged))
                chunks.append(u.to_terraform())
            self._outputs["consolidated_unions.tf"] = "".join(chunks)

        self._uniquify_resource_headers()

    def _uniquify_resource_headers(self) -> None:
        """Guarantee globally-unique Terraform resource names per type across
        the whole module.

        A few source records legitimately share a computed res_name — a scribal
        re-entry (the same death recorded twice), twins filed under one number,
        or male/female register entries whose names happen to coincide. These
        are harmless for the CSV/Familio pipeline but Terraform requires
        `resource "T" "N"` unique per type per module. So the FIRST declaration
        of each name keeps it — every `geni_T.N.id` cross-reference (all
        recomputed deterministically from the same record fields) resolves to
        that surviving copy — and each later duplicate declaration is renamed
        `N_2`, `N_3`, …. The renamed copies are redundant duplicates of the same
        person, folded away in the normal consolidation pass.

        Rewrites only the `resource "..." "..." {` declaration line, never a
        reference, so the base copy keeps all its edges. Runs after every
        emission path (per-record, consolidated, documents) has populated
        `_outputs`, iterating files in sorted order for a stable assignment.
        """
        header_re = re.compile(r'^(resource "(geni_[a-z_]+)" ")([^"]+)(" \{)', re.M)
        used: set[tuple[str, str]] = set()

        def _rename(m: re.Match[str]) -> str:
            rtype, name = m.group(2), m.group(3)
            if (rtype, name) not in used:
                used.add((rtype, name))
                return m.group(0)
            n = 2
            while (rtype, f"{name}_{n}") in used:
                n += 1
            used.add((rtype, f"{name}_{n}"))
            return f"{m.group(1)}{name}_{n}{m.group(4)}"

        for filename in sorted(self._outputs):
            self._outputs[filename] = header_re.sub(_rename, self._outputs[filename])

    def profile_minted_for(self, person: object) -> str | None:
        """The res_name this run minted for one DSL appearance, else None.

        The other half of the bridge described on `_minted_for_person`. None is
        a real answer and the only honest one for a profile nobody minted — a
        head-of-family stub, an external `data.geni_profile`, a held двор — so a
        caller must refuse rather than guess, and count its refusals.
        """
        return self._minted_for_person.get(person)

    def document_minted_for(self, record: object) -> str | None:
        """The geni_document res_name this run emitted for one DSL record
        (a birth, marriage, death or household), else None. A later
        declaration of the same name is renamed `…_2` in
        `_uniquify_resource_headers`; this is the name before that."""
        return self._document_for_record.get(record)

    def section_minted_for(self, person: object) -> str | None:
        """The about section one appearance's profile was minted with, as it
        reads inside its canonical's about (the sort marker stripped), or None
        when nothing was minted for it or it was minted without an about."""
        text = self._section_for_person.get(person)
        return strip_section_date_markers(text) if text else None

    def preference_pin_is_dead(self, canonical: str, field: str,
                               value: Any) -> bool:
        """Would RPF001 call `preference.<field> = value` on `canonical` dead?

        Asked of a pin that need not exist yet — the conflict report's
        suggestion asks it of every pin it would print — and answered by
        RPF001's own predicate over this run's seeds, so the suggestion and
        the check cannot disagree. Meaningful after `finalize()`.
        """
        return pin_is_dead(canonical, field, value,
                           seen=self._preference_seen,
                           seed_before=self._preference_seed_before)

    def _explain_dead_ignore(self, canonical: str, entry: dict[str, Any]) -> str:
        """Why an ignore entry never fired, when a retraction is the reason.

        A retraction on a folded record withholds the date it would have
        derived, so an `ignore` of that same date has nothing left to drop.
        """
        value = entry.get("birth.date")
        if value is None:
            return ""
        sources = [canonical, *self._consolidated_profiles_sources.get(canonical, [])]
        for res_name in sources:
            for date, why in self._withheld_births.get(res_name, []):
                if date == value:
                    return (f"the date is already withheld by `{why}=` on "
                            f"{res_name}; the entry repeats the retraction")
        return ""

    def emitted_birth_dates(self) -> dict[str, tuple[GeniDate | None, ...]]:
        """Every emitted profile's own birth date, before any fold, by res_name.

        One entry per emission, so a res_name two entries share (a repeated
        record number) holds two. This is the value a `birth.date` ignore entry
        must equal to drop that record's date from its canonical — read off the
        translation, never recomputed from the record.
        """
        return {name: tuple(dates) for name, dates in self._emitted_births.items()}

    def minted_twice(self) -> list[tuple[str, str]]:
        """Appearances that received a SECOND profile, as (first, second).

        Empty on every village today, which is what makes the appearance a
        usable identity key; a caller that finds it non-empty is looking at an
        ambiguity, not at an identity.
        """
        return list(self._minted_twice)

    def _profile_from_person(self, p, *, year, month, day, document_name,
                              role, record_number, patr_override=None,
                              gender_override=None,
                              birth=None, baptism=None, death=None, burial=None,
                              current_residence=None, projects=None, about="",
                              cause_of_death=None,
                              res_name_suffix: str | int | None = "",
                              last_name_override=None,
                              birth_last_name_override=None,
                              occupation=None, source_date_error=None):
        # Canonicalize first names via names.csv (e.g. "Иев" → "Иов") so both
        # res_names and the displayed first_name attribute use the modern
        # canonical form. Names with no names.csv variant entry fall back to
        # the orthographic form so we only rename where canonicalization
        # actually has an opinion.
        first_name = p.get_canonical_name() or p.name_modern or ""
        middle_name = patr_override if patr_override is not None else (p.patr_modern or "")
        # `last_name_override` lets marriages substitute the bride's maiden
        # surname with her married one (see `bride_takes_groom_surname`).
        last_name = last_name_override if last_name_override is not None else (p.last_name_modern or "")
        birth_last_name = (
            birth_last_name_override
            if birth_last_name_override is not None
            else (getattr(p, "birth_last_name_modern", None) or "")
        )
        # Suppress redundant `last_name` when it equals `birth_last_name` —
        # Geni renders both, but storing the maiden surname twice creates
        # the misleading impression of a "current" surname distinct from
        # the birth one. Keep only birth_last_name in that case.
        if last_name and last_name == birth_last_name:
            last_name = ""
        # Children inherit a maiden surname via `Person.birth_last_name_modern`;
        # include it in the res_name so the resource address keeps its
        # existing surname suffix (e.g. `_1838_07_10_iulitta_svistunova_...`).
        # Brides who route to birth_last_name (groom had no surname) keep
        # the legacy no-suffix res_name — that's how cross-record
        # consolidation has historically matched them.
        # `family_member` joins `child` for the same reason: CensusHousehold
        # reslots a DAUGHTER/GRANDDAUGHTER's DERIVED surname to birth_last_name
        # and leaves last_name empty, so keying only on last_name drops the
        # surname from her res_name the moment a redundant explicit one is
        # removed from the DSL — silently RENAMING (and, on an applied village,
        # destroying + recreating) live profiles.
        res_name_last = last_name or (
            birth_last_name if role in ("child", "family_member") else "")
        res_name = generate_res_name_2(
            year=year, month=month, day=day,
            first_name=first_name,
            middle_name=middle_name,
            last_name=res_name_last,
            document_name=document_name,
            role=role,
            record_number=record_number,
            suffix=res_name_suffix,
        )
        previous = self._minted_for_person.get(p)
        self._minted_res_names.add(res_name)
        if previous is None:
            self._minted_for_person[p] = res_name
        elif previous != res_name:
            self._minted_twice.append((previous, res_name))
        # Tag the about section with an invisible full-date marker so
        # same-year sections order chronologically (across birth/marriage/
        # death) instead of by record-emission order. Stripped at render.
        about = inject_section_date_marker(about, year, month, day)
        if about and p not in self._section_for_person:
            self._section_for_person[p] = about
        return GeniProfile(
            res_name=res_name,
            gender=GENDER_TF.get(gender_override or p.gender, ""),
            first_name=first_name,
            middle_name=middle_name,
            last_name=last_name,
            birth_last_name=birth_last_name,
            birth=birth,
            baptism=baptism,
            death=death,
            burial=burial,
            current_residence=current_residence,
            projects=projects if projects is not None else self._projects_for_location(p.residence),
            about=about,
            cause_of_death=cause_of_death,
            occupation=occupation if occupation is not None else getattr(p, "occupation", None),
            source_date_error=source_date_error,
        )

    def _emit_relatives(self, filename, record_relatives, *, year, month, day,
                        document_name, record_number,
                        about_for=None, birth_for=None) -> list[GeniProfile | None]:
        """Emit one geni_profile per Relative in the list, with role
        `rel_{N}` (1-based). Skip entries whose Person is None or has no
        `name_modern` (nothing meaningful to emit).

        `birth_for(rel)`: optional callback returning a `GeniEvent` birth
        estimate (or None). Marriages pass one so a mother/father of the
        groom or bride gets the same anchored estimate as the dedicated
        `groom_father` / `bride_relative` slots; births pass nothing.

        `about_for(rel)`: optional callback returning the profile's
        `about` block (or None for a bare profile). Births and marriages
        pass a callback that produces the legacy
        `<strong>МК ... :</strong> {role}` line (for births: `{rel_type}
        восприемника на крещении`; for marriages: `{rel_type} жениха/невесты`
        or `{rel_type} на свадьбе`). Deaths emit relative profiles inline
        in `add_death_records`, not via this helper.

        The earlier generator uses `role='rel_1'`,
        and `profile_move_list` is keyed on that exact suffix. Using the
        shorter `rel_N` form keeps consolidation lookups working. (The
        singular `role='relative'` used by deaths is emitted inline in
        `add_death_records`, not via this helper.)

        Returns the list of emitted profiles (with None placeholders for
        skipped entries) so callers can reference them by index if needed.
        """
        emitted: list[GeniProfile | None] = []
        for n, rel in enumerate(record_relatives or [], start=1):
            if rel is None or rel.person is None or not rel.person.name_modern:
                emitted.append(None)
                continue
            about = about_for(rel) if about_for is not None else None
            birth = birth_for(rel) if birth_for is not None else None
            profile = self._profile_from_person(
                rel.person, role=f"rel_{n}",
                current_residence=_location(rel.person.residence),
                about=about,
                birth=birth,
                year=year, month=month, day=day,
                document_name=document_name, record_number=record_number,
            )
            self._emit_profile(filename, profile)
            emitted.append(profile)
        return emitted

    def add_birth_records(self, records) -> None:
        other = "_other" if self._is_other_parish(records) else ""

        def _filename_for(b) -> str:
            # A record's `k_year` (christening year, if different from
            # birth year) determines which book's file it belongs to.
            # Matches legacy's `year_of_christening` assignment — a Dec
            # birth with a Jan christening lands in the following year's
            # file. Falls back to records.year when k_year is unset.
            fy = getattr(b, "k_year", None) or records.year
            return f"mk_{fy}{other}_birth.tf"

        filename = f"mk_{records.year}{other}_birth.tf"
        doc = "mk_births"
        _recs: list[Any] = records.records
        sorted_records = sorted(
            _recs,
            key=lambda r: _chronological_key(r, records.year, "b_month", "b_day", "birth"),
        )
        for b in sorted_records:
            if not admitted(b):
                continue
            if b.child is None:
                continue
            # Per-record filename: a Dec-birth / Jan-christening rollover
            # (k_year set on the Birth) lands in the following year's
            # file while preserving the birth year for res_name / about.
            filename = _filename_for(b)
            # `year` is per-record so year-rollover entries (a December-of-
            # previous-year record that was christened in the current year's
            # book) carry the true birth year into their res_name. Most
            # records leave Birth.year=None and inherit from records.year.
            year = b.year or records.year
            is_christening = getattr(b, "is_christening", False)
            christening_age = getattr(b, "christening_age", None)
            month = _month_num(b.b_month)
            day = b.b_day
            # NB: res_name / document identifiers stay keyed on the birth
            # month/day (None day for a christening) so consolidation config
            # references remain stable — the christening date lives only on
            # the baptism event below.
            common = dict(year=year, month=month, day=day,
                          document_name=doc, record_number=b.record_num)

            # patr_modern is the orthographic patronymic when set; otherwise
            # derive from the father (no canonicalization to stay legacy-compatible).
            child_patr = b.child.patr_modern or b.derive_child_patronymic() or ""
            if not child_patr and b.father is not None:
                # derive_patronymic returns the canonical form; if we ever need
                # the orthographic form here we'd fall back differently.
                pass
            # Birth event lives at the family's home (father.residence →
            # mother.residence → parish fallback); baptism stays at the
            # parish church the book belongs to.
            parish_location = _location(records.village)
            birth_location = _location(b.get_birth_location(default=records.village))
            if christening_age is not None:
                # Birth date unknown — emit a circa birth year derived from
                # the age at christening (year - age). The baptism event below
                # carries the actual christening date.
                child_birth = _event(day=None, month=None, year=year - christening_age,
                                     location=birth_location, circa=True)
            elif is_christening:
                # Christening with no stated age: the birth date is unknown
                # and is NOT the christening year, so emit no birth date
                # (location only). The baptism event carries the real date.
                child_birth = _event(day=None, month=None, year=None, location=birth_location)
            else:
                child_birth = _event(day=b.b_day, month=month, year=year, location=birth_location)
            # A civil book registers the birth: its second date is no christening.
            child_baptism = None if _is_civil(records) else _event(
                day=b.k_day, month=_month_num(b.k_month) or month,
                year=getattr(b, "k_year", None) or year,
                location=parish_location,
            )
            event_location = parish_location  # retained name for downstream uses (document location)
            event_kind = "крещение" if is_christening else "рождение"
            about_lines = [f"<strong>{_book_tag(records)} {records.village} {year}:</strong> {event_kind}"]
            rendered_christening_age = format_age(christening_age)
            if rendered_christening_age:
                verb = "Крещён" if b.gender == Gender.MALE else "Крещена"
                about_lines.append(f"{verb} в возрасте {rendered_christening_age}")
            father_title = b.father.status if b.father is not None else None
            mother_title = b.mother.status if b.mother is not None else None
            if father_title:
                about_lines.append(f"Титул/звание отца: {father_title}")
            elif mother_title:
                # Legacy emits mother's title on child's about only when
                # father has no title (typically illegitimate births where
                # mother carries the only documented status).
                about_lines.append(f"Титул/звание матери: {mother_title}")
            # Legacy's 1810 CSV consistently populated the priest column
            # in Имена в МК (it followed the 4 participant columns with a
            # clergy column). Other years' legacy CSVs mostly left the
            # priest out of that transcription line. Include priest for
            # 1810 specifically; leave other years alone to avoid the
            # inconsistent per-record pattern in their CSVs.
            include_priest_in_mk = records.year == 1810
            priest_for_mk = b.priest if include_priest_in_mk else None
            relative_persons_for_mk = [r.person for r in b.relatives if r.person]
            # The newborn's patronymic `Birth.__init__` derived from the father is no word of the book (В10).
            child_for_mk = _shallow_person_without_patr(b.child) if b.child_patronymic_derived() else b.child
            names_in_mk = _names_in_mk(
                child_for_mk, b.father, b.mother,
                b.god_parent1, b.god_parent2,
                b.god_parent3, b.god_parent4,
                priest_for_mk,
                *relative_persons_for_mk,
            )
            notes = birth_notes(b)
            if names_in_mk or notes:
                about_lines.append("Комментарий из МК:")
                if names_in_mk:
                    about_lines.append(f">Имена в МК: {names_in_mk}")
                if notes:
                    about_lines.append(f">{notes}")
            # GeniProfile.to_terraform places the first line after 8 leading
            # spaces inside the trimspace(<<-EOT ...) block; subsequent lines
            # need the same indent so `terraform fmt` leaves the block aligned.
            child_about = ("\n" + " " * 8).join(about_lines)
            # Child's last_name (when not explicit in the DSL) is inherited
            # from parents by `Birth.__init__` — see births.py. Nothing
            # to do here; `_profile_from_person` just reads the value.
            child = self._profile_from_person(
                b.child, role="child", patr_override=child_patr,
                current_residence=_location(b.child.residence),
                birth=child_birth, baptism=child_baptism,
                source_date_error=getattr(b, "source_date_error", None),
                about=child_about, **common)
            self._emit_profile(filename, child)

            father = mother = None
            if b.father is not None:
                # Parent profiles carry an "отец ребенка" about block and a
                # `death = { range = "after"; circa = true; ... }` stub signaling
                # the parent was alive at the child's birth. Same enrichment
                # goes on the consolidated version when the father is in the
                # move list.
                father_about_lines = [
                    f"<strong>{_book_tag(records)} {records.village} {year}:</strong> отец ребенка"
                ]
                _father_age = parent_age_prose(b.father_age)
                if _father_age:
                    father_about_lines.append(f"Возраст при рождении ребёнка: {_father_age}")
                if b.father.status:
                    father_about_lines.append(f"Титул/звание: {b.father.status}")
                # The parent's own age stands on its line above; the comment stays plain so the age is not said twice.
                if names_in_mk or b.comment:
                    father_about_lines.append("Комментарий из МК:")
                    if names_in_mk:
                        father_about_lines.append(f">Имена в МК: {names_in_mk}")
                    if b.comment:
                        father_about_lines.append(f">{b.comment}")
                father_about = ("\n" + " " * 8).join(father_about_lines)
                father_death = GeniEvent(
                    date=GeniDate(
                        day=b.b_day, month=month, year=year,
                        date_range="after", circa=True,
                    ),
                )
                father = self._profile_from_person(
                    b.father, role="father",
                    current_residence=_location(b.father.residence),
                    about=father_about,
                    birth=parent_birth_estimate(year, Gender.MALE, record_year=year),
                    death=father_death,
                    **common)
                self._emit_profile(filename, father)
            if b.mother is not None:
                # Mirror father's enrichment: about block with "мать
                # ребенка" role label + alive-as-of-birth death stub.
                mother_about_lines = [
                    f"<strong>{_book_tag(records)} {records.village} {year}:</strong> мать ребенка"
                ]
                _mother_age = parent_age_prose(b.mother_age)
                if _mother_age:
                    mother_about_lines.append(f"Возраст при рождении ребёнка: {_mother_age}")
                if b.mother.status:
                    mother_about_lines.append(f"Титул/звание: {b.mother.status}")
                # The parent's own age stands on its line above; the comment stays plain so the age is not said twice.
                if names_in_mk or b.comment:
                    mother_about_lines.append("Комментарий из МК:")
                    if names_in_mk:
                        mother_about_lines.append(f">Имена в МК: {names_in_mk}")
                    if b.comment:
                        mother_about_lines.append(f">{b.comment}")
                mother_about = ("\n" + " " * 8).join(mother_about_lines)
                mother_death = GeniEvent(
                    date=GeniDate(
                        day=b.b_day, month=month, year=year,
                        date_range="after",
                    ),
                )
                mother = self._profile_from_person(
                    b.mother, role="mother",
                    current_residence=_location(b.mother.residence),
                    about=mother_about,
                    birth=parent_birth_estimate(year, Gender.FEMALE, record_year=year),
                    death=mother_death,
                    **common)
                self._emit_profile(filename, mother)

            if father is not None or mother is not None:
                # Always build the family union; `_route_union` decides per
                # partner-consolidation whether it goes to the per-year file
                # or to `consolidated_unions.tf`.
                # Legacy union res_name format:
                #   "{father_first} {father_mid} {father_last}
                #    [and {mother_first} {mother_mid} {mother_last}]
                #    {record_number} {year}"
                # passed through generate_res_name → `ivan_petrovich__2_1800`.
                # The earlier generator builds one f-string with a fixed
                # slot for the "and {mother}" group, then does one-pass
                # `.replace("  ", " ")`. That collapses pairs but not triples:
                # father-only case has 3 consecutive spaces (empty last_name +
                # empty mother slot) → 2 spaces → `__` in res_name.
                father_part = (
                    f"{father.first_name} {father.middle_name} {father.last_name}"
                    if father is not None else "  "
                )
                mother_part = (
                    f"and {mother.first_name} {mother.middle_name} {mother.last_name}"
                    if mother is not None else ""
                )
                raw = f"{father_part} {mother_part} {b.record_num} {year}"
                union_res_name = generate_res_name(raw.strip().replace("  ", " "))
                union = GeniUnion(
                    origin=UnionOrigin.BIRTH,
                    res_name=union_res_name,
                    partner_1=self.consolidation.move_to_new_name(father.res_name) if father else None,
                    partner_2=self.consolidation.move_to_new_name(mother.res_name) if mother else None,
                    children={self.consolidation.move_to_new_name(child.res_name)},
                )
                # Route to consolidated bucket when ANY participant
                # (father, mother, OR child) is in profile_move_list.
                # Mirrors legacy's `at_least_one_consolidated_profile`
                # which includes
                # children — without considering children, an MK birth
                # whose father is a per-record stub (not consolidated)
                # but whose child IS consolidated (e.g. father=Прохор stub,
                # child=Татьяна Прохоровна → in a `tatjana_prohorovna`
                # consolidation) routes to per-
                # year file. Legacy routed it to consolidated_unions.tf.
                consolidated_partner = (
                    (father is not None and self.consolidation.in_profile_move_list(father.res_name))
                    or (mother is not None and self.consolidation.in_profile_move_list(mother.res_name))
                    or self.consolidation.in_profile_move_list(child.res_name)
                )
                self._route_union(
                    union, filename=filename, is_consolidated=consolidated_partner,
                )

            # Godparent profile enrichment — mirrors
            # the earlier generator. A godparent is an
            # adult sponsor at the christening, so legacy estimates their
            # birth within [year-60, year-6] and stamps a death = "after"
            # the christening date. The `about` block declares the role
            # and carries the status and МК comment.
            christening_day = b.k_day if b.k_day is not None else b.b_day
            christening_month = _month_num(b.k_month) or month
            christening_year = getattr(b, "k_year", None) or year
            gp_birth_range = adult_birth_window(year, min_age=6)
            gp_death_after = GeniEvent(
                date=GeniDate(
                    day=christening_day, month=christening_month,
                    year=christening_year, date_range="after",
                ),
            )

            gp1 = gp2 = gp3 = gp4 = None
            gp_profiles_by_pos: list[GeniProfile | None] = [None, None, None, None]
            for pos, gp_person in (
                (1, b.god_parent1), (2, b.god_parent2),
                (3, b.god_parent3), (4, b.god_parent4),
            ):
                if gp_person is None:
                    continue
                profile = self._profile_from_person(
                    gp_person, role=f"god_parent_{pos}",
                    current_residence=_location(gp_person.residence),
                    birth=gp_birth_range,
                    death=gp_death_after,
                    about=self._build_godparent_about(
                        gp_person, records.village, year, names_in_mk, notes,
                    ),
                    **common)
                self._emit_profile(filename, profile)
                gp_profiles_by_pos[pos - 1] = profile
            gp1, gp2, gp3, gp4 = gp_profiles_by_pos

            # Legacy `god_parent_rel`
            # is invoked ONLY when the source CSV row has
            # `Чей родств.N == "восприемника №N"` — i.e., when there's
            # an EXPLICIT `relative` whose `relationship_ref` references
            # a specific godparent. The relative-ref case is handled
            # below by the `gprel_union` loop (which uses the relative,
            # not the parent, as partner_1).
            #
            # An earlier version of this code emitted an aux
            # `<father>_and_<godparent>` (or `<mother> <godparent>` with
            # godparent as child) union for EVERY godparent + parent
            # pair, regardless of relative refs. Legacy never emits
            # those, and the female-godparent branch leaked the
            # godparent into the parents' marriage-union children list
            # via partner-lookup consolidation (e.g.
            # `_<date>_marina_andreevna_mk_births_41_god_parent_2`
            # ending up as a "child" of the parents). Removed.

            def _rel_about(rel, *, _year=year, _notes=notes,
                           _names_in_mk=names_in_mk):
                """Legacy parity:
                relatives tied to a godparent get an `about` block with
                role label `{rel_type} восприемника на крещении`."""
                if not rel.relationship_ref or not rel.relationship_ref.startswith(
                    "восприемника №"
                ):
                    return None
                rel_type = rel.relationship.value if rel.relationship else ""
                lines = [
                    f"<strong>МК {records.village} {_year}:</strong> "
                    f"{rel_type + ' ' if rel_type else ''}восприемника на крещении"
                ]
                if rel.person.status:
                    lines.append(f"Титул/звание: {rel.person.status}")
                if _names_in_mk or _notes:
                    lines.append("Комментарий из МК:")
                    if _names_in_mk:
                        lines.append(f">Имена в МК: {_names_in_mk}")
                    if _notes:
                        lines.append(f">{_notes}")
                return ("\n" + " " * 8).join(lines)

            relative_profiles = self._emit_relatives(
                filename, b.relatives,
                year=year, month=month, day=day,
                document_name=doc, record_number=b.record_num,
                about_for=_rel_about,
            )

            # Per-relative union linking the relative to a referenced in-record
            # subject (currently god_parent_N). Mirrors legacy `god_parent_rel`.
            # Spouse-style
            # relationships (HUSBAND/WIFE) emit a partner-pair union; all
            # others (FATHER/MOTHER/etc.) emit a single-parent union with the
            # godparent in the children set.
            from verso.ru.relationship import Relationship as _Relationship
            gp_by_index = {1: gp1, 2: gp2, 3: gp3, 4: gp4}
            for rel, rel_profile in zip(b.relatives or [], relative_profiles, strict=False):
                if rel is None or rel_profile is None:
                    continue
                ref = rel.relationship_ref or ""
                m = re.match(r"восприемника №(\d+)$", ref)
                if m:
                    target = gp_by_index.get(int(m.group(1)))
                elif ref == "мать":
                    # The mother's own father or husband, named in her own
                    # right — the shape незаконнорождённые births take, where
                    # the entry names her kin instead of a father for the child.
                    target = mother
                else:
                    continue
                if target is None:
                    continue
                rel_parts = [rel_profile.first_name, rel_profile.middle_name]
                if rel_profile.last_name:
                    rel_parts.append(rel_profile.last_name)
                rel_parts.append("and")
                rel_parts.extend([target.first_name, target.middle_name])
                if target.last_name:
                    rel_parts.append(target.last_name)
                rel_parts.extend([str(b.record_num), str(year)])
                gprel_union_res_name = generate_res_name(
                    " ".join(rel_parts).strip().replace("  ", " "),
                )
                is_spouse = rel.relationship in (
                    _Relationship.HUSBAND, _Relationship.WIFE,
                )
                gprel_union = GeniUnion(
                    res_name=gprel_union_res_name,
                    partner_1=self.consolidation.move_to_new_name(rel_profile.res_name),
                    partner_2=(self.consolidation.move_to_new_name(target.res_name)
                               if is_spouse else None),
                    children=(set() if is_spouse
                              else {self.consolidation.move_to_new_name(target.res_name)}),
                )
                gprel_consolidated = (
                    self.consolidation.in_profile_move_list(rel_profile.res_name)
                    or self.consolidation.in_profile_move_list(target.res_name)
                )
                self._route_union(
                    gprel_union, filename=filename,
                    is_consolidated=gprel_consolidated,
                )

            # Clergy (priest/deacon/dyachok/sexton) are intentionally NOT
            # emitted as geni_profile resources — the earlier generator
            # never did, so suppressing them
            # here keeps byte-parity with its .tf output.

            # geni_document for the birth event. Legacy's `profiles = [...]`
            # includes every emitted profile for the record: child, parents,
            # godparents, AND any relatives.
            doc_profiles = [child.res_name]
            if father is not None: doc_profiles.append(father.res_name)
            if mother is not None: doc_profiles.append(mother.res_name)
            if gp1 is not None: doc_profiles.append(gp1.res_name)
            if gp2 is not None: doc_profiles.append(gp2.res_name)
            if gp3 is not None: doc_profiles.append(gp3.res_name)
            if gp4 is not None: doc_profiles.append(gp4.res_name)
            for rp in relative_profiles:
                if rp is not None:
                    doc_profiles.append(rp.res_name)

            # Legacy's year-usage for cross-year records is asymmetric:
            #   - res_name           → birth year (`year`)
            #   - title              → christening year (`k_year`)
            #   - description body   → birth year (`year`)
            # Mirror exactly.
            doc_title_year = getattr(b, "k_year", None) or year
            doc_res_name = generate_res_name(
                f"Birth of {child.first_name}{' ' + child.middle_name if child.middle_name else ''} {b.record_num} {year}"
            )
            self._document_for_record[b] = doc_res_name
            # Per-page inventory/case overrides win over the records
            # container defaults (legacy carries this at page level).
            doc_archive = getattr(b, "archive", None) or records.archive
            doc_fund = getattr(b, "fund", None) or records.fund
            doc_inventory = b.inventory or records.inventory
            doc_case = b.case or records.case
            desc_lines = [
                f"{_book_title(records)} {records.village} {year}: {event_kind} {child.first_name}",
                f"Архив: {doc_archive}",
                f"Фонд: {doc_fund}",
                f"Опись: {doc_inventory}",
                f"Дело: {doc_case}",
            ]
            # Legacy always emits a `Лист:` label; value is blank when the
            # page is unknown (`"?"` DSL placeholder or missing). Matches the
            # marriage/death document builders below.
            if b.page and b.page != "?":
                desc_lines.append(f"Лист: {b.page}")
            else:
                desc_lines.append("Лист:")
            desc_lines.append(f"№ записи: {b.record_num}")
            description = "\n".join(f"        {line}" for line in desc_lines)

            # Extended text body: dates, child name, parents.
            # Legacy uses k_year (book/christening year) in the text
            # body's first line, even though the description above uses
            # b.year. Override the first line accordingly.
            text_lines = list(desc_lines) + [""]
            text_lines[0] = (
                f"{_book_title(records)} {records.village} {doc_title_year}: "
                f"{event_kind} {child.first_name}"
            )
            bd = b.b_day if b.b_day is not None else "?"
            bm = b.b_month.value if b.b_month else "?"
            if is_christening:
                # No recorded birth date. With a known age, note the circa
                # birth year; otherwise omit the birth-date line entirely.
                if christening_age is not None:
                    text_lines.append(
                        f"Дата рождения: около {year - christening_age} г. "
                        f"(возраст при крещении: {christening_age})"
                    )
            else:
                text_lines.append(f"Дата рождения: {bd}.{bm}.{year}")
            kd = b.k_day if b.k_day is not None else "?"
            km = (b.k_month.value if b.k_month else None) or bm
            ky = getattr(b, "k_year", None) or year
            if not _is_civil(records):
                text_lines.append(f"Дата крещения: {kd}.{km}.{ky}")
            elif b.k_day is not None:
                # A civil book's second date is the registration; one it did not
                # write is not printed — its month is only the section's.
                text_lines.append(f"Дата регистрации: {kd}.{km}.{ky}")
            text_lines.append(f"Ребенок: {child.first_name}")
            if b.father is not None:
                text_lines.append(
                    "Отец: " + _mk_doc_name_line(b.father, father)
                )
            if b.mother is not None and mother is not None:
                text_lines.append(
                    "Мать: " + _mk_doc_name_line(b.mother, mother)
                )
            # Legacy writes `Воспреемник 1:` / `Воспреемник 2:` lines for
            # each godparent present, in the same shape as Отец/Мать —
            # status + canonical first + canonical patronymic + last_name.
            # When the godparent's residence differs from the parish
            # village, legacy appends ` ({residence})` as a suffix (Отец /
            # Мать do NOT get the same suffix even when they live outside).
            for idx, gp, gp_profile in (
                (1, b.god_parent1, gp1),
                (2, b.god_parent2, gp2),
                (3, b.god_parent3, gp3),
                (4, b.god_parent4, gp4),
            ):
                if gp is None or gp_profile is None:
                    continue
                line = f"Воспреемник {idx}: " + _mk_doc_name_line(
                    gp, gp_profile,
                )
                if gp.residence and gp.residence != records.village:
                    line += f" ({gp.residence})"
                text_lines.append(line)
            # Legacy splits these across two lines: `Комментарий: {general}`
            # (reconstructed here as "Имена в МК: ...") and `Пометки: {notes}`
            # (DSL's birth.comment). One blank separator before whichever
            # appears first.
            if names_in_mk or notes:
                text_lines.append("")
            if names_in_mk:
                text_lines.append(f"Комментарий: Имена в МК: {names_in_mk}")
            if notes:
                text_lines.append(f"Пометки: {notes}")
            text = "\n".join(f"        {line}" if line else line for line in text_lines)
            self._outputs[filename] += _document_resource(
                res_name=doc_res_name,
                title=f"{_book_title(records)} {records.village} {doc_title_year}: {event_kind} {child.first_name}",
                description=description,
                text=text,
                date_day=b.b_day,
                date_month=month,
                date_year=year,
                labels=["Birth"],
                location=event_location,
                profiles=[self.consolidation.move_to_new_name(p) for p in doc_profiles],
                # Legacy uses the parent's residence (location_of_birth) for
                # project rules on the birth document — NOT the parish.
                projects=self._projects_for_location(birth_location),
            )

    def add_marriage_records(self, records) -> None:
        other = "_other" if self._is_other_parish(records) else ""
        filename = f"mk_{records.year}{other}_marriage.tf"
        doc = "mk_marriages"
        # Sort: by per-month record_num (primary), chronological (tiebreaker).
        def _marriage_sort_key(r):
            rec_year = r.year or records.year
            book_num = self._marriage_book_record_num(r)
            return (rec_year, book_num,
                    _chronological_key(r, records.year, "w_month",
                                       "w_day", "marriage"))
        sorted_records = sorted(records.records, key=_marriage_sort_key)
        for m in sorted_records:
            if not admitted(m):
                continue
            # Per-record year — rollover case (see add_birth_records).
            year = m.year or records.year
            month = _month_num(m.w_month)
            day = m.w_day
            common = dict(year=year, month=month, day=day,
                          document_name=doc, record_number=m.record_num)

            parish_village = getattr(m, "village", None) or records.village
            parish_location = _location(parish_village)

            relative_persons_for_mk = [r.person for r in (m.relatives or []) if r.person]
            names_in_mk = _names_in_mk(
                m.groom, m.bride,
                m.witness1, m.witness2, m.witness3, m.witness4,
                m.witness5, m.witness6,
                *relative_persons_for_mk,
            )

            # Default-arg binding below captures loop vars at function-
            # definition time rather than at call time; both helpers are
            # only invoked within the same iteration so semantics are
            # unchanged, but it silences ruff B023.
            def _partner_birth_year(age, *, year=year, month=month, day=day):
                """The partner's birth year derived from their stated age, or
                None when the record gives no usable age.

                When age has a fractional months component (e.g. DSL gives
                `groom_age="18 лет 6 мес"`), subtract the full age from
                the wedding date so the year is correct: 1915-01-19 minus
                18y6m = 1896-07-19, so the birth year is 1896 — not 1897,
                which a naive `int(age_years)` truncation would yield.
                """
                age_years = _age_to_years(age)
                if age_years is None:
                    return None
                from datetime import date as _date
                from dateutil.relativedelta import relativedelta as _rd
                years_part = int(age_years)
                months_part = round((age_years - years_part) * 12)
                anchor = _date(int(year), int(month or 1), int(day or 1))
                return (anchor - _rd(years=years_part, months=months_part)).year

            def _partner_birth(age, loc, *, year=year):
                # Single circa year when age is known; broad "between" range
                # (year-60 .. year-13) when age is unknown — mirrors
                # the earlier generator.
                birth_year = _partner_birth_year(age)
                if birth_year is not None:
                    return GeniEvent(date=GeniDate(year=birth_year, circa=True),
                                     location=loc)
                event = adult_birth_window(year, min_age=13)
                event.location = loc
                return event

            partner_death = GeniEvent(
                date=GeniDate(day=day, month=month, year=year, date_range="after"),
            )

            def _partner_about(person, role_label, age=None, *, year=year,
                               names_in_mk=names_in_mk, m=m,
                               parish_village=parish_village):
                lines = [f"<strong>{_book_tag(records)} {parish_village} {year}:</strong> {role_label}"]
                rendered_age = format_age(age)
                if rendered_age:
                    lines.append(f"Возраст: {rendered_age}")
                if person.status:
                    lines.append(f"Титул/звание: {person.status}")
                if names_in_mk or m.comment:
                    lines.append("Комментарий из МК:")
                    if names_in_mk:
                        lines.append(f">Имена в МК: {names_in_mk}")
                    if m.comment:
                        lines.append(f">{m.comment}")
                return ("\n" + " " * 8).join(lines)

            # Extract bride/groom father relatives for the inline
            # _partner_about emission and the generic `_emit_relatives` call.
            # A partner's missing patronymic is backfilled from the father's
            # first name by `Marriage.derive_partner_patronymic` (as a
            # newborn's is by `Birth.derive_child_patronymic`).
            groom_father_rel = None
            bride_father_rel = None
            # Bride's deceased prior husband (widow remarrying). Legacy
            # routes this through the same `_bf` emission as bride-father
            # but emits a husband+wife union (partner_2=bride) instead of
            # a father→child one.
            bride_prior_husband_rel = None
            other_relatives: list[Any] = []
            for rel in m.relatives or []:
                if rel is None or rel.person is None:
                    other_relatives.append(rel)
                    continue
                if rel.relationship == Relationship.FATHER:
                    if rel.relationship_ref == "жених" and groom_father_rel is None:
                        groom_father_rel = rel
                        continue
                    if rel.relationship_ref == "невеста" and bride_father_rel is None:
                        bride_father_rel = rel
                        continue
                if rel.relationship == Relationship.HUSBAND:
                    if rel.relationship_ref == "невеста" and bride_prior_husband_rel is None:
                        bride_prior_husband_rel = rel
                        continue
                other_relatives.append(rel)

            groom_patr_override = m.derive_partner_patronymic(m.groom)
            bride_patr_override = m.derive_partner_patronymic(m.bride)

            groom = bride = None
            if m.groom is not None:
                groom_res = _location(m.groom.residence)
                groom = self._profile_from_person(
                    m.groom, role="groom",
                    current_residence=groom_res,
                    birth=_partner_birth(m.groom_age, groom_res),
                    death=partner_death,
                    about=_partner_about(m.groom, "жених", m.groom_age),
                    patr_override=groom_patr_override,
                    **common,
                )
                self._emit_profile(filename, groom)
            bride_last_override = None  # bound here so the doc-context use below is safe
            if m.bride is not None:
                bride_res = _location(m.bride.residence)
                # When the DSL marks the bride as taking the groom's surname,
                # emit the bride profile with the groom's feminized surname
                # as `last_name` and keep her maiden surname as
                # `birth_last_name`. The res_name embeds the married surname
                # too — this matches the legacy consolidation key.
                bride_birth_last_override = None
                if getattr(m, "bride_takes_groom_surname", False):
                    if m.groom is not None and (m.groom.last_name_modern or m.groom.last_name):
                        groom_last = m.groom.last_name_modern or m.groom.last_name
                        bride_last_override = feminize_surname(groom_last)
                        bride_birth_last_override = m.bride.last_name_modern or ""
                    elif m.bride.last_name_modern:
                        # Groom's surname is unknown but bride's surname was
                        # deduced from her father (last_name_in_book=False).
                        # Treat it as her maiden surname; leave last_name empty.
                        bride_last_override = ""
                        bride_birth_last_override = m.bride.last_name_modern
                bride = self._profile_from_person(
                    m.bride, role="bride",
                    current_residence=bride_res,
                    birth=_partner_birth(m.bride_age, bride_res),
                    death=partner_death,
                    about=_partner_about(m.bride, "невеста", m.bride_age),
                    patr_override=bride_patr_override,
                    last_name_override=bride_last_override,
                    birth_last_name_override=bride_birth_last_override,
                    **common,
                )
                self._emit_profile(filename, bride)

            # In document-context strings (union/doc res_names, title,
            # partner line) we always render the bride's MAIDEN surname —
            # legacy keys every such reference on who she was *at* the
            # wedding. When the married-surname override actually fired
            # above, `bride.last_name` holds the married surname and
            # `bride.birth_last_name` the maiden (possibly empty). When
            # the override did NOT fire (flag unset, or flag set but the
            # groom has no surname to feminize), `bride.last_name` still
            # holds her own — use it directly.
            if bride is not None and bride_last_override is not None:
                bride_doc_last = bride.birth_last_name
            elif bride is not None:
                bride_doc_last = bride.last_name
            else:
                bride_doc_last = ""

            # Marriage union — always build; `_route_union` chooses per-year
            # vs consolidated routing based on partner consolidation.
            if groom is not None or bride is not None:
                # Empty last_name slots would leave double-spaces → double
                # underscores in the final res_name. Filter empties (legacy
                # achieves the same via `.replace("  ", " ")` at the end).
                groom_fio = " ".join(x for x in [
                    groom.first_name, groom.middle_name, groom.last_name
                ] if x) if groom is not None else ""
                bride_fio = " ".join(x for x in [
                    bride.first_name, bride.middle_name, bride_doc_last
                ] if x) if bride is not None else ""
                raw = groom_fio
                if bride_fio:
                    raw += f" and {bride_fio}" if raw else bride_fio
                raw += f" m{m.record_num} {year}"
                union_res_name = generate_res_name(raw.strip())
                marriage_event = _event(
                    day=day, month=month, year=year, location=parish_location,
                )
                # The geni_union resource requires at least two profiles
                # (partners or children). Marriage records have no children,
                # so skip union emission when only one partner is present —
                # e.g. a marriage where the source explicitly notes
                # "имя невесты не указано в записи".
                if groom is not None and bride is not None:
                    union = GeniUnion(
                        origin=UnionOrigin.MARRIAGE,
                        res_name=union_res_name,
                        partner_1=self.consolidation.move_to_new_name(groom.res_name),
                        partner_2=self.consolidation.move_to_new_name(bride.res_name),
                        marriage=marriage_event,
                    )
                    consolidated_partner = (
                        self.consolidation.in_profile_move_list(groom.res_name)
                        or self.consolidation.in_profile_move_list(bride.res_name)
                    )
                    self._route_union(
                        union, filename=filename, is_consolidated=consolidated_partner,
                    )

            # Marriage-parent (father-of-groom / father-of-bride) profiles.
            # Legacy emits a male profile for each populated `Отец жениха`
            # / `Отец невесты` block, then a `bf` (= bride/groom-father)
            # union linking father → child as a single-parent family.
            # The DSL surfaces
            # these via `relatives=[relative(p, Relationship.FATHER, ref)]`
            # where `ref` is "жених" / "невеста"; we pop those entries
            # out of `m.relatives` here so `_emit_relatives` below does
            # not double-emit them as generic `rel_N` profiles. Roles
            # use legacy suffixes `groom_father` and `bride_relative` so
            # the consolidation move-list keys keep matching.
            groom_father_profile = None
            if groom_father_rel is not None and groom is not None:
                gf_person = groom_father_rel.person
                groom_father_profile = self._profile_from_person(
                    gf_person, role="groom_father",
                    current_residence=_location(gf_person.residence),
                    about=_partner_about(gf_person, "отец жениха"),
                    birth=parent_birth_estimate(
                        _partner_birth_year(m.groom_age), Gender.MALE,
                        record_year=year,
                    ),
                    **common,
                )
                self._emit_profile(filename, groom_father_profile)
                gf_parts = [
                    groom_father_profile.first_name,
                    groom_father_profile.middle_name,
                ]
                if groom_father_profile.last_name:
                    gf_parts.append(groom_father_profile.last_name)
                gf_parts.append("and")
                gf_parts.extend([groom.first_name, groom.middle_name])
                if groom.last_name:
                    gf_parts.append(groom.last_name)
                gf_parts.extend([f"m{m.record_num}", str(year), "bf"])
                gf_union_res_name = generate_res_name(
                    " ".join(gf_parts).strip().replace("  ", " "),
                )
                gf_union = GeniUnion(
                    res_name=gf_union_res_name,
                    partner_1=self.consolidation.move_to_new_name(groom_father_profile.res_name),
                    children={self.consolidation.move_to_new_name(groom.res_name)},
                )
                gf_consolidated = (
                    self.consolidation.in_profile_move_list(groom_father_profile.res_name)
                    or self.consolidation.in_profile_move_list(groom.res_name)
                )
                self._route_union(
                    gf_union, filename=filename, is_consolidated=gf_consolidated,
                )

            bride_father_profile = None
            if bride_father_rel is not None and bride is not None:
                bf_person = bride_father_rel.person
                bride_father_profile = self._profile_from_person(
                    bf_person, role="bride_relative",
                    current_residence=_location(bf_person.residence),
                    about=_partner_about(bf_person, "отец невесты"),
                    birth=parent_birth_estimate(
                        _partner_birth_year(m.bride_age), Gender.MALE,
                        record_year=year,
                    ),
                    **common,
                )
                self._emit_profile(filename, bride_father_profile)
                bf_parts = [
                    bride_father_profile.first_name,
                    bride_father_profile.middle_name,
                ]
                if bride_father_profile.last_name:
                    bf_parts.append(bride_father_profile.last_name)
                bf_parts.append("and")
                bf_parts.extend([bride.first_name, bride.middle_name])
                # Bride uses her MAIDEN surname in the union res_name
                # (legacy: `bride_birth_last_name`).
                if bride_doc_last:
                    bf_parts.append(bride_doc_last)
                bf_parts.extend([f"m{m.record_num}", str(year), "bf"])
                bf_union_res_name = generate_res_name(
                    " ".join(bf_parts).strip().replace("  ", " "),
                )
                bf_union = GeniUnion(
                    res_name=bf_union_res_name,
                    partner_1=self.consolidation.move_to_new_name(bride_father_profile.res_name),
                    children={self.consolidation.move_to_new_name(bride.res_name)},
                )
                bf_consolidated = (
                    self.consolidation.in_profile_move_list(bride_father_profile.res_name)
                    or self.consolidation.in_profile_move_list(bride.res_name)
                )
                self._route_union(
                    bf_union, filename=filename, is_consolidated=bf_consolidated,
                )

            # Widow's prior union: same `_bf` resource shape as bride-father,
            # but partner_2=bride instead of children={bride}. Emitted when a
            # marriage record names the bride's deceased first husband as a
            # relative (Relationship.HUSBAND, ref="невеста").
            bride_prior_husband_profile = None
            if bride_prior_husband_rel is not None and bride is not None:
                bh_person = bride_prior_husband_rel.person
                bride_prior_husband_profile = self._profile_from_person(
                    bh_person, role="bride_relative",
                    current_residence=_location(bh_person.residence),
                    about=_partner_about(bh_person, "муж невесты"),
                    **common,
                )
                self._emit_profile(filename, bride_prior_husband_profile)
                bh_parts = [
                    bride_prior_husband_profile.first_name,
                    bride_prior_husband_profile.middle_name,
                ]
                if bride_prior_husband_profile.last_name:
                    bh_parts.append(bride_prior_husband_profile.last_name)
                bh_parts.append("and")
                bh_parts.extend([bride.first_name, bride.middle_name])
                if bride_doc_last:
                    bh_parts.append(bride_doc_last)
                bh_parts.extend([f"m{m.record_num}", str(year), "bf"])
                bh_union_res_name = generate_res_name(
                    " ".join(bh_parts).strip().replace("  ", " "),
                )
                bh_union = GeniUnion(
                    res_name=bh_union_res_name,
                    partner_1=self.consolidation.move_to_new_name(bride_prior_husband_profile.res_name),
                    partner_2=self.consolidation.move_to_new_name(bride.res_name),
                )
                bh_consolidated = (
                    self.consolidation.in_profile_move_list(bride_prior_husband_profile.res_name)
                    or self.consolidation.in_profile_move_list(bride.res_name)
                )
                self._route_union(
                    bh_union, filename=filename, is_consolidated=bh_consolidated,
                )

            # Witness/поручитель enrichment: adult-age birth estimate,
            # alive-as-of-marriage death stub, about block. Legacy emits
            # these on every witness profile.
            witness_birth = adult_birth_window(year, min_age=17)
            witness_death = GeniEvent(
                date=GeniDate(day=day, month=month, year=year,
                              date_range="after"),
            )

            def _build_witness_about(w_person, *, village=parish_village,
                                     year=year, names_in_mk=names_in_mk,
                                     comment=m.comment):
                lines = [
                    f"<strong>{_book_tag(records)} {village} {year}:</strong> поручитель на свадьбе"
                ]
                if w_person.status:
                    lines.append(f"Титул/звание: {w_person.status}")
                if names_in_mk or comment:
                    lines.append("Комментарий из МК:")
                    if names_in_mk:
                        lines.append(f">Имена в МК: {names_in_mk}")
                    if comment:
                        lines.append(f">{comment}")
                return ("\n" + " " * 8).join(lines)

            witness_profiles: list[GeniProfile | None] = []
            for i, witness in enumerate(
                    [m.witness1, m.witness2, m.witness3, m.witness4,
                     m.witness5, m.witness6], start=1):
                if witness is None:
                    witness_profiles.append(None)
                    continue
                w_profile = self._profile_from_person(
                    witness, role=f"witness_{i}",
                    current_residence=_location(witness.residence),
                    birth=witness_birth,
                    death=witness_death,
                    about=_build_witness_about(witness),
                    **common)
                self._emit_profile(filename, w_profile)
                witness_profiles.append(w_profile)

            # Generic marriage relatives (siblings, mothers, FATHERS without
            # жених/невеста ref, etc.) — emit through `_emit_relatives` with
            # an about_for callback mirroring `_partner_about` (fathers) and
            # `_build_witness_about` (witnesses), so they aren't bare profiles.
            _ref_genitive = {"жених": "жениха", "невеста": "невесты"}

            def _witness_ref_genitive(ref_raw, _m=m):
                """«поручитель №6» → «поручительницы №6» / «поручителя №6».

                Поручитель is what the marriage books call a wedding witness.
                The about line reads «{родство} {кого}», so the ref has to be
                genitive and agree with them: a дьячок is the husband of a
                поручительницы. Returns None for any other ref.
                """
                witness = re.match(r"^поручитель №(\d+)$", ref_raw)
                if not witness:
                    return None
                index = int(witness.group(1))
                target = getattr(_m, f"witness{index}", None)
                female = target is not None and target.gender == Gender.FEMALE
                return f"поручительницы №{index}" if female else f"поручителя №{index}"

            def _marriage_rel_about(rel, *, _year=year, _m=m,
                                    _names_in_mk=names_in_mk,
                                    _village=parish_village,
                                    _ref_genitive=_ref_genitive,
                                    _witness_genitive=_witness_ref_genitive):
                rel_type = rel.relationship.value if rel.relationship else "родственник"
                ref_raw = rel.relationship_ref or ""
                ref_gen = (_witness_genitive(ref_raw)
                           or _ref_genitive.get(ref_raw, ref_raw))
                role = f"{rel_type} {ref_gen}" if ref_gen else f"{rel_type} на свадьбе"
                lines = [f"<strong>{_book_tag(records)} {_village} {_year}:</strong> {role}"]
                if rel.person.status:
                    lines.append(f"Титул/звание: {rel.person.status}")
                if _names_in_mk or _m.comment:
                    lines.append("Комментарий из МК:")
                    if _names_in_mk:
                        lines.append(f">Имена в МК: {_names_in_mk}")
                    if _m.comment:
                        lines.append(f">{_m.comment}")
                return ("\n" + " " * 8).join(lines)

            def _marriage_rel_birth(rel, *, _m=m, _year=year):
                # Only parents get an estimate, and only when we know WHOSE
                # parent they are — the anchor is that partner's birth year.
                # Siblings, in-laws and unreferenced relatives stay bare.
                if not is_parent_relationship(rel.relationship):
                    return None
                if rel.relationship_ref == "жених":
                    age = _m.groom_age
                elif rel.relationship_ref == "невеста":
                    age = _m.bride_age
                else:
                    return None
                return parent_birth_estimate(
                    _partner_birth_year(age),
                    PARENT_RELATIONSHIP_GENDER[rel.relationship],
                    record_year=_year,
                )

            marriage_relative_profiles = self._emit_relatives(
                filename, other_relatives,
                year=year, month=month, day=day,
                document_name=doc, record_number=m.record_num,
                about_for=_marriage_rel_about,
                birth_for=_marriage_rel_birth,
            )
            # Per-relative union tying a relative to the поручитель they are
            # refd to («поручитель №N»), the marriage counterpart of the
            # godparent wiring in add_birth_records. Without it the relative —
            # typically the husband of a woman standing as witness — is emitted
            # as a profile with no edge to her.
            for rel, rel_profile in zip(other_relatives, marriage_relative_profiles,
                                        strict=False):
                if rel is None or rel_profile is None:
                    continue
                wm = re.match(r"поручитель №(\d+)$", rel.relationship_ref or "")
                if not wm:
                    continue
                index = int(wm.group(1))
                target = (witness_profiles[index - 1]
                          if 0 < index <= len(witness_profiles) else None)
                if target is None:
                    continue
                parts = [rel_profile.first_name, rel_profile.middle_name]
                if rel_profile.last_name:
                    parts.append(rel_profile.last_name)
                parts.append("and")
                parts.extend([target.first_name, target.middle_name])
                if target.last_name:
                    parts.append(target.last_name)
                parts.extend([str(m.record_num), str(year)])
                is_spouse = rel.relationship in (Relationship.HUSBAND, Relationship.WIFE)
                wrel_union = GeniUnion(
                    res_name=generate_res_name(" ".join(parts).strip().replace("  ", " ")),
                    partner_1=self.consolidation.move_to_new_name(rel_profile.res_name),
                    partner_2=(self.consolidation.move_to_new_name(target.res_name)
                               if is_spouse else None),
                    children=(set() if is_spouse
                              else {self.consolidation.move_to_new_name(target.res_name)}),
                )
                self._route_union(
                    wrel_union, filename=filename,
                    is_consolidated=(
                        self.consolidation.in_profile_move_list(rel_profile.res_name)
                        or self.consolidation.in_profile_move_list(target.res_name)),
                )

            # Clergy profiles suppressed for legacy byte-parity (see
            # add_birth_records for rationale).

            # geni_document for the marriage event.
            if groom is None and bride is None:
                continue

            groom_fio_parts = []
            if groom is not None:
                groom_fio_parts = [groom.first_name, groom.middle_name, groom.last_name]
            bride_fio_parts = []
            if bride is not None:
                bride_fio_parts = [bride.first_name, bride.middle_name, bride_doc_last]
            groom_fio = " ".join(x for x in groom_fio_parts if x)
            bride_fio = " ".join(x for x in bride_fio_parts if x)
            title_ru_parts = [groom_fio]
            if bride_fio:
                title_ru_parts.append(f"и {bride_fio}")
            title_ru = " ".join(p for p in title_ru_parts if p)

            # Document res_name — legacy prefixes the record_num with "m" to
            # disambiguate from same-year birth/death docs.
            # Format:
            #   `Marriage of {groom_first} {groom_mid} {groom_last}
            #    [and {bride_first} {bride_mid} {bride_birth_last}]
            #    m{record_num} {year}`.
            # Bride uses her BIRTH (maiden) surname, which in DSL terms is
            # `bride.last_name_orig` → maps to Person.last_name.
            res_name_parts = ["Marriage of"]
            if groom is not None:
                if groom.first_name:
                    res_name_parts.append(groom.first_name)
                if groom.middle_name:
                    res_name_parts.append(groom.middle_name)
                if groom.last_name:
                    res_name_parts.append(groom.last_name)
            if bride is not None:
                res_name_parts.append("and")
                if bride.first_name:
                    res_name_parts.append(bride.first_name)
                if bride.middle_name:
                    res_name_parts.append(bride.middle_name)
                if bride_doc_last:
                    res_name_parts.append(bride_doc_last)
            res_name_parts.append(f"m{m.record_num}")
            res_name_parts.append(str(year))
            doc_res_name = generate_res_name(" ".join(res_name_parts))
            self._document_for_record[m] = doc_res_name

            desc_lines = [
                f"{_book_title(records)} {parish_village} {year}: брак {title_ru}",
                f"Архив: {getattr(m, 'archive', None) or records.archive}",
                f"Фонд: {getattr(m, 'fund', None) or records.fund}",
                f"Опись: {getattr(m, 'inventory', None) or records.inventory}",
                f"Дело: {getattr(m, 'case', None) or records.case}",
            ]
            # Legacy always emits a Лист: label; the value is blank when
            # page is unknown ("?" DSL placeholder or missing).
            if m.page and m.page != "?":
                desc_lines.append(f"Лист: {m.page}")
            else:
                desc_lines.append("Лист:")
            desc_lines.append(f"№ записи: {m.record_num}")
            description = "\n".join(f"        {line}" for line in desc_lines)

            # Text body: legacy quirk — the first line omits the village;
            # the description above keeps it.
            text_lines = [f"{_book_title(records)} {year}: брак {title_ru}"]
            text_lines.extend(desc_lines[1:])
            text_lines.append("")
            if year:
                wd = day if day is not None else "?"
                wm = month if month is not None else "?"
                # A civil marriage is its registration; a parish one, its wedding.
                label = "Дата регистрации" if _is_civil(records) else "Дата венчания"
                text_lines.append(f"{label}: {wd}.{wm}.{year}")

            def _partner_line(label, profile, person, age, last_name_override=None,
                              *, parish_village=parish_village):
                parts = []
                if person is not None and person.status:
                    parts.append(person.status)
                if profile.first_name: parts.append(profile.first_name)
                if profile.middle_name: parts.append(profile.middle_name)
                last_for_line = profile.last_name if last_name_override is None else last_name_override
                if last_for_line: parts.append(last_for_line)
                line = f"{label}: " + " ".join(str(x) for x in parts if x)
                suffix = []
                if person is not None and person.residence and person.residence != parish_village:
                    suffix.append(f"({person.residence})")
                if age is not None:
                    suffix.append(str(age))
                if suffix:
                    line += " " + " ".join(suffix)
                return line

            if groom is not None:
                text_lines.append(_partner_line("Жених", groom, m.groom, m.groom_age))
            if bride is not None:
                text_lines.append(_partner_line(
                    "Невеста", bride, m.bride, m.bride_age,
                    last_name_override=bride_doc_last,
                ))
            witness_persons = [m.witness1, m.witness2, m.witness3, m.witness4,
                               m.witness5, m.witness6]
            for i, wp in enumerate(witness_profiles, start=1):
                if wp is None:
                    continue
                wit_person = witness_persons[i - 1]
                w_line_parts = []
                # Legacy includes the witness's status when set —
                # `Свидетель 1: коллежский регистратор Михаил Алексеевич Сидоров`
                # in the marriage doc text.
                if wit_person is not None and wit_person.status:
                    w_line_parts.append(str(wit_person.status))
                w_line_parts.append(wp.first_name)
                w_line_parts.append(wp.middle_name)
                if wp.last_name:
                    w_line_parts.append(wp.last_name)
                text_lines.append(f"Свидетель {i}: " + " ".join(x for x in w_line_parts if x))

            # Split the two comment sources onto separate lines, mirroring
            # legacy's birth-record pattern (see add_birth_records ~line
            # 1265): `Комментарий: Имена в МК: ...` and `Пометки: {notes}`.
            if names_in_mk or m.comment:
                text_lines.append("")
            if names_in_mk:
                text_lines.append(f"Комментарий: Имена в МК: {names_in_mk}")
            if m.comment:
                text_lines.append(f"Пометки: {m.comment}")
            text = "\n".join(f"        {line}" if line else line for line in text_lines)

            doc_profiles: list[str] = []
            if groom is not None:
                doc_profiles.append(groom.res_name)
            if bride is not None:
                doc_profiles.append(bride.res_name)
            # Marriage parent profiles are emitted as standalone resources but
            # legacy never lists them in the document's `profiles` array
            # (only groom/bride/witnesses), so omit here for byte-parity.
            for wp in witness_profiles:
                if wp is not None:
                    doc_profiles.append(wp.res_name)
            for rp in marriage_relative_profiles:
                if rp is not None:
                    doc_profiles.append(rp.res_name)

            self._outputs[filename] += _document_resource(
                res_name=doc_res_name,
                title=f"{_book_title(records)} {parish_village} {year}: брак {title_ru}",
                description=description,
                text=text,
                date_day=day,
                date_month=month,
                date_year=year,
                labels=["Marriage"],
                location=parish_location,
                profiles=[self.consolidation.move_to_new_name(p) for p in doc_profiles],
                # Legacy uses the marriage parish (location_of_marriage) as
                # the project-rule location for the document.
                projects=self._projects_for_location(parish_location),
            )

    def _death_book_record_num(self, d) -> int | str | None:
        """Return the death's per-gender record number (the DSL's first
        positional arg). This is the book record number used in res_names,
        union names, and document names, consistent across all years.

        May be None: some records carry no number in the source at all (a
        scribe's omission, or a row the marginal bracket numbering skips).
        The DSL states that honestly as `death(None, ...)` and the res_name
        slot renders it as `none`.

        (Historically, res_names used a book-global «№ п/п» sourced
        from a master death CSV; that coupling was removed.)
        """
        return d.record_num

    def _marriage_book_record_num(self, m) -> int:
        """Return the marriage's per-month record number. Used only as a
        sort key — marriage res_names already carry this number."""
        try:
            return int(m.record_num)
        except (TypeError, ValueError):
            return -1  # unnumbered record — sort first, stable sort keeps DSL order

    def add_death_records(self, records) -> None:
        other = "_other" if self._is_other_parish(records) else ""
        filename = f"mk_{records.year}{other}_death.tf"
        doc = "mk_deaths"
        parish_location = _location(records.village)
        # Sort: by record_num (primary), chronological (tiebreaker). Year is
        # the outer key for rollover rows (Dec-of-previous-year in a new book).
        def _death_sort_key(r):
            rec_year = r.year or records.year
            book_num = self._death_book_record_num(r)
            # Unnumbered (`death(None, ...)`) or a non-numeric marker sorts
            # first; the sort is stable, so DSL order is preserved among them.
            # Must NOT fall back to `book_num` itself — a None or str in the
            # tuple raises TypeError against the int keys of every numbered
            # record. Mirrors _marriage_book_record_num.
            if book_num is None:
                book_num_sort = -1
            else:
                try:
                    book_num_sort = int(book_num)
                except (TypeError, ValueError):
                    book_num_sort = -1
            return (rec_year, book_num_sort,
                    _chronological_key(r, records.year, "d_month",
                                       "d_day", "death"))
        sorted_records = sorted(records.records, key=_death_sort_key)
        for d in sorted_records:
            if not admitted(d):
                continue
            if d.deceased is None:
                continue
            # Per-record year — rollover case (see add_birth_records).
            year = d.year or records.year
            month = _month_num(d.d_month)
            day = d.d_day
            book_rec_num = self._death_book_record_num(d)
            # Res_name date: legacy CSV's `Месяц = ?` / `День = ?` rows
            # were rendered as `1/1` in res_names. Mirror that so
            # the translator's deceased res_name slot matches.
            res_name_month = month if month is not None else 1
            res_name_day = day if day is not None else 1
            common = dict(year=year, month=res_name_month, day=res_name_day,
                          document_name=doc, record_number=book_rec_num)

            deceased_residence_location = _location(d.deceased.residence)
            # Legacy fills `1` for unknown day/month in the death event's
            # date field, matching the same `1/1` substitution it does in
            # res_names. Mirror that here so per-year mk_*_death.tf
            # date blocks line up byte-for-byte even when the CSV row
            # had `?`/empty in the day or month column.
            event_day = d.d_day if d.d_day is not None else 1
            event_month = month if month is not None else 1
            death_event = _event(day=event_day, month=event_month, year=year,
                                 location=deceased_residence_location or parish_location)
            # A civil book registers the death: its second date is no burial.
            burial_event = None if _is_civil(records) else _burial_event(
                d, year=year, death_month=month, location=parish_location)

            # If the deceased's age is a plain number, infer an approximate
            # birth event: year - age, same month as death, circa=true.
            # For sub-year ages (e.g. "6 мес", "1 нед"), subtract months or
            # weeks from the death date — legacy does the same via
            # relativedelta.
            # Estimate a circa birth date from the death date minus the age,
            # via the shared Y/M/W/D-aware helper. Year-bearing ages keep the
            # death month (no day); short durations (infant deaths "6 мес"/"1
            # нед") also get a circa day when the death day is known. (Same
            # helper drives the census member birth estimate.)
            birth_event = None
            withheld_birth: GeniDate | None = None
            # A burial age the author withdrew (`death(source_age_error=)`)
            # dates nothing: neither the deceased's birth nor, below, the parent
            # bounded by it. The document still prints the age as written.
            if year is not None and getattr(d, "source_age_error", None):
                bd = _birth_date_from_age(year, month, d.d_day, d.age,
                                          bare_year_keeps_ref_month=True)
                if bd is not None:
                    withheld_birth = GeniDate(day=bd[2], month=bd[1], year=bd[0],
                                              circa=True)
            elif year is not None:
                # Deaths keep the legacy behaviour for bare-year ages: a "45"
                # places the birth in the death month (year + death-month). Ages
                # with sub-year components get precise month/day arithmetic.
                bd = _birth_date_from_age(year, month, d.d_day, d.age,
                                          bare_year_keeps_ref_month=True)
                if bd is not None:
                    b_year, b_month, b_day = bd
                    birth_event = GeniEvent(
                        date=GeniDate(
                            day=b_day, month=b_month, year=b_year, circa=True,
                        ),
                    )

            # Effective deceased gender: d.gender overrides Person.gender.
            deceased_gender = d.gender if isinstance(d.gender, Gender) else d.deceased.gender
            # Profile's cause_of_death field carries the value verbatim;
            # the doc body never emits a 'Причина смерти:' line at all
            # (legacy suppresses it unconditionally — see the death doc
            # text assembly below).
            cause = d.cause_of_death if d.cause_of_death else None

            # About block — role varies by gender. `Имена в МК` carries
            # the deceased's book-name plus, for children, the parent:
            #   Adult deceased (own patronymic):  "Firstname Patronymic"
            #   Child deceased (no own patr):     "Firstname; Parent FullName"
            # `Death.__init__` auto-derives a patr_old for child deceased
            # from the FATHER relative's name — skip it in the book-
            # faithful rendering so we don't interpolate the derived form.
            #
            # Detect "child deceased" via `deceased.patr_orig is None`:
            # when the DSL didn't supply a patronymic positionally, the
            # book itself didn't carry one either.
            from verso.ru.relationship import Relationship as _Relationship
            deceased_is_child = (
                d.deceased is not None and not d.deceased.patr_orig
                and any(r.relationship in (_Relationship.FATHER, _Relationship.MOTHER)
                        for r in d.relatives if r.relationship)
            )
            rel_persons = [r.person for r in d.relatives if r.person]
            if deceased_is_child:
                deceased_for_mk = _shallow_person_without_patr(d.deceased)
            else:
                deceased_for_mk = d.deceased
            names_in_mk = _names_in_mk(deceased_for_mk, *rel_persons)
            # Legacy only emits "Имена в МК:" for deaths when the death
            # record mentions NAMES that differ from the canonical first
            # name — i.e. the CSV's "Имена в МК" column was empty for
            # single-name deaths whose first name was already canonical.
            # Detect the case: deceased-only, patr_orig is None, and the
            # canonical first name equals the recorded orthographic
            # form. Emit an empty `>` marker to match legacy's
            # "Комментарий из МК:\n>" formatting.
            bare_comment_marker = False
            if (not deceased_is_child
                    and not rel_persons
                    and d.deceased is not None
                    and not d.deceased.patr_orig
                    and not d.deceased.last_name):
                canonical = d.deceased.get_canonical_name() or ""
                orthographic = d.deceased.name_orig or d.deceased.name_modern or ""
                if canonical == orthographic:
                    names_in_mk = None
                    bare_comment_marker = True
            role_label = "умершая" if deceased_gender == Gender.FEMALE else "умерший"
            deceased_about_lines = [
                f"<strong>{_book_tag(records)} {records.village} {year}:</strong> {role_label}"
            ]
            rendered_deceased_age = format_age(d.age)
            if rendered_deceased_age:
                deceased_about_lines.append(f"Возраст: {rendered_deceased_age}")
            if d.deceased.status:
                deceased_about_lines.append(f"Титул/звание: {d.deceased.status}")
            if names_in_mk or d.comment or bare_comment_marker:
                deceased_about_lines.append("Комментарий из МК:")
                if names_in_mk:
                    deceased_about_lines.append(f">Имена в МК: {names_in_mk}")
                elif bare_comment_marker and not d.comment:
                    deceased_about_lines.append(">")
                if d.comment:
                    deceased_about_lines.append(f">{d.comment}")
            deceased_about = ("\n" + " " * 8).join(deceased_about_lines)

            deceased = self._profile_from_person(
                d.deceased, role="deceased",
                gender_override=deceased_gender,
                birth=birth_event,
                death=death_event,
                burial=burial_event,
                cause_of_death=cause,
                current_residence=deceased_residence_location,
                about=deceased_about,
                **common,
            )
            if withheld_birth is not None:
                self._withheld_births.setdefault(deceased.res_name, []).append(
                    (withheld_birth, "source_age_error"))
            self._emit_profile(filename, deceased)

            witness_profiles = []
            for i, witness in enumerate([d.witness1, d.witness2], start=1):
                if witness is None:
                    witness_profiles.append(None)
                    continue
                w = self._profile_from_person(witness, role=f"witness_{i}", **common)
                self._emit_profile(filename, w)
                witness_profiles.append(w)

            # Relative — legacy emits a single profile at role="relative"
            # (not role="relative_1") and attaches a role-specific about block.
            first_rel = d.relatives[0] if d.relatives else None
            relative_profile = None
            if first_rel is not None and first_rel.person is not None and first_rel.person.name_modern:
                rel_type = first_rel.relationship.value if first_rel.relationship else None
                deceased_form = "умершей" if deceased_gender == Gender.FEMALE else "умершего"
                rel_about_lines = [
                    f"<strong>{_book_tag(records)} {records.village} {year}:</strong> "
                    f"{rel_type + ' ' if rel_type else ''}{deceased_form}"
                ]
                if first_rel.person.status:
                    rel_about_lines.append(f"Титул/звание: {first_rel.person.status}")
                if names_in_mk or d.comment:
                    rel_about_lines.append("Комментарий из МК:")
                    if names_in_mk:
                        rel_about_lines.append(f">Имена в МК: {names_in_mk}")
                    if d.comment:
                        rel_about_lines.append(f">{d.comment}")
                rel_about = ("\n" + " " * 8).join(rel_about_lines)

                # A parent of the deceased is bounded by the deceased's own
                # (estimated) birth year — a far tighter constraint than the
                # death year. Spouses / children / in-laws stay bare: for a
                # SON/DAUGHTER the offset runs the other way.
                rel_birth = None
                if is_parent_relationship(first_rel.relationship):
                    deceased_birth_year = (
                        birth_event.date.year
                        if birth_event is not None and birth_event.date is not None
                        else None
                    )
                    rel_birth = parent_birth_estimate(
                        deceased_birth_year,
                        PARENT_RELATIONSHIP_GENDER[first_rel.relationship],
                        record_year=year,
                    )

                relative_profile = self._profile_from_person(
                    first_rel.person, role="relative",
                    current_residence=_location(first_rel.person.residence),
                    about=rel_about,
                    birth=rel_birth,
                    **common,
                )
                self._emit_profile(filename, relative_profile)

            # Family union — built only when the stated kinship places the
            # deceased (see `_DEATH_EDGE`); `_route_union` then chooses
            # per-year vs consolidated routing based on partner consolidation.
            edge = _DEATH_EDGE.get(first_rel.relationship) if first_rel else None
            if relative_profile is not None and edge is not None:
                # res_name: `{deceased_fio} and {rel_fio} d{record} {year}`
                # with single-space collapse (empty last_names compressed).
                deceased_fio = " ".join(x for x in [
                    deceased.first_name, deceased.middle_name, deceased.last_name
                ] if x)
                rel_fio = " ".join(x for x in [
                    relative_profile.first_name,
                    relative_profile.middle_name,
                    relative_profile.last_name,
                ] if x)
                raw = deceased_fio
                if rel_fio:
                    raw += f" and {rel_fio}" if raw else rel_fio
                raw += f" d{book_rec_num} {year}"
                union_res_name = generate_res_name(raw.strip())
                # Spouse: the deceased becomes partner_2 and the union has no
                # children. Parent: the deceased sits in the relative's
                # children. Foster parent: same, under Geni's `foster`
                # modifier, so the union carries the приёмыш without claiming
                # descent.
                deceased_ref = self.consolidation.move_to_new_name(deceased.res_name)
                union = GeniUnion(
                    origin=UnionOrigin.DEATH,
                    res_name=union_res_name,
                    partner_1=self.consolidation.move_to_new_name(relative_profile.res_name),
                    partner_2=deceased_ref if edge == "spouse" else None,
                    children={deceased_ref} if edge == "child" else set(),
                    foster_children={deceased_ref} if edge == "foster" else set(),
                )
                consolidated_partner = (
                    self.consolidation.in_profile_move_list(deceased.res_name)
                    or self.consolidation.in_profile_move_list(relative_profile.res_name)
                )
                self._route_union(
                    union, filename=filename, is_consolidated=consolidated_partner,
                )

            # Clergy profiles suppressed for legacy byte-parity (see
            # add_birth_records for rationale).

            # geni_document for the death event.
            deceased_fio_parts = [deceased.first_name, deceased.middle_name,
                                  deceased.last_name]
            deceased_fio = " ".join(x for x in deceased_fio_parts if x)
            # Doc res_name: legacy builds the f-string with fixed slots for
            # first/middle/last and does one-pass `.replace("  ", " ")`. For
            # a deceased with no middle/last (only a first name), that leaves
            # two consecutive spaces → `death_of_ivan__d11_1850` (double
            # underscore).
            deceased_raw = (
                f"Death of {deceased.first_name} {deceased.middle_name} "
                f"{deceased.last_name} d{book_rec_num} {year}"
            )
            doc_res_name = generate_res_name(
                deceased_raw.strip().replace("  ", " ")
            )
            self._document_for_record[d] = doc_res_name

            desc_lines = [
                f"{_book_title(records)} {records.village} {year}: смерть {deceased_fio}",
                f"Архив: {getattr(d, 'archive', None) or records.archive}",
                f"Фонд: {getattr(d, 'fund', None) or records.fund}",
                f"Опись: {getattr(d, 'inventory', None) or records.inventory}",
                f"Дело: {getattr(d, 'case', None) or records.case}",
            ]
            if d.page and d.page != "?":
                desc_lines.append(f"Лист: {d.page}")
            else:
                desc_lines.append("Лист:")
            desc_lines.append(f"№ записи: {d.record_num}")
            description = "\n".join(f"        {line}" for line in desc_lines)

            # Text body: legacy quirk — first line omits the village (the
            # description above keeps it) — same quirk already applied to
            # marriage records.
            text_lines = [
                f"{_book_title(records)} {year}: смерть {deceased_fio}"
            ]
            text_lines.extend(desc_lines[1:])
            text_lines.append("")
            # Legacy renders unknown day/month as "1" (not "?") in the
            # text body, matching its date-field substitution above.
            dd = d.d_day if d.d_day is not None else 1
            dm = d.d_month.value if d.d_month else 1
            text_lines.append(f"Дата смерти: {dd}.{dm}.{year}")
            if _is_civil(records) and d.b_day is not None:
                # A civil book's second date is the registration (a parish book's
                # burial is not printed here, and is not printed now).
                rm = d.b_month.value if d.b_month else dm
                text_lines.append(f"Дата регистрации: {d.b_day}.{rm}.{year}")
            # Combined Умерший line: `{status} {name} {age}` — the age goes
            # inline, not on its own line. format_age owns the unit and the
            # numeral agreement; this used to append a fixed " лет" unless the
            # age's trailing token matched a five-entry abbreviation map, which
            # gave «3 лет», «1 лет» and doubled the unit on «полгода», «6 недель».
            umershij_parts = []
            if d.deceased.status:
                umershij_parts.append(d.deceased.status)
            umershij_parts.append(deceased_fio)
            rendered_age = format_age(d.age)
            umershij_suffix = f" {rendered_age}" if rendered_age else ""
            text_lines.append(
                "Умерший: " + " ".join(str(x) for x in umershij_parts if x) + umershij_suffix
            )
            # Legacy's death doc text body never carried a standalone
            # 'Причина смерти:' line — the cause was only on the profile
            # resource. Suppress emission here regardless of value.
            if relative_profile is not None and first_rel is not None:
                rel_fio_parts = [relative_profile.first_name,
                                 relative_profile.middle_name,
                                 relative_profile.last_name]
                rel_fio = " ".join(x for x in rel_fio_parts if x)
                # Legacy format: `Родственник: {status} {name}` — the
                # relationship type is implicit from the DSL/CSV, not shown
                # in parens.
                rel_line_parts = []
                if first_rel.person and first_rel.person.status:
                    rel_line_parts.append(first_rel.person.status)
                if rel_fio:
                    rel_line_parts.append(rel_fio)
                text_lines.append(
                    "Родственник: " + " ".join(str(x) for x in rel_line_parts if x)
                )

            # Split comment sources onto separate lines (mirrors legacy
            # births/marriages): `Комментарий: Имена в МК: ...` and
            # `Пометки: {notes}`.
            if names_in_mk or d.comment:
                text_lines.append("")
            if names_in_mk:
                text_lines.append(f"Комментарий: Имена в МК: {names_in_mk}")
            if d.comment:
                text_lines.append(f"Пометки: {d.comment}")
            text = "\n".join(f"        {line}" if line else line for line in text_lines)

            doc_profiles = [deceased.res_name]
            if relative_profile is not None:
                doc_profiles.append(relative_profile.res_name)
            for wp in witness_profiles:
                if wp is not None:
                    doc_profiles.append(wp.res_name)

            self._outputs[filename] += _document_resource(
                res_name=doc_res_name,
                title=f"{_book_title(records)} {records.village} {year}: смерть {deceased_fio}",
                description=description,
                text=text,
                date_day=d.d_day,
                date_month=month,
                date_year=year,
                labels=["Death"],
                # Legacy uses the parish (row['Н.П. события']) for the death
                # document's location AND project-rule keying — NOT the
                # deceased's residence. The deceased's own `death` event
                # still points at their residence above (home where they died).
                location=parish_location,
                profiles=[self.consolidation.move_to_new_name(p) for p in doc_profiles],
                projects=self._projects_for_location(parish_location),
            )

    def add_external_source_records(self, records) -> None:
        """Emit a per-record profile + a proof `geni_document` for each
        external-source record (судимость / военная служба).

        Unlike metric-book records there are no events, unions, or clergy —
        just one profile (carrying a circa birth event when the source gives a
        birth year) and one document whose `source_url` Geni snapshots to a PDF
        proof. The minted profile is a deliberate duplicate of the
        already-modelled person; a later consolidation pass merges it onto the
        canonical profile. The document's `profiles`
        list passes through `move_to_new_name`, so once that merge lands the
        proof follows the survivor automatically.
        """
        from verso.ru.dsl.records.external_sources import ExternalSourceKind
        from verso.ru.domain.causes_of_death import KILLED, WOUNDS

        village = records.village
        for r in records.records:
            if not admitted(r):
                continue
            year = r.event_year
            month = r.event_month.value if r.event_month else None
            day = r.event_day
            if r.kind == ExternalSourceKind.CRIMINAL:
                doc = "ext_vss"
            elif r.kind == ExternalSourceKind.WWI:
                doc = "ext_gwar"
            else:
                doc = "ext_pn"
            filename = f"ext_{year if year else 'undated'}.tf"

            residence = r.person.residence or village
            birth_location = _location(residence)
            # Birth year: explicit `birth_year` wins; otherwise derive it from
            # the recorded `age` and the event year (e.g. 1888 − 40 л. = 1848),
            # mirroring how death/census records derive birth from age. Emitted
            # as a circa birth event (helps Geni matching + later consolidation).
            birth_year = r.birth_year
            if birth_year is None and year is not None and r.age is not None:
                age_years = _age_to_years(r.age)
                if age_years is not None:
                    birth_year = int(year - age_years)
            if r.birth_date is not None:
                # A stated birth date (wwii_record «Дата рождения») — emit it as
                # given. Year-only (day unknown) stays circa, a matching aid for
                # the later consolidation; a full date is exact. Keep `birth_year`
                # in sync so the «Год рождения» description line still renders.
                bd = r.birth_date
                if bd.year:
                    birth_year = bd.year
                birth_event = _event(
                    day=bd.day,
                    month=bd.month.value if bd.month else None,
                    year=bd.year,
                    location=birth_location,
                    circa=bd.circa or bd.day is None,
                )
            else:
                birth_event = (
                    _event(day=None, month=None, year=birth_year,
                           location=birth_location, circa=True)
                    if birth_year else None
                )

            # A fatal WWI casualty («причина выбытия» = убит/умер/погиб) emits a
            # death event dated to the card's event date, mirroring death
            # records. Non-fatal (болен/ранен) leaves the profile's death alone.
            death_event = None
            cause_of_death = None
            reason = (r.casualty_reason or "").lower()
            if any(w in reason for w in ("убит", "умер", "погиб")) and year is not None:
                # Build the death date from the full EventDate so a ranged
                # casualty («дата события» с интервалом) keeps its end bound.
                ev = r.date
                death_event = GeniEvent(date=GeniDate(
                    day=day, month=month, year=year, circa=ev.circa if ev else False,
                    end_day=ev.day_end if ev else None,
                    end_month=ev.month_end.value if ev and ev.month_end else None,
                    end_year=ev.year_end if ev else None,
                    end_circa=ev.circa_end if ev else False,
                    date_range=ev.date_range if ev else None,
                ))
                # Cause only when the reason is specific: «ран» → от ран,
                # убит/погиб → убит. Plain «умер» records the death without a
                # fabricated cause.
                if "ран" in reason:
                    cause_of_death = WOUNDS
                elif "убит" in reason or "погиб" in reason:
                    cause_of_death = KILLED

            # Place comes from the corpus's structured place entry (via the
            # person's residence), not a free-text field — single source of truth.
            # Used for the document description / projects, but NOT the profile
            # `about` (which carries the kind-specific facts below + the comment).
            place = location_label(residence)
            about_lines = [f"<strong>{r.citation.catalog}</strong>"]
            if r.kind in (ExternalSourceKind.WWI, ExternalSourceKind.WWII):
                if r.rank:
                    about_lines.append(f"Звание: {r.rank}")
                if r.military_unit:
                    about_lines.append(f"Воинская часть: {r.military_unit}")
                if r.casualty_reason:
                    about_lines.append(f"Причина выбытия: {r.casualty_reason}")
                if r.award:
                    about_lines.append(f"Награда: {r.award}")
                if r.award_number is not None:
                    about_lines.append(f"Номер награждения: {r.award_number}")
                if r.marital_status:
                    about_lines.append(f"Семейное положение: {r.marital_status}")
                if r.place_of_casualty:
                    about_lines.append(f"Место выбытия: {r.place_of_casualty}")
                if r.draft_board:
                    about_lines.append(f"Военкомат: {r.draft_board}")
                draft_date = _format_event_date(r.draft_date)
                if draft_date:
                    about_lines.append(f"Дата призыва: {draft_date}")
                feat_date = _format_event_date(r.feat_date)
                if feat_date:
                    about_lines.append(f"Дата подвига: {feat_date}")
            else:  # судимость
                rendered_r_age = format_age(r.age)
                if rendered_r_age:
                    about_lines.append(f"Возраст: {rendered_r_age}")
            if r.comment:
                about_lines.append(r.comment)
            about = ("\n" + " " * 8).join(about_lines)

            profile = self._profile_from_person(
                r.person, role="external",
                current_residence=birth_location,
                birth=birth_event,
                death=death_event,
                cause_of_death=cause_of_death,
                about=about,
                year=year, month=month, day=day,
                document_name=doc, record_number=r.res_key,
            )
            self._emit_profile(filename, profile)

            fio = " ".join(filter(None, [
                profile.first_name, profile.middle_name, profile.last_name,
            ]))
            desc_lines = [f"{r.citation.catalog}: {fio}"]
            if r.kind == ExternalSourceKind.CRIMINAL:
                # судимость layout: source citation sits directly under the
                # catalog header, then the gazette entry's № / page, then the
                # indexed person facts (name / age / event date) leading into
                # the verbatim record below.
                if r.citation.bibliography:
                    desc_lines.append(f"Источник: {r.citation.bibliography}")
                if r.record_number is not None:
                    desc_lines.append(f"№ записи: {r.record_number}")
                if r.page:
                    desc_lines.append(f"Страница: {r.page}")
                desc_lines.append(f"Имя: {fio}")
                rendered_r_age = format_age(r.age)
                if rendered_r_age:
                    desc_lines.append(f"Возраст: {rendered_r_age}")
                event_date = _format_event_date(r.date)
                if event_date:
                    desc_lines.append(f"Дата события: {event_date}")
            else:
                if r.record_number is not None:
                    desc_lines.append(f"№ записи: {r.record_number}")
                rendered_r_age = format_age(r.age)
                if rendered_r_age:
                    desc_lines.append(f"Возраст: {rendered_r_age}")
                if birth_year:
                    desc_lines.append(f"Год рождения: {birth_year}")
                if r.marital_status:
                    desc_lines.append(f"Семейное положение: {r.marital_status}")
                if r.rank:
                    desc_lines.append(f"Звание: {r.rank}")
                if r.military_unit:
                    desc_lines.append(f"Воинская часть: {r.military_unit}")
                if r.casualty_reason:
                    desc_lines.append(f"Причина выбытия: {r.casualty_reason}")
                if r.document_type:
                    desc_lines.append(f"Тип документа: {r.document_type.value}")
                if r.award:
                    desc_lines.append(f"Награда: {r.award}")
                if r.award_number is not None:
                    desc_lines.append(f"Номер награждения: {r.award_number}")
                # Home village (from the corpus's places) — distinct from «Место выбытия».
                if place:
                    desc_lines.append(f"Место: {place}")
                if r.place_of_casualty:
                    desc_lines.append(f"Место выбытия: {r.place_of_casualty}")
                # WWII (ВОВ) enlistment/feat fields («военкомат», «дата призыва»,
                # «дата подвига») — pamyat-naroda card fields absent from WWI.
                if r.draft_board:
                    desc_lines.append(f"Военкомат: {r.draft_board}")
                draft_date = _format_event_date(r.draft_date)
                if draft_date:
                    desc_lines.append(f"Дата призыва: {draft_date}")
                feat_date = _format_event_date(r.feat_date)
                if feat_date:
                    desc_lines.append(f"Дата подвига: {feat_date}")
                # «Дата выбытия» only when it differs from the card's event date.
                casualty_date = _format_event_date(r.casualty_date)
                if casualty_date:
                    desc_lines.append(f"Дата выбытия: {casualty_date}")
                if r.page:
                    desc_lines.append(f"Страница: {r.page}")
            # When the document body is a re-hosted scan (file upload), the
            # catalog page URL is no longer the doc's `source_url` attribute
            # (ExactlyOneOf) — record it in the description so provenance
            # survives. Labelled «Онлайн-просмотр» (not «Источник») so it doesn't
            # collide with судимость's bibliographic «Источник:» line.
            if r.citation.scan_files and r.citation.source_url:
                desc_lines.append(f"Онлайн-просмотр: {r.citation.source_url}")
            if r.citation.original_text:
                desc_lines.append("")
                desc_lines.append("Оригинальная запись:")
                desc_lines.append(r.citation.original_text)
            if r.kind != ExternalSourceKind.CRIMINAL and r.citation.bibliography:
                desc_lines.append(f"Источник: {r.citation.bibliography}")
            if r.citation.archive:
                desc_lines.append(f"Архив: {r.citation.archive}")
            if r.citation.fund:
                desc_lines.append(f"Фонд: {r.citation.fund}")
            if r.citation.inventory:
                desc_lines.append(f"Опись: {r.citation.inventory}")
            if r.citation.case:
                desc_lines.append(f"Дело: {r.citation.case}")
            if r.citation.archive_location:
                desc_lines.append(f"Шкаф/ящик: {r.citation.archive_location}")
            if r.comment:
                desc_lines.append(f"Комментарий: {r.comment}")
            description = "\n".join(
                f"        {line}" if line else line for line in desc_lines
            )

            doc_res_name = generate_res_name(
                f"{r.kind.value} {fio} {r.res_key} {year or ''}".strip()
            )
            # The document body is the re-hosted scan when a scan_file is given,
            # else a snapshot of the catalog source_url. `file` and `source_url`
            # are mutually exclusive on the provider (ExactlyOneOf). The content
            # type is derived from the scan file extension (override with
            # scan_content_type).
            #
            # NB: pointing source_url straight at the scan IMAGE URL (so Geni
            # snapshots it, no local file) was tried and does NOT work for the
            # anti-botted catalogs we use — Geni's fetcher hits gwar's Incapsula
            # block page (and can't render the RSL viewer), so a local re-host is
            # the only reliable route.
            doc_profiles = [self.consolidation.move_to_new_name(profile.res_name)]
            doc_projects = self._projects_for_location(residence)
            doc_location = _location(village)
            # Transcription lives in `description`: the OAuth API can't set a
            # document's `text` body, and `text` is mutually exclusive with
            # `source_url`/`file` on the provider (ExactlyOneOf).
            scan_files = r.citation.scan_files
            if scan_files:
                # One geni_document PER re-hosted scan (a WWII award carries the
                # приказ + наградной-лист pages). The first keeps the full
                # transcription; the rest are extra pages of the same proof.
                # (`source_url` is dropped — mutually exclusive with `file`.)
                for n, sf in enumerate(scan_files):
                    if n == 0:
                        rn, title, desc = doc_res_name, f"{r.citation.catalog}: {fio}", description
                    else:
                        rn = f"{doc_res_name}_{n + 1}"
                        title = f"{r.citation.catalog}: {fio} (скан {n + 1})"
                        extra = [f"Дополнительный скан к документу «{r.citation.catalog}»: {fio}."]
                        if r.citation.source_url:
                            extra.append(f"Онлайн-просмотр: {r.citation.source_url}")
                        desc = "\n".join(f"        {ln}" if ln else ln for ln in extra)
                    self._outputs[filename] += _document_resource(
                        res_name=rn, title=title, description=desc, text="",
                        date_day=day, date_month=month, date_year=year,
                        labels=r.labels, location=doc_location,
                        profiles=doc_profiles, projects=doc_projects,
                        source_url=None,
                        content_type=(r.citation.scan_content_type or _scan_content_type(sf)),
                        file=sf, file_name=sf.rsplit("/", 1)[-1],
                    )
            else:
                self._outputs[filename] += _document_resource(
                    res_name=doc_res_name,
                    title=f"{r.citation.catalog}: {fio}",
                    description=description, text="",
                    date_day=day, date_month=month, date_year=year,
                    labels=r.labels, location=doc_location,
                    profiles=doc_profiles, projects=doc_projects,
                    source_url=r.citation.source_url,
                    content_type="text/html", file=None, file_name=None,
                )

    def add_name_list_records(self, records) -> None:
        """Emit one profile per listed person + a single shared proof
        `geni_document` for a flat archival name list (e.g. 1917 voter lists).

        Flat: no households/relationships. Each entry mints a deliberate
        duplicate profile (circa birth = list year − age) reconciled in the
        normal consolidation pass; all entries share one document (the list),
        whose `profiles` list passes through `move_to_new_name` so the proof
        follows each survivor after a merge.
        """
        year = records.year
        month = records.record_month
        day = records.record_day
        village = records.village
        filename = f"list_{year}.tf"
        doc_location = _location(village)

        doc_profiles: list[str] = []
        roster_lines: list[str] = []
        for e in records.entries:
            if not admitted(e):
                continue
            residence = e.person.residence or village
            birth_location = _location(residence)
            by = e.birth_year(year)
            birth_event = (
                _event(day=None, month=None, year=by,
                       location=birth_location, circa=True)
                if by else None
            )
            # About block mirrors the metric-book / census shape: a bold
            # `<strong>{label} {village} {year}:</strong> {locator}` header,
            # then fact lines, then a `Комментарий из {genitive} {year} года:`
            # section with `>`-prefixed comment lines. `label`/`label_genitive`
            # are the document_type / its genitive (falls back to document_type).
            label = records.document_type
            label_genitive = records.document_type_genitive or records.document_type
            about_lines = [
                f"<strong>{label} {village} {year}:</strong> № {e.number}"
            ]
            rendered_e_age = format_age(e.age)
            if rendered_e_age:
                about_lines.append(f"Возраст: {rendered_e_age}")
            # The лист, when the DSL wrapped this entry in `page("11", …)`.
            # One shared document covers the whole list, so unlike census
            # (where `Лист:` sits in the document header) the per-entry sheet
            # can only live here and on the roster line.
            if getattr(e, "page", None):
                about_lines.append(f"Лист: {e.page}")
            # `>`-prefixed comment lines, mirroring МК/census: the as-written
            # «ФИО/ИО/Имя в документе» line first (auto-derived from the person's
            # original-spelling fields, surname-first so the «ФИО» label matches
            # the token order — preserves the source spelling the profile name
            # canonicalizes away), then the free-text comment.
            gt_lines: list[str] = []
            doc_name = _name_in_document(e.person, surname_first=True)
            if doc_name:
                gt_lines.append(doc_name)
            if e.comment:
                gt_lines.append(e.comment)
            if gt_lines:
                about_lines.append(f"Комментарий из {label_genitive} {year} года:")
                about_lines.extend(f">{gl}" for gl in gt_lines)
            about = ("\n" + " " * 8).join(about_lines)

            profile = self._profile_from_person(
                e.person, role="listed",
                current_residence=birth_location,
                birth=birth_event,
                about=about,
                year=year, month=month, day=day,
                document_name="list", record_number=e.number,
            )
            self._emit_profile(filename, profile)
            doc_profiles.append(self.consolidation.move_to_new_name(profile.res_name))

            fio = " ".join(filter(None, [
                profile.first_name, profile.middle_name, profile.last_name,
            ]))
            line = f"{e.number}. {fio}"
            rendered_e_age = format_age(e.age)
            if rendered_e_age:
                line += f" — {rendered_e_age}"
            if by:
                line += f" (~{by})"
            if getattr(e, "page", None):
                line += f" (л. {e.page})"
            if e.comment:
                line += f". {e.comment}"
            roster_lines.append(line)

        if not doc_profiles:
            return

        # Shared document. A census-style provenance header (title + archive
        # coordinates) leads both `description` and `text`; `text` then appends
        # the roster after a `---` separator + column header. (Census docs prove
        # text bodies apply.) A `scan_file` switches the body to a re-hosted
        # `file` (ExactlyOneOf drops text).
        header_lines = [f"{records.document_type}, {village} {year}"]
        if records.district:
            header_lines.append(f"Счётный участок: {records.district}")
        if records.volost:
            header_lines.append(f"Волость: {records.volost}")
        if records.archive:
            header_lines.append(f"Архив: {records.archive}")
        if records.fund:
            header_lines.append(f"Фонд: {records.fund}")
        if records.inventory:
            header_lines.append(f"Опись: {records.inventory}")
        if records.case:
            header_lines.append(f"Дело: {records.case}")

        desc_lines = list(header_lines)
        if records.scan_file and records.source_url:
            desc_lines.append(f"Онлайн-просмотр: {records.source_url}")
        description = "\n".join(
            f"        {ln}" if ln else ln for ln in desc_lines
        )
        text_lines = [
            *header_lines, "", "",
            "---", "№. Имя — Возраст (год рождения)", "---",
            *roster_lines,
        ]
        text = "\n".join(f"        {ln}" if ln else ln for ln in text_lines)

        doc_res_name = generate_res_name(
            f"{records.document_type} {village} {year} {records.district or ''}".strip()
        )
        doc_projects = self._projects_for_location(village)
        if records.scan_file:
            self._outputs[filename] += _document_resource(
                res_name=doc_res_name,
                title=f"{records.document_type}, {village} {year}",
                description=description, text="",
                date_day=day, date_month=month, date_year=year,
                labels=records.labels, location=doc_location,
                profiles=doc_profiles, projects=doc_projects,
                source_url=None,
                content_type=_scan_content_type(records.scan_file),
                file=records.scan_file,
                file_name=records.scan_file.rsplit("/", 1)[-1],
            )
        else:
            has_url = bool(records.source_url)
            self._outputs[filename] += _document_resource(
                res_name=doc_res_name,
                title=f"{records.document_type}, {village} {year}",
                description=description, text="" if has_url else text,
                date_day=day, date_month=month, date_year=year,
                labels=records.labels, location=doc_location,
                profiles=doc_profiles, projects=doc_projects,
                source_url=records.source_url,
                content_type="text/html" if has_url else None,
                file=None, file_name=None,
            )

    def _foster_children_for(self, h, member_profiles, owner_num, head_num):
        """Canonical res_names of the household's foster children (приёмыш;
        FOSTER_SON/FOSTER_DAUGHTER) whose foster parent is member `owner_num`.

        A foster child's foster parent is `ref_member` (the source's приёмный-
        parent pointer) when set, else the HEAD. Callers pass the member whose
        union they are building (the HEAD for the head+wife/head-only union, a
        sub-head for a pass-(a) union); `_emit_lone_foster_parent_unions` mops
        up foster parents who have no couple/head union of their own.
        Returns `(canonical_res_names, original_res_names)`.
        """
        from verso.ru.dsl.records.census import _FOSTER_ROLES
        res: set[str] = set()
        orig: list[str] = []
        for m in h.members:
            if m.role not in _FOSTER_ROLES:
                continue
            fp = m.ref_member if m.ref_member is not None else head_num
            if fp != owner_num:
                continue
            mp = member_profiles.get(m.number)
            if mp is None:
                continue
            orig.append(mp.res_name)
            res.add(self.consolidation.move_to_new_name(mp.res_name))
        return res, orig

    def _emit_lone_foster_parent_unions(self, h, member_profiles, head_num,
                                        year, filename, display_id):
        """Emit a single-partner foster union for each foster parent who has NO
        couple/head union of their own — a приёмыш whose `ref_member` names a
        member who is neither the HEAD nor a WIFE-paired sub-head (e.g. a
        приёмыш of a brother of the head, who has no wife). Without this the
        foster child would fall back to the
        HEAD's union (wrong foster parent)."""
        from verso.ru.dsl.records.census import CensusRole, _FOSTER_ROLES
        members_by_num0 = {x.number: x for x in h.members}
        # A foster parent already has a union when they are the HEAD, a WIFE-
        # paired sub-head, or a biological parent (some child resolves to them
        # via _resolve_parent_ref). Only truly union-less foster parents get a
        # lone single-partner union here.
        covered = {head_num} | {
            w.ref_member for w in h.members
            if w.role == CensusRole.WIFE and w.ref_member is not None
        } | {
            pr for pr in (
                _resolve_parent_ref(c, members_by_num0) for c in h.members
            ) if pr is not None
        }
        by_parent: dict[int, tuple[set[str], list[str]]] = {}
        for m in h.members:
            if m.role not in _FOSTER_ROLES:
                continue
            fp = m.ref_member if m.ref_member is not None else head_num
            if fp in covered:
                continue  # handled by the head+wife / pass-(a) union sites
            mp = member_profiles.get(m.number)
            if mp is None:
                continue
            res, orig = by_parent.setdefault(fp, (set(), []))
            res.add(self.consolidation.move_to_new_name(mp.res_name))
            orig.append(mp.res_name)
        members_by_num = {x.number: x for x in h.members}
        for fp, (res, orig) in by_parent.items():
            fp_member = members_by_num.get(fp)
            fp_profile = member_profiles.get(fp)
            if fp_member is None or fp_profile is None:
                continue
            # A foster parent may have no `record_number` (e.g. a brother of
            # the head), so build the union res_name from a synthetic
            # `{display_id}-{member}` id (the hidden-member id shape) — unique
            # per household+member and distinct from record-number unions.
            fp_p = fp_member.person
            fp_res = generate_res_name(
                f"{fp_p.get_canonical_name() or fp_p.name_modern or ''} "
                f"{fp_p.patr_modern or ''} {fp_p.last_name_modern or ''} "
                f"rs{display_id}-{fp} {year}".strip().replace("  ", " "))
            if not fp_res:
                continue
            union = GeniUnion(
                origin=UnionOrigin.ROLL,
                res_name=fp_res,
                partner_1=self.consolidation.move_to_new_name(fp_profile.res_name),
                partner_2=None,
                foster_children=res,
            )
            self._route_union(
                union, filename=filename,
                is_consolidated=self._any_in_move_list(fp_profile.res_name, *orig),
            )

    def add_census_records(self, records, *, suffix: str = "") -> None:
        # Lazy import to avoid a top-level circular: census.py imports from
        # genealogy modules, which tf_translator also touches.
        from verso.ru.dsl.records.census import CensusRole, _FOSTER_ROLES

        year = records.year
        # Cat D: `archive_suffix` on CensusRecords is the per-file
        # identity (fund-inventory-case[-part-N|-<village>]) that legacy
        # uses in the rs_*_1.tf filename. When `suffix_in_res_names` is
        # also True, the suffix is threaded into every profile res_name
        # too (matches legacy's inconsistent rule: 11 of 32 census files
        # include the suffix in res_names, the other 21 don't).
        archive_suffix = getattr(records, "archive_suffix", None)
        suffix_in_res_names = getattr(records, "suffix_in_res_names", False)
        # Household-list sources that are NOT revision tales pin their own
        # prefix (`CONFESSION_LIST` in verso.ru.dsl.records.census): an исповедная
        # роспись emits `ir_1828_1.tf` and `ir`-keyed profile res_names, so it
        # cannot collide with a ревизская сказка of the same year. The default
        # is "rs", so every revision tale renders byte-for-byte as before.
        file_prefix = records.file_prefix
        doc_prefix = records.file_prefix
        if archive_suffix:
            filename = f"{file_prefix}_{year}_{archive_suffix}_1.tf"
        elif suffix:
            filename = f"{file_prefix}_{year}_{suffix}.tf"
        else:
            # Legacy always appends a "_1" file-partition suffix even
            # when archive_suffix is absent — rs_1795_1.tf / rs_1721_1.tf
            # etc. Match that.
            filename = f"{file_prefix}_{year}_1.tf"
        doc = f"{doc_prefix}_{suffix}" if suffix else doc_prefix
        member_res_name_suffix = archive_suffix if suffix_in_res_names else ""
        child_roles = {
            CensusRole.SON, CensusRole.DAUGHTER,
            CensusRole.STEPSON, CensusRole.STEPDAUGHTER,
        }
        # Compute per-household display IDs. Households with an explicit
        # `family_id` (e.g. "1а"/"1б" for legacy Cyrillic-suffixed rows)
        # use that literal value and do NOT contribute to the 1-based
        # numeric counter; households without one auto-number 1, 2, 3,
        # …. This mirrors legacy's numbering where Cyrillic-suffixed
        # households shared the "1" numeric slot with the following
        # numeric "1" household.
        household_display_ids: list[str] = []
        numeric_index = 0
        for _h in records.households:
            if _h.family_id:
                household_display_ids.append(_h.family_id)
            else:
                numeric_index += 1
                household_display_ids.append(str(numeric_index))

        for h_index, h in enumerate(records.households, start=1):
            # Transcribed but not yet checked against the scan: emit nothing
            # for this двор. The `continue` sits inside the enumerate loop on
            # purpose — `h_index` and `household_display_ids` are already
            # assigned, so skipping one household does not renumber the rest.
            if not admitted(h):
                continue
            # Legacy's per-household order is
            # `[un-consolidated profiles, document, union]`. Emit the
            # virtual-father stub and member profiles first; the document
            # (which only references profile res_names, never the
            # profile objects) comes after the loop.
            display_id: str = household_display_ids[h_index - 1]
            stub_res_name = self._emit_head_of_family_stub_if_needed(
                filename=filename, records=records, household=h, h_index=display_id,
                archive_suffix=archive_suffix,
            )
            # Emit a profile for every member (as before), keeping a map from
            # member number to emitted profile so we can wire up the
            # household's head-wife union and its direct children.
            member_profiles: dict[Any, GeniProfile | None] = {}
            head_member = None
            wife_member = None
            for m in h.members:
                p = m.person
                if p is None:
                    continue
                # All hidden members emit their per-year profile so
                # they're available for cross-references (sub-family
                # unions, document profile lists, etc.). The
                # "Отсутствует в РС …" comment is purely documentation
                # describing why the person was added manually — it
                # no longer drives any conditional drop. When the
                # res_name happens to be in the consolidation
                # `profile_move_list`, the emitted profile is routed
                # to the consolidated target as usual.
                manual_only = False
                # Census member death event. Three shapes:
                #   1. Departure with reason=="умер" and a known year →
                #      circa death at that year, with the village as
                #      location (matches legacy on 'умер' deaths).
                #   2. Any non-deceased member with a known current age →
                #      "after {census_date}" range marker. The "after"
                #      range is a LOWER bound derived from the fact that
                #      the census recorded them alive at that age — it
                #      doesn't conflict with later sightings elsewhere
                #      (those just tighten the lower bound). Legacy
                #      emitted this for every record with `Лет (текущая
                #      РС)` populated, regardless of departure reason.
                #   3. Hidden / prev-age-only / age-unknown members → no
                #      death event (no alive-at-census signal to anchor
                #      a lower bound).
                dep_reason = _resolve_departure_reason(m)
                died_year = (
                    _resolve_departure_year(m)
                    if dep_reason == "умер"
                    else None
                )
                # Hidden members (string `record_number=`, e.g. "1-14")
                # are placeholder profiles for ancestors referenced via
                # ref_member but NOT actually present in the revision
                # book — no alive-at-census signal, so no after-stub.
                is_hidden = m.is_hidden()
                # DSL convention: when the source CSV's `Лет (текущая
                # РС)` column was empty, the importer compresses the
                # prior age into both `previous_age` and `m.age` so
                # the document body still has something to render.
                # Detect that compression (same value in both, no
                # arrival year) and treat it as "current age unknown"
                # for death-stub purposes — legacy keyed on the source
                # column being empty, so emitted no after-stub. When
                # `previous_age` and `m.age` differ, both columns were
                # filled (the normal case) and the after-stub stays.
                prev_age_val = getattr(m, "previous_age", None)
                prev_age_compresses_current = (
                    prev_age_val is not None
                    and m.age is not None
                    and str(prev_age_val) == str(m.age)
                )
                # Members with unknown age — legacy emitted no birth
                # event (can't derive year) and no death-after stub
                # either. Mirror that.
                age_unknown = m.age in (None, "?", "", "-")
                if died_year is not None:
                    census_death = GeniEvent(
                        date=GeniDate(year=died_year, circa=True),
                        location=_location(records.village),
                    )
                elif dep_reason == "умер":
                    # `departure_reason="умер"` with no year → "died
                    # sometime before this revision". Legacy emits
                    # `death = { range = "before"; circa = true; year
                    # = census_year; location = village }` as an upper
                    # bound on the death year.
                    census_death = GeniEvent(
                        date=GeniDate(
                            year=year, circa=True, date_range="before",
                        ),
                        location=_location(records.village),
                    )
                elif is_hidden or prev_age_compresses_current or age_unknown:
                    census_death = None
                else:
                    # "after {census_date}" — include page-level day/
                    # month when the household carries 'Дата записи'.
                    census_death = GeniEvent(
                        date=GeniDate(
                            day=getattr(h, "record_day", None),
                            month=getattr(h, "record_month", None),
                            year=year,
                            date_range="after",
                        ),
                    )
                # Census records sometimes have a per-page "Дата записи"
                # (Cat B1): when the CSV populated that column, legacy's
                # res_name includes it as `_YYYY_MM_DD_name_...`. Years
                # without the column (pre-1816 mostly) fall back to
                # `_YYYY_00_00_...` — pass 0/0 instead of None so the
                # res_name generator keeps the padded shape that the
                # consolidation `profile_move_list` keys expect.
                page_month = getattr(h, "record_month", None)
                page_day = getattr(h, "record_day", None)
                # Birth estimate: legacy sets `birth.date.year =
                # census_year - age, circa=True` on every census member
                # whose age is a plain integer. `birth.location` is set
                # ONLY when the DSL carries an `origin` (the member's
                # natal village differs from their current residence);
                # legacy doesn't duplicate the parish location as
                # birth.location.
                origin_loc = _location(m.origin) if m.origin else None
                # Inference requires the parish to have a prior RS — gated
                # by census_records.prev_revision_year. When the DSL marks
                # this revision as having a known prior, a male member
                # without origin AND without previous_age must have been
                # born after the prior RS, and (since the family was on
                # record at this parish then) born here. For first-
                # revision sources the gate stays unset, so no
                # birth.location is fabricated.
                #
                # Exception: when `arrival_reason` is set, the member came
                # *into* this household after the prior RS from somewhere
                # else (bought, gifted, transferred). The absence of
                # previous_age then signals an external arrival, not a
                # post-prior-RS birth at this parish — don't fabricate
                # birth.location at the current village.
                inferred_birth_loc = None
                has_prev_age = (
                    getattr(m, "previous_age", None) is not None
                    or bool(m.comment and "прошлая РС:" in m.comment)
                )
                has_arrival = _resolve_arrival_reason(m) is not None
                if (records.prev_revision_year is not None
                        and not origin_loc
                        and m.role in (CensusRole.SON, CensusRole.GRANDSON,
                                       CensusRole.NEPHEW, CensusRole.STEPSON,
                                       CensusRole.HEAD)
                        and m.age not in (None, "?", "", "-")
                        and not has_prev_age
                        and not has_arrival):
                    # Check person gender — only male. (Every role in the guard
                    # above is male, so an unknown gender is treated as male.)
                    p_gender = getattr(p, "gender", None)
                    is_male = p_gender == Gender.MALE or p_gender is None
                    if is_male:
                        inferred_birth_loc = _location(records.village)
                effective_birth_loc = origin_loc or inferred_birth_loc
                # The birth the line dates, a retraction honoured (see
                # `member_birth`); `withheld` is what a retraction took away,
                # kept so RIG001 can name an `ignore` that merely repeats it.
                member_birth = derive_member_birth(
                    m, year=year, page_month=page_month, page_day=page_day,
                    location=effective_birth_loc, prev_revision=self.prev_revision)
                withheld = withheld_member_birth(
                    m, year=year, page_month=page_month, page_day=page_day,
                    prev_revision=self.prev_revision)
                about_label = getattr(records, "document_type", None) or "РС"
                about_label_genitive = (
                    getattr(records, "document_type_genitive", None)
                    or getattr(records, "document_type", None)
                    or "РС"
                )
                about_text = self._build_census_member_about(
                    village=records.village, year=year, h_index=display_id,
                    status=p.status, comment=m.comment, origin=m.origin,
                    member=m, occupation=m.occupation,
                    marital_status=m.marital_status, household=h,
                    label=about_label, label_genitive=about_label_genitive,
                    unit_label=records.household_label,
                )
                # Census member projects: legacy checks 'Неелов' in the
                # origin (prev-revision) location too, not just the
                # current residence. A wife brought in from a village of
                # the Нееловская волость should get the neelovo
                # project even if her current_residence is the parish village.
                member_projects = None
                if m.origin:
                    origin_projects = self._projects_for_location(m.origin)
                    residence_projects = self._projects_for_location(
                        m.person.residence or records.village,
                    )
                    # Union of both — any source that surfaces an extra
                    # project keyed rule contributes.
                    member_projects = list(residence_projects)
                    for p_id in origin_projects:
                        if p_id not in member_projects:
                            member_projects.append(p_id)
                # Extract destination location from "убыл: ... в X" or
                # similar markers in the comment. Legacy's CSV had a
                # separate "Н.П. куда отправлены / убыли" column the DSL
                # collapses into the comment text. Common patterns:
                #   - "выдана замуж в X" — moved to X by marriage
                #   - "Переведен … в X" — transferred to X
                # When matched, X becomes current_residence (overrides
                # the parish default) so consolidation aligns with
                # legacy.
                dest_name = _resolve_destination(m)
                destination_loc = _location(dest_name) if dest_name else None
                resident_loc = (
                    destination_loc
                    or _location(m.person.residence)
                )
                profile = self._profile_from_person(
                    p,
                    year=year,
                    month=page_month if page_month is not None else 0,
                    day=page_day if page_day is not None else 0,
                    document_name=doc,
                    role="family_member",
                    record_number=f"{display_id}_{m.number}",
                    current_residence=resident_loc,
                    birth=member_birth,
                    death=census_death,
                    res_name_suffix=member_res_name_suffix,
                    about=about_text,
                    projects=member_projects,
                    occupation=m.occupation,
                )
                if manual_only and not self.consolidation.in_profile_move_list(profile.res_name):
                    # Not in move_list → drop entirely (legacy never
                    # wrote a per-year profile for these manual-add-only
                    # records).
                    pass
                else:
                    if withheld is not None:
                        self._withheld_births.setdefault(
                            profile.res_name, []).append(withheld)
                    self._emit_profile(filename, profile)
                    if not manual_only:
                        # Only actual-in-revision members populate
                        # member_profiles / union partners / children.
                        # Manual adds are about-block-only.
                        member_profiles[m.number] = profile
                        # Skip hidden HEADs when picking head_member.
                        # Hidden HEADs are implicit ancestors (e.g. a
                        # great-grandfather added manually for the chain,
                        # standing before the visible head). They're
                        # handled by the hidden-ancestor union path;
                        # pairing them with the visible head's wife
                        # creates a phantom union (the hidden ancestor
                        # and the head's wife with the head's children).
                        if (m.role == CensusRole.HEAD
                                and head_member is None
                                and not m.is_hidden()):
                            head_member = m
                        elif m.role == CensusRole.WIFE:
                            # Only pair with HEAD when the wife either has
                            # no explicit ref_member or her ref points at
                            # the head. A WIFE with ref_member to another
                            # member (e.g., a brother) belongs in HIS sub-
                            # family union, not the head's.
                            head_num = head_member.number if head_member else 1
                            if m.ref_member is None or m.ref_member == head_num:
                                # Multi-wife head-of-household tie-break.
                                #
                                # When the head has multiple WIFE members
                                # (e.g. 1st wife dead by current revision
                                # + 2nd wife taken as widow), only ONE
                                # head+wife union gets emitted. Picking
                                # blindly by encounter order can route
                                # the union under the wrong consolidated
                                # bucket. Preference order:
                                #
                                #   1. WIFE whose profile is in the
                                #      consolidation `profile_move_list`
                                #      (her record consolidates to a
                                #      known person — typically the wife
                                #      attested across multiple revisions
                                #      / MK records, e.g. a dead first
                                #      wife whose profile folds into an
                                #      earlier roll's entry vs. an alive
                                #      second wife with no cross-record
                                #      presence).
                                #   2. Alive wife over departed/dead one
                                #      when consolidation status ties
                                #      (e.g. both wives uncommitted to
                                #      consolidation — legacy paired the
                                #      head with the surviving wife, not
                                #      the dead one).
                                if wife_member is None:
                                    wife_member = m
                                else:
                                    cur_p = member_profiles.get(wife_member.number)
                                    new_p = profile
                                    cur_consolidated = (
                                        cur_p is not None
                                        and self.consolidation.in_profile_move_list(cur_p.res_name)
                                    )
                                    new_consolidated = self.consolidation.in_profile_move_list(
                                        new_p.res_name
                                    )
                                    cur_dead = getattr(wife_member, "departure_reason", None) is not None
                                    new_dead = getattr(m, "departure_reason", None) is not None
                                    if new_consolidated and not cur_consolidated:
                                        wife_member = m
                                    elif new_consolidated == cur_consolidated and cur_dead and not new_dead:
                                        wife_member = m

            head_profile = (
                member_profiles.get(head_member.number)
                if head_member is not None else None
            )
            wife_profile = (
                member_profiles.get(wife_member.number)
                if wife_member is not None else None
            )

            # Stub union: when `_emit_head_of_family_stub_if_needed`
            # fired, link the implied parent stub to its attested full
            # siblings — HEAD (always, since the trigger required
            # member #1 to lack a ref) and any BROTHER/SISTER members
            # with effective_ref=1 EXCEPT those flagged as half/step-
            # siblings via `роль в оригинале: сводный брат` /
            # `сводная сестра` (their parent is a different person and
            # they belong to a different lineage line).
            if stub_res_name is not None:
                stub_children: set[str] = set()
                stub_orig: list[str] = []
                for sc in h.members:
                    if sc.number == 1 and head_profile is not None:
                        stub_orig.append(head_profile.res_name)
                        stub_children.add(self.consolidation.move_to_new_name(head_profile.res_name))
                        continue
                    if sc.role not in (CensusRole.BROTHER, CensusRole.SISTER):
                        continue
                    # Hidden BROTHER/SISTER use ref_member for spouse, not
                    # parent — they're still HEAD's siblings for the
                    # implied-ancestor stub. Treat as eff_ref=1 here.
                    if sc.is_hidden():
                        eff_ref = 1
                    else:
                        eff_ref = sc.ref_member if sc.ref_member is not None else 1
                    if eff_ref != 1:
                        continue
                    # Half/step-sibling — different parent, not part of this lineage.
                    if sc.comment and (
                        "сводный брат" in sc.comment
                        or "сводная сестра" in sc.comment
                    ):
                        continue
                    cp = member_profiles.get(sc.number)
                    if cp is None:
                        continue
                    stub_orig.append(cp.res_name)
                    stub_children.add(self.consolidation.move_to_new_name(cp.res_name))
                if stub_children:
                    stub_union = GeniUnion(
                        origin=UnionOrigin.ROLL_ANCESTOR,
                        res_name=f"head_of_family_{display_id}_{year}",
                        partner_1=self.consolidation.move_to_new_name(
                            stub_res_name,
                        ),
                        partner_2=None,
                        children=stub_children,
                    )
                    self._route_union(
                        stub_union, filename=filename,
                        is_consolidated=self._any_in_move_list(
                            stub_res_name, *stub_orig,
                        ),
                    )

            # Cross-household `father_ref` unions: a member whose father
            # isn't in this household but is known via a consolidated
            # profile name (e.g. a WIFE married in from elsewhere).
            # Emit a single-partner sub-family union linking the
            # external father → this member, then route it to
            # consolidation so it merges into the father's bucket via
            # partner-lookup. Mirrors legacy's patronymic-based wife→
            # father linkage but as an explicit per-DSL annotation.
            for fr_member in h.members:
                fr_target = getattr(fr_member, "father_ref", None)
                if not fr_target:
                    continue
                fr_profile = member_profiles.get(fr_member.number)
                if fr_profile is None:
                    continue
                fr_year = year
                fr_h_index = display_id
                fr_res_name = generate_res_name(
                    f"{fr_target} rs{fr_h_index}-{fr_member.number} {fr_year}"
                    .strip().replace("  ", " ")
                )
                fr_child_consolidated = self.consolidation.move_to_new_name(
                    fr_profile.res_name,
                )
                fr_union = GeniUnion(
                    origin=UnionOrigin.ROLL,
                    res_name=fr_res_name,
                    partner_1=fr_target,
                    partner_2=None,
                    children={fr_child_consolidated},
                )
                self._route_union(
                    fr_union, filename=filename,
                    is_consolidated=self._any_in_move_list(
                        fr_target, fr_profile.res_name,
                    ) or fr_target in self.consolidation.profile_move_list.values(),
                )

            # Ascending-role unions: a visible MOTHER/FATHER member of
            # the head implies a deceased spouse and a marriage that
            # produced the head (and any of head's siblings). Legacy's
            # write_family_members_to_file (pre-Nov-2025) emitted a
            # single-partner union named `<first>_<patr>_rs<rn>_<year>`
            # with the parent as partner_1 and the head + any
            # BROTHER/SISTER members as children. `union_move_list_v2`
            # then merges this union into the consolidated parent-pair
            # union (e.g. `tatjana_sergeevna_rs12_1850` →
            # `nikolaj_and_tatjana_sergeevna`). Without this emission,
            # the v2 redirect has nothing to merge and the parent's
            # profile reference is dropped from the consolidated union.
            #
            # Runs unconditionally (before the can_emit_unions branch)
            # so it fires for both WIFE-present and no-WIFE households.
            ascending_roles = (CensusRole.FATHER, CensusRole.MOTHER)
            for ap in h.members:
                if ap.role not in ascending_roles:
                    continue
                if ap.is_hidden():
                    continue
                # Skip when a hidden ancestor in the same household
                # already covers the same parent→head relationship via
                # the hidden-ancestor pass (a hidden ancestor pair → head
                # case). The hidden-ancestor union
                # uses the visible MOTHER/FATHER as `partner_2` and HEAD
                # as a child; an additional ascending-only union here
                # would attribute HEAD as this parent's child a second
                # time.
                if head_member is not None:
                    hp_num = getattr(head_member, "parent_member", None)
                    if hp_num is not None:
                        hp = next(
                            (x for x in h.members if x.number == hp_num),
                            None,
                        )
                        if (hp is not None and hp.is_hidden()
                                and getattr(hp, "ref_member", None) == ap.number):
                            continue
                ap_profile = member_profiles.get(ap.number)
                if ap_profile is None:
                    continue
                ap_res = _build_subfamily_union_res_name(ap, year=year)
                if ap_res is None:
                    continue
                # Children of the ascending-role member: the head and any
                # BROTHER/SISTER siblings of HEAD (when the parent's ref
                # points at HEAD), plus any SON/DAUGHTER members whose
                # `ref_member` points at this parent.
                #
                # A MOTHER/FATHER whose ref names another member is THAT
                # member's parent, not the head's, and the head's siblings
                # are not her children: a woman listed as the mother of the
                # head's nephew, whose ref names her husband (the head's
                # brother), was made the mother of her own husband; and an
                # entry «<name>'s mother» naming the head's brother.
                # (`_emit_head_of_family_stub_if_needed`
                # asks the same question for the head's implied parent.)
                ap_ref = ap.ref_member if ap.ref_member is not None else 1
                head_num = head_member.number if head_member is not None else 1
                of_head = ap_ref == head_num
                ap_kid_res: set[str] = set()
                ap_kid_orig: list[str] = []
                if of_head and head_profile is not None and head_member is not None:
                    ap_kid_orig.append(head_profile.res_name)
                    ap_kid_res.add(
                        self.consolidation.move_to_new_name(head_profile.res_name)
                    )
                for kid in h.members:
                    # The siblings-of-head-share-head's-parent heuristic
                    # only applies to a BROTHER/SISTER with NO explicit
                    # `parent_member`. When `parent_member` is set the
                    # member's parent is known — the hidden-ancestor pass
                    # routes them to that parent's union; claiming them
                    # here too would double-link them (e.g. BROTHERs of the
                    # head who are sons of a hidden ancestor, not of the
                    # head's father).
                    is_sibling = (
                        of_head
                        and kid.role in (CensusRole.BROTHER, CensusRole.SISTER)
                        and getattr(kid, "parent_member", None) is None
                    )
                    is_child_via_ref = (
                        kid.role in (CensusRole.SON, CensusRole.DAUGHTER)
                        and kid.ref_member == ap.number
                    )
                    # A foster child (FOSTER_SON/FOSTER_DAUGHTER) is never a
                    # biological child of any household member — exclude from
                    # every biological parent union.
                    if kid.role in _FOSTER_ROLES:
                        continue
                    if not (is_sibling or is_child_via_ref):
                        continue
                    kid_profile = member_profiles.get(kid.number)
                    if kid_profile is None:
                        continue
                    ap_kid_orig.append(kid_profile.res_name)
                    ap_kid_res.add(
                        self.consolidation.move_to_new_name(kid_profile.res_name)
                    )
                if not ap_kid_res:
                    continue
                ap_union = GeniUnion(
                    origin=UnionOrigin.ROLL,
                    res_name=ap_res,
                    partner_1=self.consolidation.move_to_new_name(
                        ap_profile.res_name,
                    ),
                    partner_2=None,
                    children=ap_kid_res,
                )
                self._route_union(
                    ap_union, filename=filename,
                    is_consolidated=self._any_in_move_list(
                        ap_profile.res_name, *ap_kid_orig,
                    ),
                )

            # Minimum-viable household union: head + wife as partners and
            # the head's direct child-role members as children. Skip the
            # union emission when either partner is missing, has no
            # Person, or has no `name_modern` (no stable token for the
            # union res_name) — but still emit the document below.
            # ref_member-driven grandchild / daughter-in-law attachments
            # are a follow-up.
            # Secondary-relationship marital unions: a member with
            # `secondary_role=HUSBAND/WIFE` + `secondary_ref_member=<spouse>`
            # describes a marital relationship reconstructed from
            # cross-document evidence — distinct from their primary role
            # in the source document (e.g. m12 is BROTHER of HEAD per
            # the original RS, AND HUSBAND of m2 per other materials).
            # The primary role/ref_member is preserved untouched. Emit
            # the marital union here so consolidation can fold it into
            # the cross-document bucket via partner-lookup. Runs before
            # the head_only / head+wife branching so it fires regardless
            # of household shape.
            sec_hh_by_num = {x.number: x for x in h.members}
            for sm in h.members:
                sec_role = getattr(sm, "secondary_role", None)
                sec_ref = getattr(sm, "secondary_ref_member", None)
                if sec_role is None or sec_ref is None:
                    continue
                if sec_role not in (CensusRole.HUSBAND, CensusRole.WIFE):
                    continue
                spouse_m = sec_hh_by_num.get(sec_ref)
                if spouse_m is None:
                    continue
                sm_profile = member_profiles.get(sm.number)
                spouse_profile = member_profiles.get(spouse_m.number)
                if sm_profile is None or spouse_profile is None:
                    continue
                if sec_role == CensusRole.HUSBAND:
                    husband_m_sec, _wife_m_sec = sm, spouse_m
                    husband_p_sec, wife_p_sec = sm_profile, spouse_profile
                else:
                    husband_m_sec, _wife_m_sec = spouse_m, sm
                    husband_p_sec, wife_p_sec = spouse_profile, sm_profile
                # Build res_name from the husband's identity so the
                # union id is stable regardless of which side carries
                # the `secondary_role` annotation.
                sec_res = _build_subfamily_union_res_name(
                    husband_m_sec, year=year, h_index=display_id,
                )
                if sec_res is None:
                    continue
                sec_union = GeniUnion(
                    origin=UnionOrigin.ROLL,
                    res_name=sec_res,
                    partner_1=self.consolidation.move_to_new_name(
                        husband_p_sec.res_name,
                    ),
                    partner_2=self.consolidation.move_to_new_name(
                        wife_p_sec.res_name,
                    ),
                )
                self._route_union(
                    sec_union, filename=filename,
                    is_consolidated=self._any_in_move_list(
                        husband_p_sec.res_name,
                        wife_p_sec.res_name,
                    ),
                )

            can_emit_unions = (
                head_member is not None
                and wife_member is not None
                and head_profile is not None
                and wife_profile is not None
                and head_member.person is not None
                and bool(head_member.person.name_modern)
            )
            if not can_emit_unions:
                # Head-only union: when HEAD is recorded but no WIFE,
                # legacy still emitted a `<head>_rs<num>_<year>` union
                # with HEAD as the sole partner and members with
                # effective_ref=1 + no `previous_age` as children.
                # Mirrors legacy's CSV-driven heuristic: members new in
                # this RS (no prev) who relate to the HEAD become
                # children of HEAD's record.
                if (head_member is not None and head_profile is not None
                        and head_member.person is not None
                        and head_member.person.name_modern):
                    head_only_res = _build_subfamily_union_res_name(
                        head_member, year=year,
                    )
                    if head_only_res:
                        ho_children: set[str] = set()
                        # Foster children (приёмыш) whose foster parent is the
                        # HEAD (ref_member unset or →HEAD, or →a member with no
                        # union). Sub-head-pointing foster kids go to Pass (a).
                        ho_foster, _ho_foster_orig = self._foster_children_for(
                            h, member_profiles, head_member.number,
                            head_member.number)
                        ho_orig: list[str] = []
                        # Eligible HEAD-children roles: direct children
                        # (SON/DAUGHTER/STEPSON/STEPDAUGHTER) and step-
                        # siblings of HEAD (BROTHER/SISTER with
                        # `сводный брат`/`сводная сестра` qualifier in
                        # the role-original comment). Full siblings of
                        # HEAD belong to the implied-parent stub union
                        # instead — they share HEAD's parent, not HEAD
                        # himself.
                        ho_child_roles = (
                            CensusRole.SON, CensusRole.DAUGHTER,
                            CensusRole.STEPSON, CensusRole.STEPDAUGHTER,
                        )
                        for c in h.members:
                            if c.number == head_member.number:
                                continue
                            # Foster children are collected via
                            # `_foster_children_for` above (into ho_foster), not
                            # as biological children — skip them here.
                            if c.role in _FOSTER_ROLES:
                                continue
                            # WIFE members are normally skipped as HEAD's
                            # children (they're partners, not descendants).
                            # Exception: a WIFE with `parent_member=HEAD`
                            # IS HEAD's daughter, married to another
                            # household member (typically a SON_IN_LAW).
                            # The WIFE role describes her relationship to
                            # her husband; the `parent_member` annotation
                            # describes her relationship to HEAD.
                            head_num_for_wife_check = (
                                head_member.number
                                if head_member is not None else None
                            )
                            wife_pm = getattr(c, "parent_member", None)
                            if c.role == CensusRole.WIFE and not (
                                wife_pm is not None
                                and head_num_for_wife_check is not None
                                and wife_pm == head_num_for_wife_check
                            ):
                                continue
                            # Members with `previous_age` belong to the
                            # implied-parent stub union when one exists
                            # AND when they're full siblings of HEAD
                            # (BROTHER/SISTER without a step-sibling
                            # qualifier) — those are the only members
                            # the stub claims as its children alongside
                            # HEAD (see stub_children collection at
                            # ~4060). SON/DAUGHTER with `previous_age`
                            # are HEAD's own children, attested by the
                            # prior RS through HEAD himself, not through
                            # the implied grandparent — they belong in
                            # HEAD's union.
                            if (stub_res_name is not None
                                    and getattr(c, "previous_age", None) is not None
                                    and c.role in (CensusRole.BROTHER, CensusRole.SISTER)
                                    and not (c.comment and (
                                        "сводный брат" in c.comment
                                        or "сводная сестра" in c.comment
                                    ))):
                                continue
                            # Members with `parent_member` set typically
                            # have their lineage captured via a hidden-
                            # ancestor union — but only skip when the
                            # parent IS hidden. When parent_member points
                            # at the visible HEAD (e.g., a hidden DAUGHTER
                            # with parent_member=1 + ref_member=husband
                            # to encode SON_IN_LAW + daughter pair), the
                            # member is HEAD's child and should land in
                            # HEAD's union regardless of ref_member.
                            pm = getattr(c, "parent_member", None)
                            members_by_num = {
                                x.number: x for x in h.members
                            }
                            head_num = (
                                head_member.number
                                if head_member is not None else None
                            )
                            if pm is not None:
                                pm_member = members_by_num.get(pm)
                                if (pm_member is not None
                                        and pm_member.is_hidden()):
                                    continue
                                # Visible parent: only include when it's
                                # HEAD itself (otherwise the member is a
                                # grandchild via another visible member).
                                if head_num is None or pm != head_num:
                                    continue
                                # parent_member→HEAD: include c regardless
                                # of ref_member.
                            else:
                                eff_ref = (
                                    c.ref_member
                                    if c.ref_member is not None else 1
                                )
                                if eff_ref != 1:
                                    continue
                            # Skip hidden members ONLY when there's a
                            # hidden HEAD in the household (= an unrecorded
                            # ancestor chain ABOVE the visible head).
                            # Otherwise hidden SONs are head's actual
                            # children (e.g. two hidden sons of the head
                            # need to land in the head's consolidated
                            # union).
                            if c.is_hidden():
                                has_hidden_head = any(
                                    x.role == CensusRole.HEAD and x.is_hidden()
                                    for x in h.members
                                )
                                if has_hidden_head:
                                    continue
                            # Role gate: direct children always count;
                            # BROTHER/SISTER count only when flagged as
                            # step-siblings via "роль в оригинале:
                            # сводный/сводная". Full siblings go to the
                            # stub union, not here.
                            #
                            # Exception: when `parent_member` points
                            # explicitly at HEAD, the member IS HEAD's
                            # child regardless of declared role. Used
                            # for `role=None, parent_member=HEAD,
                            # ref_member=<spouse>` patterns where role
                            # had to be cleared so `ref_member` could
                            # encode the spouse (a `SON` role would
                            # cause `ref_member` to be interpreted as
                            # parent, not spouse).
                            is_step_sibling = bool(
                                c.role in (CensusRole.BROTHER, CensusRole.SISTER)
                                and c.comment
                                and ("сводный брат" in c.comment
                                     or "сводная сестра" in c.comment)
                            )
                            is_explicit_head_child = (
                                pm is not None and head_num is not None
                                and pm == head_num
                            )
                            if (c.role not in ho_child_roles
                                    and not is_step_sibling
                                    and not is_explicit_head_child):
                                continue
                            cp = member_profiles.get(c.number)
                            if cp is None:
                                continue
                            ho_orig.append(cp.res_name)
                            ho_children.add(
                                self.consolidation.move_to_new_name(cp.res_name)
                            )
                        # Rule B: SISTER/BROTHER pointing at a SON/DAUGHTER of
                        # HEAD is genealogically also a child of HEAD (full
                        # sibling of HEAD's child = HEAD's child too).
                        for c in h.members:
                            if c.role not in (CensusRole.BROTHER, CensusRole.SISTER):
                                continue
                            if c.ref_member is None:
                                continue
                            if getattr(c, "parent_member", None) is not None:
                                continue
                            # Step-siblings have a different parent — exclude.
                            if c.comment and (
                                "сводный брат" in c.comment
                                or "сводная сестра" in c.comment
                            ):
                                continue
                            ref_target = next(
                                (x for x in h.members if x.number == c.ref_member),
                                None,
                            )
                            if ref_target is None:
                                continue
                            if ref_target.role not in ho_child_roles:
                                continue
                            target_eff_ref = (
                                ref_target.ref_member
                                if ref_target.ref_member is not None else 1
                            )
                            if target_eff_ref != 1:
                                continue
                            cp = member_profiles.get(c.number)
                            if cp is None:
                                continue
                            ho_orig.append(cp.res_name)
                            ho_children.add(
                                self.consolidation.move_to_new_name(cp.res_name)
                            )
                        if ho_children or ho_foster:
                            ho_union = GeniUnion(
                                origin=UnionOrigin.ROLL,
                                res_name=head_only_res,
                                partner_1=self.consolidation.move_to_new_name(
                                    head_profile.res_name,
                                ),
                                partner_2=None,
                                children=ho_children,
                                foster_children=ho_foster,
                            )
                            self._route_union(
                                ho_union, filename=filename,
                                is_consolidated=self._any_in_move_list(
                                    head_profile.res_name, *ho_orig,
                                ),
                            )
                # For households with no WIFE, still emit sub-family
                # unions where any member's `ref_member` points at a
                # `#hidden` ancestor (string record_number). These were
                # generated by the legacy generator via patronymic
                # matching. Pass (b) below handles this for can_emit
                # households; mirror the same logic here for no-WIFE
                # households so HEAD/BROTHER/NEPHEW/COUSIN refs are
                # not silently dropped.
                hh_members_by_num = {x.number: x for x in h.members}
                nowife_parent_to_children: dict[int, list[Any]] = {}
                for c in h.members:
                    parent_ref = _resolve_parent_ref(c, hh_members_by_num)
                    if parent_ref is None:
                        continue
                    nowife_parent_to_children.setdefault(
                        parent_ref, []
                    ).append(c)
                for pnum, kids in nowife_parent_to_children.items():
                    # `parent_member` may dangle when a household was
                    # split (the referenced ancestor moved to a sibling
                    # household). Silently skip — it's safe because the
                    # union would be cross-household anyway.
                    p = hh_members_by_num.get(pnum)
                    if p is None:
                        continue
                    # Skip the HEAD: the head-only union path above is
                    # the canonical emit point for HEAD→child relationships
                    # in no-WIFE households. Without this guard a member
                    # with `ref_member=head_num` (e.g. a hidden DAUGHTER
                    # pointing at the head) would cause
                    # this loop to emit a second union with the same
                    # res_name as the head-only union — invalid HCL.
                    if head_member is not None and pnum == head_member.number:
                        continue
                    # Skip parents that already get a sub-family union
                    # via Pass (a) below — when a WIFE explicitly points
                    # at this parent via ref_member, Pass (a) emits the
                    # head+wife→children union with the same res_name,
                    # so Pass (b) here would create a duplicate (e.g.
                    # m2 has WIFE m3 with ref_member=2 → Pass (a) emits
                    # m2+m3→child; without this guard, Pass (b) would
                    # also emit m2→child with the same res_name).
                    if any(
                        (x.role == CensusRole.WIFE
                         or (x.role == CensusRole.DAUGHTER and x.is_hidden()))
                        and x.ref_member == pnum
                        for x in h.members
                    ):
                        continue
                    p_profile = member_profiles.get(pnum)
                    if p_profile is None:
                        continue
                    p_res = _build_subfamily_union_res_name(
                        p, year=year, h_index=display_id,
                    )
                    if p_res is None:
                        continue
                    kid_res: set[str] = set()
                    kid_orig: list[str] = []
                    for c in kids:
                        cp = member_profiles.get(c.number)
                        if cp is None:
                            continue
                        kid_orig.append(cp.res_name)
                        kid_res.add(
                            self.consolidation.move_to_new_name(cp.res_name)
                        )
                    # Spouse-from-ref_member inference fires ONLY for
                    # HIDDEN parents — for them, `ref_member` is a
                    # deliberate encoding of the spouse (we couldn't
                    # add a real WIFE row because the person is
                    # synthesized). For VISIBLE parents `ref_member`
                    # encodes their own upward link (e.g. SON's
                    # ref_member points at their father), not a
                    # spouse, so reading it as partner_2 would
                    # mistakenly bind a parent and child as a couple
                    # (e.g. m14 SON of m13 — without this guard,
                    # Pass (b) would emit m14+m13→grandchild).
                    #
                    # Also skip when the hidden member's role is a
                    # CHILD role (SON/DAUGHTER/STEPSON/STEPDAUGHTER).
                    # For child roles, `ref_member` encodes the parent.
                    # Concrete regression shape: a hidden m12 SON with
                    # ref_member=2 (his father) — without this guard, the
                    # father is wrongly paired as the son's spouse,
                    # dragging the son's daughter into the father's union.
                    partner_2_res = None
                    partner_2_orig = []
                    if (p.is_hidden()
                            and p.role not in (CensusRole.SON, CensusRole.DAUGHTER,
                                               CensusRole.STEPSON, CensusRole.STEPDAUGHTER)):
                        spouse_ref = getattr(p, "ref_member", None)
                        if spouse_ref is not None:
                            spouse = hh_members_by_num.get(spouse_ref)
                            if spouse is not None and not spouse.is_hidden():
                                spouse_profile = member_profiles.get(spouse.number)
                                if spouse_profile is not None:
                                    partner_2_res = (
                                        self.consolidation.move_to_new_name(
                                            spouse_profile.res_name,
                                        )
                                    )
                                    partner_2_orig.append(spouse_profile.res_name)
                    # Foster children (приёмыш) whose ref_member names THIS
                    # sub-family parent ride along in the same union — so a
                    # parent with both a biological and a foster child gets ONE
                    # union, not two (e.g. a parent with a son and a
                    # приёмыш).
                    p_foster, p_foster_orig = self._foster_children_for(
                        h, member_profiles, pnum,
                        head_member.number if head_member is not None else pnum)
                    p_union = GeniUnion(
                        origin=UnionOrigin.ROLL,
                        res_name=p_res,
                        partner_1=self.consolidation.move_to_new_name(
                            p_profile.res_name,
                        ),
                        partner_2=partner_2_res,
                        children=kid_res or None,
                        foster_children=p_foster or None,
                    )
                    self._route_union(
                        p_union, filename=filename,
                        is_consolidated=self._any_in_move_list(
                            p_profile.res_name, *kid_orig, *partner_2_orig,
                            *p_foster_orig,
                        ),
                    )
                # No-WIFE branch also runs Pass (a): a WIFE whose
                # `ref_member` points at a non-head member (e.g. a
                # brother) defines her own sub-family union. Without
                # this, e.g. a household of a HEAD recruited away, his
                # BROTHER and the brother's WIFE (ref→ the brother) —
                # silently drops the brother+wife union.
                head_num_for_pass_a = (
                    head_member.number if head_member is not None else None
                )
                for sub_wife in h.members:
                    # Pass (a) also handles hidden DAUGHTER members whose
                    # `ref_member` points at a non-HEAD member (encoding
                    # the SON_IN_LAW + hidden DAUGHTER marital pair, e.g.,
                    # a hidden DAUGHTER with ref=8 (her husband). The
                    # DAUGHTER role keeps the document
                    # text correct (still HEAD's daughter via `(1)` if
                    # `parent_member=1` is set) while the WIFE-of-non-head
                    # routing emits the husband-wife sub-family union.
                    is_dil_pair = (
                        sub_wife.role == CensusRole.DAUGHTER
                        and sub_wife.is_hidden()
                    )
                    if (sub_wife.role != CensusRole.WIFE
                            and not is_dil_pair):
                        continue
                    if sub_wife.ref_member is None:
                        continue
                    if (head_num_for_pass_a is not None
                            and sub_wife.ref_member == head_num_for_pass_a):
                        continue
                    sub_head = next(
                        (x for x in h.members
                         if x.number == sub_wife.ref_member),
                        None,
                    )
                    if sub_head is None:
                        continue
                    sub_head_profile = member_profiles.get(sub_head.number)
                    sub_wife_profile = member_profiles.get(sub_wife.number)
                    if sub_head_profile is None or sub_wife_profile is None:
                        continue
                    sub_res = _build_subfamily_union_res_name(
                        sub_head, year=year,
                    )
                    if sub_res is None:
                        continue
                    sub_children: set[str] = set()
                    sub_child_orig: list[str] = []
                    for c in h.members:
                        # Skip the wife/DIL-pair member herself — she's
                        # the partner, not a child of her own union.
                        if c.number == sub_wife.number:
                            continue
                        if getattr(c, "parent_member", None) == sub_head.number:
                            # Explicit typed upward link — honoured
                            # regardless of role (mirrors the with-WIFE
                            # branch's pass (a); see CPL001).
                            pass
                        else:
                            if c.ref_member != sub_head.number:
                                continue
                            if c.role not in (
                                CensusRole.SON, CensusRole.DAUGHTER,
                                CensusRole.STEPSON, CensusRole.STEPDAUGHTER,
                            ):
                                continue
                            # Step-children belong to their biological
                            # parents' union (built by the hidden-ancestor
                            # pass via `parent_member` — the branch above
                            # when this sub-head IS the biological parent),
                            # never the step-parent's.
                            if c.role in (CensusRole.STEPSON,
                                          CensusRole.STEPDAUGHTER):
                                continue
                        # Secondary-mother routing for a sub-family father
                        # with two wives (e.g. a man widowed by his first
                        # wife m14, remarried to a widow m15).
                        # A child annotated `secondary_role=SON/DAUGHTER` +
                        # `secondary_ref_member=<wife>` belongs to THAT
                        # wife's union only; skip it for the other wife.
                        # Mirrors the head+wife path's filter — without it
                        # both wives' unions get every child (tree conflict).
                        sm_role = getattr(c, "secondary_role", None)
                        sm_ref = getattr(c, "secondary_ref_member", None)
                        if (sm_role in (CensusRole.SON, CensusRole.DAUGHTER)
                                and sm_ref is not None
                                and sm_ref != sub_wife.number):
                            continue
                        cp = member_profiles.get(c.number)
                        if cp is None:
                            continue
                        sub_child_orig.append(cp.res_name)
                        sub_children.add(
                            self.consolidation.move_to_new_name(cp.res_name)
                        )
                    # Foster children (приёмыш) whose ref_member names THIS
                    # sub-head attach to the sub-head's union foster_children
                    # (mirrors the with-WIFE branch's pass (a)). Covers a
                    # female-head (widow) household whose son took in a приёмыш
                    # (a приёмная дочь of the widow head's son).
                    sub_foster, sub_foster_orig = self._foster_children_for(
                        h, member_profiles, sub_head.number,
                        head_member.number if head_member is not None else sub_head.number)
                    sub_union = GeniUnion(
                        origin=UnionOrigin.ROLL,
                        res_name=sub_res,
                        partner_1=self.consolidation.move_to_new_name(
                            sub_head_profile.res_name,
                        ),
                        partner_2=self.consolidation.move_to_new_name(
                            sub_wife_profile.res_name,
                        ),
                        children=sub_children or None,
                        foster_children=sub_foster or None,
                    )
                    self._route_union(
                        sub_union, filename=filename,
                        is_consolidated=self._any_in_move_list(
                            sub_head_profile.res_name,
                            sub_wife_profile.res_name,
                            *sub_child_orig,
                            *sub_foster_orig,
                        ),
                    )

                # Foster parents without a couple/head union get a single-
                # partner foster union (same as the with-WIFE branch below).
                if head_member is not None:
                    self._emit_lone_foster_parent_unions(
                        h, member_profiles, head_member.number, year, filename,
                        display_id)

                # Still emit the household document — many one-person
                # households (HEAD only, no WIFE) carry no union but
                # should retain their `census_of_the_family_number_…`
                # document.
                self._emit_census_household_document(
                    filename=filename, records=records,
                    household=h, h_index=display_id,
                )
                continue

            # Hidden-ancestor sub-family unions emit BEFORE the head+wife
            # union (and before pass (a)) — legacy's per-household order
            # is `[hidden_ancestor_unions, head_wife_union, pass_a, pass_b]`.
            # Compute the hidden subset here; pass (b) below filters them
            # out.
            hh_members_by_num = {x.number: x for x in h.members}
            hidden_parent_to_children: dict[int, list[Any]] = {}
            for c in h.members:
                parent_ref = _resolve_parent_ref(c, hh_members_by_num)
                if parent_ref is None:
                    continue
                p = hh_members_by_num.get(parent_ref)
                if p is None or not p.is_hidden():
                    continue
                hidden_parent_to_children.setdefault(parent_ref, []).append(c)
            for pnum, kids in hidden_parent_to_children.items():
                p = hh_members_by_num[pnum]
                p_profile = member_profiles.get(pnum)
                if p_profile is None:
                    continue
                p_res = _build_subfamily_union_res_name(
                    p, year=year, h_index=display_id,
                )
                if p_res is None:
                    continue
                kid_res: set[str] = set()
                kid_orig: list[str] = []
                for c in kids:
                    cp = member_profiles.get(c.number)
                    if cp is None:
                        continue
                    kid_orig.append(cp.res_name)
                    kid_res.add(
                        self.consolidation.move_to_new_name(cp.res_name)
                    )
                # When the hidden parent declares a `ref_member`
                # pointing at a visible non-head member, treat that
                # member as the second partner of the union. Use case:
                # a stepdaughter whose biological father is a hidden
                # ancestor and biological mother is the head's current
                # wife — declaring `ref_member=<wife>` on the hidden
                # father lets us reconstruct the bio-parent couple
                # without inventing a duplicate mother record.
                #
                # Skip the inference when the hidden member's ROLE is
                # a child role (SON/DAUGHTER/STEPSON/STEPDAUGHTER) —
                # for child roles, `ref_member` encodes the parent,
                # NOT the spouse. Concrete regression shape: a household
                # has a hidden m12 SON with ref_member=2 (his father).
                # Without this guard, the father was paired as the son's
                # spouse, dragging the son's daughter into the father's
                # union.
                partner_2_res = None
                partner_2_orig = []
                spouse_ref = getattr(p, "ref_member", None)
                if (spouse_ref is not None
                        and p.role not in (CensusRole.SON, CensusRole.DAUGHTER,
                                           CensusRole.STEPSON, CensusRole.STEPDAUGHTER)):
                    spouse = hh_members_by_num.get(spouse_ref)
                    if spouse is not None and not spouse.is_hidden():
                        spouse_profile = member_profiles.get(spouse.number)
                        if spouse_profile is not None:
                            partner_2_res = (
                                self.consolidation.move_to_new_name(
                                    spouse_profile.res_name,
                                )
                            )
                            partner_2_orig.append(spouse_profile.res_name)
                p_union = GeniUnion(
                    origin=UnionOrigin.ROLL,
                    res_name=p_res,
                    partner_1=self.consolidation.move_to_new_name(
                        p_profile.res_name,
                    ),
                    partner_2=partner_2_res,
                    children=kid_res or None,
                )
                self._route_union(
                    p_union, filename=filename,
                    is_consolidated=self._any_in_move_list(
                        p_profile.res_name, *kid_orig, *partner_2_orig,
                    ),
                )

            # head/wife stay Optional through the long member scan above, but
            # every path from here dereferences all four — the union res_name,
            # the foster lookup, and both partners of the union itself. Today a
            # household missing any of them raises a bare AttributeError several
            # hundred lines from the cause; name the household instead. This is
            # unreachable for current data (all four villages generate), so it
            # changes no output — it just stops a future gap from surfacing as
            # "'NoneType' object has no attribute 'person'".
            if (head_member is None or wife_member is None
                    or head_profile is None or wife_profile is None):
                missing = [
                    name for name, val in (
                        ("head member", head_member), ("wife member", wife_member),
                        ("head profile", head_profile), ("wife profile", wife_profile),
                    ) if val is None
                ]
                raise ValueError(
                    f"census household {display_id} ({year}): cannot build the "
                    f"head+wife union — no {', no '.join(missing)}. Check the "
                    f"household's HEAD/WIFE roles in the DSL."
                )

            # Union res_name — two conventions:
            #  - Short form `{head_canon}_rs{record_number}_{year}`
            #    when the head member carries a `record_number` (typed
            #    field sourced from the CSV `№ п/п` column). Matches
            #    the earlier generator.
            #  - Long form `{head}_and_{wife}_{display_id}_{year}`
            #    fallback for DSLs that haven't been migrated yet.
            short_form = _build_subfamily_union_res_name(
                head_member, year=year,
            )
            if short_form:
                union_res_name = short_form
            else:
                head_first = head_member.person.name_modern or ""
                head_mid = head_member.person.patr_modern or ""
                head_last = head_member.person.last_name_modern or ""
                wife_first = wife_member.person.name_modern or ""
                wife_mid = wife_member.person.patr_modern or ""
                wife_last = wife_member.person.last_name_modern or ""
                union_res_name = generate_res_name(
                    f"{head_first} {head_mid} {head_last} and "
                    f"{wife_first} {wife_mid} {wife_last} {display_id}_{year}"
                )

            # Direct children of the HEAD are wired into the head+wife union.
            # An explicit `ref_member` normally names an INTERMEDIATE parent
            # (a grandson whose father is a son in the same household), and
            # those belong to that parent's union instead — but `ref_member`
            # pointing AT THE HEAD names the head himself, which is what an
            # unset `ref_member` already means. Treating the two the same is
            # what the head-only branch above does (`eff_ref`); before this
            # they disagreed, and a child written `SON, ref_member=<head>`
            # was emitted attached to NO union at all (54 such children in
            # one roll alone).
            children_res_names = set()
            child_orig_res_names: list[str] = []  # pre-move; for routing check
            head_num_for_children = (
                head_member.number if head_member is not None else None
            )
            for m in h.members:
                if m.role not in child_roles:
                    continue
                if (m.ref_member is not None
                        and m.ref_member != head_num_for_children):
                    continue
                # Lineage already attributed elsewhere via parent_member.
                if getattr(m, "parent_member", None) is not None:
                    continue
                # A child with an explicit secondary-mother hint
                # (`secondary_role=SON/DAUGHTER` + `secondary_ref_member`
                # at a WIFE other than the primary `wife_member`) belongs
                # to that wife's union, emitted separately below.
                sec_mom_role = getattr(m, "secondary_role", None)
                sec_mom_ref = getattr(m, "secondary_ref_member", None)
                if (sec_mom_role in (CensusRole.SON, CensusRole.DAUGHTER)
                        and sec_mom_ref is not None
                        and sec_mom_ref != wife_member.number):
                    continue
                # Hidden SON members ARE sometimes the head's actual
                # children (just not enumerated by name in the source —
                # encoded as hidden=True placeholders for the GRANDSON
                # entries that reference them via parent_member). Only
                # exclude hidden SONs as the head's children when the
                # household contains a hidden HEAD (= an unrecorded
                # ancestor chain ABOVE the visible head). In that case
                # hidden SONs are part of that ancestor chain (e.g.
                # a hidden SON of a hidden ancestor, where the visible
                # head is that SON's son, not father). When all HEADs are
                # visible, hidden SONs are siblings of head's other
                # visible children (the head's actual sons).
                if m.is_hidden():
                    has_hidden_head = any(
                        x.role == CensusRole.HEAD and x.is_hidden()
                        for x in h.members
                    )
                    if has_hidden_head:
                        continue
                child_profile = member_profiles.get(m.number)
                if child_profile is None:
                    continue
                child_orig_res_names.append(child_profile.res_name)
                children_res_names.add(
                    self.consolidation.move_to_new_name(child_profile.res_name)
                )
            # Rule B: SISTER/BROTHER pointing at a SON/DAUGHTER of HEAD
            # is genealogically also HEAD's child (full sibling of a
            # head-child = head-child too). Mirrors the same logic in
            # the head_only emission branch above.
            for m in h.members:
                if m.role not in (CensusRole.BROTHER, CensusRole.SISTER):
                    continue
                if m.ref_member is None:
                    continue
                if getattr(m, "parent_member", None) is not None:
                    continue
                if m.comment and (
                    "сводный брат" in m.comment
                    or "сводная сестра" in m.comment
                ):
                    continue
                ref_target = next(
                    (x for x in h.members if x.number == m.ref_member),
                    None,
                )
                if ref_target is None:
                    continue
                if ref_target.role not in child_roles:
                    continue
                target_eff_ref = (
                    ref_target.ref_member
                    if ref_target.ref_member is not None
                    else (head_member.number if head_member is not None else None)
                )
                if (head_member is not None
                        and target_eff_ref != head_member.number):
                    continue
                child_profile = member_profiles.get(m.number)
                if child_profile is None:
                    continue
                child_orig_res_names.append(child_profile.res_name)
                children_res_names.add(
                    self.consolidation.move_to_new_name(child_profile.res_name)
                )

            # Foster children (приёмыш) whose foster parent is the HEAD land in
            # the head+wife couple's union via foster_children (Geni "foster"
            # modifier), NOT as biological children. Those whose ref_member
            # names a sub-head are attached to that sub-head's union in Pass (a).
            foster_res_names, foster_orig_res_names = self._foster_children_for(
                h, member_profiles, head_member.number, head_member.number)

            union = GeniUnion(
                origin=UnionOrigin.ROLL,
                res_name=union_res_name,
                partner_1=self.consolidation.move_to_new_name(head_profile.res_name),
                partner_2=self.consolidation.move_to_new_name(wife_profile.res_name),
                children=children_res_names or None,
                foster_children=foster_res_names or None,
            )
            # Route through `_route_union` so census unions whose head,
            # wife, OR any child profile is in `profile_move_list` land
            # in `consolidated_unions.tf` instead of the per-year file.
            # Legacy's `rs_*.tf` files have been trimmed to drop
            # consolidated head+wife unions even when only a child is
            # consolidated (mirrors the earlier generator's
            # `at_least_one_consolidated_profile(*union_profile_res_names)`
            # where `union_profile_res_names` includes children).
            # `in_profile_move_list` expects the per-year (pre-move)
            # res_name, so check against the originals, not the moved
            # names that the union resource itself carries.
            consolidated_partner = self._any_in_move_list(
                head_profile.res_name,
                wife_profile.res_name,
                *child_orig_res_names,
                *foster_orig_res_names,
            )
            self._route_union(
                union, filename=filename, is_consolidated=consolidated_partner,
            )

            # Secondary-mother unions: children annotated with
            # `secondary_role=SON/DAUGHTER` + `secondary_ref_member` at a
            # WIFE other than the primary `wife_member` (e.g. the head's
            # 2nd wife bore the children, while the 1st wife — the
            # consolidatable partner the tie-break picks — had died years
            # earlier). Each distinct secondary
            # wife gets her own head+wife union; her children were
            # excluded from the primary union above.
            sec_mother_groups: dict[int, list[Any]] = {}
            for m in h.members:
                sm_role = getattr(m, "secondary_role", None)
                sm_ref = getattr(m, "secondary_ref_member", None)
                if sm_role not in (CensusRole.SON, CensusRole.DAUGHTER):
                    continue
                if sm_ref is None or sm_ref == wife_member.number:
                    continue
                sec_mother_groups.setdefault(sm_ref, []).append(m)
            for sec_wife_num, sec_kids in sec_mother_groups.items():
                sec_wife_member = next(
                    (x for x in h.members if x.number == sec_wife_num),
                    None,
                )
                if (sec_wife_member is None
                        or sec_wife_member.person is None):
                    continue
                # Only pair a secondary wife with the HEAD when she is one of
                # the HEAD's wives (no ref_member, or ref→head). A secondary
                # wife whose ref_member points at a non-head member is a
                # SUB-FAMILY father's wife (a wife whose ref→ a sub-head,
                # not the head) — her children's union is
                # emitted by Pass (a) below, so pairing her with the head here
                # would fabricate a spurious head+wife union.
                if (sec_wife_member.ref_member is not None
                        and head_member is not None
                        and sec_wife_member.ref_member != head_member.number):
                    continue
                sec_wife_profile = member_profiles.get(sec_wife_num)
                if sec_wife_profile is None:
                    continue
                sec_kid_res: set[str] = set()
                sec_kid_orig: list[str] = []
                for k in sec_kids:
                    kp = member_profiles.get(k.number)
                    if kp is None:
                        continue
                    sec_kid_orig.append(kp.res_name)
                    sec_kid_res.add(
                        self.consolidation.move_to_new_name(kp.res_name)
                    )
                if not sec_kid_res:
                    continue
                hf = head_member.person.name_modern or ""
                hm = head_member.person.patr_modern or ""
                hl = head_member.person.last_name_modern or ""
                sw_f = sec_wife_member.person.name_modern or ""
                sw_m = sec_wife_member.person.patr_modern or ""
                sw_l = sec_wife_member.person.last_name_modern or ""
                sec_union = GeniUnion(
                    origin=UnionOrigin.ROLL,
                    res_name=generate_res_name(
                        f"{hf} {hm} {hl} and "
                        f"{sw_f} {sw_m} {sw_l} {display_id}_{year}"
                    ),
                    partner_1=self.consolidation.move_to_new_name(
                        head_profile.res_name,
                    ),
                    partner_2=self.consolidation.move_to_new_name(
                        sec_wife_profile.res_name,
                    ),
                    children=sec_kid_res,
                )
                self._route_union(
                    sec_union, filename=filename,
                    is_consolidated=self._any_in_move_list(
                        head_profile.res_name,
                        sec_wife_profile.res_name,
                        *sec_kid_orig,
                    ),
                )

            head_num = head_member.number if head_member else None
            seen_subhead_nums: set[int] = set()

            # Pass (a): WIFE → ref_member sub-head pairings.
            for sub_wife in h.members:
                if sub_wife.role != CensusRole.WIFE:
                    continue
                if sub_wife.ref_member is None:
                    continue
                if head_num is not None and sub_wife.ref_member == head_num:
                    continue
                sub_head = next(
                    (x for x in h.members if x.number == sub_wife.ref_member),
                    None,
                )
                if sub_head is None:
                    continue
                sub_head_profile = member_profiles.get(sub_head.number)
                sub_wife_profile = member_profiles.get(sub_wife.number)
                if sub_head_profile is None or sub_wife_profile is None:
                    continue
                sub_res = _build_subfamily_union_res_name(sub_head, year=year)
                if sub_res is None:
                    continue
                sub_children: set[str] = set()
                sub_child_orig: list[str] = []
                for c in h.members:
                    if getattr(c, "parent_member", None) == sub_head.number:
                        # Explicit typed upward link — honoured regardless
                        # of role. Covers the 1897 посемейные списки shape:
                        # a source-faithful GRANDSON of HEAD whose father
                        # is this wife-paired sub-head (ref_member alone is
                        # NOT a parent link for lineage roles — CPL001).
                        pass
                    else:
                        if c.ref_member != sub_head.number:
                            continue
                        if c.role not in child_roles:
                            continue
                        # A step-child is the natural child of only ONE
                        # partner (by a prior/other spouse). Its `ref_member`
                        # points at the step-parent (this sub-head), but it
                        # belongs in its biological parents' union — built
                        # separately by the hidden-ancestor pass via
                        # `parent_member` (handled by the branch above when
                        # this sub-head IS the biological parent). (Geni's
                        # `adopted_children` field is for legal adoption
                        # only, never step-kids.)
                        if c.role in (CensusRole.STEPSON, CensusRole.STEPDAUGHTER):
                            continue
                    # Secondary-mother routing for a sub-family father with
                    # two wives (a man widowed by his first wife m14,
                    # remarried to a widow m15). A child annotated
                    # `secondary_role=SON/DAUGHTER` + `secondary_ref_member=
                    # <wife>` belongs to THAT wife's union only; skip it for
                    # the other wife. Without it both sub-wife unions get
                    # every child (a duplicate_parents tree conflict).
                    sm_role = getattr(c, "secondary_role", None)
                    sm_ref = getattr(c, "secondary_ref_member", None)
                    if (sm_role in (CensusRole.SON, CensusRole.DAUGHTER)
                            and sm_ref is not None
                            and sm_ref != sub_wife.number):
                        continue
                    cp = member_profiles.get(c.number)
                    if cp is None:
                        continue
                    sub_child_orig.append(cp.res_name)
                    sub_children.add(
                        self.consolidation.move_to_new_name(cp.res_name)
                    )
                # Foster children (приёмыш) whose ref_member names THIS sub-head
                # attach to the sub-head's union foster_children (Geni "foster"),
                # e.g. a «приемный сын» of a SON of the head, not of the
                # head himself.
                sub_foster, sub_foster_orig = self._foster_children_for(
                    h, member_profiles, sub_head.number,
                    head_member.number if head_member is not None else sub_head.number)
                sub_union = GeniUnion(
                    origin=UnionOrigin.ROLL,
                    res_name=sub_res,
                    partner_1=self.consolidation.move_to_new_name(
                        sub_head_profile.res_name,
                    ),
                    partner_2=self.consolidation.move_to_new_name(
                        sub_wife_profile.res_name,
                    ),
                    children=sub_children or None,
                    foster_children=sub_foster or None,
                )
                sub_consolidated = self._any_in_move_list(
                    sub_head_profile.res_name,
                    sub_wife_profile.res_name,
                    *sub_foster_orig,
                    *sub_child_orig,
                )
                self._route_union(
                    sub_union, filename=filename,
                    is_consolidated=sub_consolidated,
                )
                seen_subhead_nums.add(sub_head.number)

            # Rule A: DAUGHTER_IN_LAW (сноха) with default ref→HEAD
            # is the wife of one of HEAD's sons. When the household has
            # exactly one deceased SON, she's unambiguously his widow —
            # emit a sub-family union pairing them. Mirrors legacy's
            # CSV-driven inference where сноха role implied a son-of-head
            # husband and a single dead son disambiguated it.
            for dil in h.members:
                if dil.role != CensusRole.DAUGHTER_IN_LAW:
                    continue
                eff_ref = (
                    dil.ref_member if dil.ref_member is not None
                    else head_num
                )
                if head_num is None or eff_ref != head_num:
                    continue
                # Only count direct SONs of HEAD (no ref_member, or
                # ref_member→HEAD). SONs with ref_member→another visible
                # member are grandsons via that member's lineage.
                dead_sons = [
                    m for m in h.members
                    if m.role == CensusRole.SON
                    and m.departure_reason == "умер"
                    and (m.ref_member is None or m.ref_member == head_num)
                ]
                if len(dead_sons) != 1:
                    continue
                sub_head = dead_sons[0]
                if sub_head.number in seen_subhead_nums:
                    continue
                sub_head_profile = member_profiles.get(sub_head.number)
                dil_profile = member_profiles.get(dil.number)
                if sub_head_profile is None or dil_profile is None:
                    continue
                sub_res = _build_subfamily_union_res_name(sub_head, year=year)
                if sub_res is None:
                    continue
                sub_children = set()
                sub_child_orig = []
                for c in h.members:
                    if getattr(c, "parent_member", None) == sub_head.number:
                        # Explicit typed upward link — honoured regardless
                        # of role (mirrors pass (a); see CPL001).
                        pass
                    else:
                        if c.ref_member != sub_head.number:
                            continue
                        if c.role not in child_roles:
                            continue
                        # A step-child is the natural child of only ONE
                        # partner (by a prior/other spouse). Its `ref_member`
                        # points at the step-parent (this sub-head), but it
                        # belongs in its biological parents' union — built
                        # separately by the hidden-ancestor pass via
                        # `parent_member` (handled by the branch above when
                        # this sub-head IS the biological parent). (Geni's
                        # `adopted_children` field is for legal adoption
                        # only, never step-kids.)
                        if c.role in (CensusRole.STEPSON, CensusRole.STEPDAUGHTER):
                            continue
                    cp = member_profiles.get(c.number)
                    if cp is None:
                        continue
                    sub_child_orig.append(cp.res_name)
                    sub_children.add(
                        self.consolidation.move_to_new_name(cp.res_name)
                    )
                sub_union = GeniUnion(
                    origin=UnionOrigin.ROLL,
                    res_name=sub_res,
                    partner_1=self.consolidation.move_to_new_name(
                        sub_head_profile.res_name,
                    ),
                    partner_2=self.consolidation.move_to_new_name(
                        dil_profile.res_name,
                    ),
                    children=sub_children or None,
                )
                self._route_union(
                    sub_union, filename=filename,
                    is_consolidated=self._any_in_move_list(
                        sub_head_profile.res_name,
                        dil_profile.res_name,
                        *sub_child_orig,
                    ),
                )
                seen_subhead_nums.add(sub_head.number)

            # Pass (b): lone sub-heads — members with children pointing
            # at them via ref_member but no WIFE pairing. Standard case
            # only counts child roles (SON/DAUGHTER/STEPSON/STEPDAUGHTER)
            # — siblings/cousins linked by ref_member don't form a
            # parent-child union. Exception: when the referenced parent
            # is itself a `#hidden` ancestor (string record_number, role
            # often None), accept ANY role for the descendant. This
            # captures patterns like a HEAD whose father is a hidden
            # placeholder in the same household — legacy emitted these
            # via patronymic matching, the typed-DSL way is to set
            # ref_member explicitly.
            members_by_num = {x.number: x for x in h.members}
            parent_to_children: dict[int, list[Any]] = {}
            for c in h.members:
                parent_ref = _resolve_parent_ref(c, members_by_num)
                if parent_ref is None:
                    continue
                # Hidden-ancestor entries already emitted before the
                # head+wife union above — skip here.
                p = members_by_num.get(parent_ref)
                if p is not None and p.is_hidden():
                    continue
                parent_to_children.setdefault(parent_ref, []).append(c)
            for parent_num, kids in parent_to_children.items():
                if parent_num in seen_subhead_nums:
                    continue
                if head_num is not None and parent_num == head_num:
                    continue
                parent = next(
                    (x for x in h.members if x.number == parent_num), None,
                )
                if parent is None:
                    continue
                parent_profile = member_profiles.get(parent_num)
                if parent_profile is None:
                    continue
                lone_res = _build_subfamily_union_res_name(
                    parent, year=year, h_index=display_id,
                )
                if lone_res is None:
                    continue
                lone_children: set[str] = set()
                lone_child_orig: list[str] = []
                for c in kids:
                    cp = member_profiles.get(c.number)
                    if cp is None:
                        continue
                    lone_child_orig.append(cp.res_name)
                    lone_children.add(
                        self.consolidation.move_to_new_name(cp.res_name)
                    )
                # Foster children (приёмыш) of this lone sub-head ride along in
                # the same union (see the no-WIFE branch's equivalent).
                lone_foster, lone_foster_orig = self._foster_children_for(
                    h, member_profiles, parent_num,
                    head_member.number if head_member is not None else parent_num)
                lone_union = GeniUnion(
                    origin=UnionOrigin.ROLL,
                    res_name=lone_res,
                    partner_1=self.consolidation.move_to_new_name(
                        parent_profile.res_name,
                    ),
                    partner_2=None,
                    children=lone_children or None,
                    foster_children=lone_foster or None,
                )
                lone_consolidated = self._any_in_move_list(
                    parent_profile.res_name,
                    *lone_child_orig,
                    *lone_foster_orig,
                )
                self._route_union(
                    lone_union, filename=filename,
                    is_consolidated=lone_consolidated,
                )

            # Foster parents (приёмный родитель) who have no couple/head union
            # of their own get a single-partner foster union. Runs after all
            # biological unions so `covered` reflects every head/sub-head pairing.
            if head_member is not None:
                self._emit_lone_foster_parent_unions(
                    h, member_profiles, head_member.number, year, filename,
                    display_id)

            # Cat F: household document lands AFTER the member profiles
            # AND after the head+wife and sub-family unions, matching the
            # legacy-committed `rs_*.tf` per-family order
            # `[profiles, head_union, sub_unions, document]`.
            # `_emit_census_household_document` reconstructs profile
            # res_names deterministically, so it doesn't need the
            # `member_profiles` dict — it just re-derives what the loop
            # above produced.
            self._emit_census_household_document(
                filename=filename, records=records, household=h, h_index=display_id,
            )

    def _emit_census_household_document(self, *, filename, records, household, h_index):
        """Cat F: render the `census_of_the_family_number_N_...` document
        resource for one household and append to the per-file output.
        Mirrors legacy's 20-space-indented heredoc body with a header
        block (archive/fund/inventory/case/list/family-number) and a
        per-member table.
        """
        year = records.year
        archive_suffix = getattr(records, "archive_suffix", None)
        # Legacy generate_res_name lowercases + transliterates the suffix,
        # so '100-1-1-Собакевичево' becomes '100-1-1-sobakevichevo'. Mirror that
        # for the doc res_name (the filename / archive_suffix elsewhere
        # keeps the original Cyrillic).
        archive_suffix_res = (
            generate_res_name(archive_suffix) if archive_suffix else None
        )
        # Non-revision household sources rename both halves of the document's
        # identity: an исповедная роспись counts «двор», not «семья», and
        # keys its resources on `confession_of_the_household_number_…` so the
        # two sources can coexist in one year. Census defaults unchanged.
        res_prefix = records.doc_res_prefix
        unit_label = records.household_label
        doc_res_name = (
            f"{res_prefix}_{h_index}_{year}_{archive_suffix_res}"
            if archive_suffix_res else
            f"{res_prefix}_{h_index}_{year}"
        )
        self._document_for_record[household] = doc_res_name
        doc_type = getattr(records, "document_type", None) or "Ревизская сказка"
        title = f"{doc_type} {records.village} {year}: {unit_label} {h_index}"
        list_page = household.page or ""
        district = getattr(records, "district", None)
        volost = getattr(records, "volost", None)
        if district and volost:
            district_line = f"Счетный участок: {district} ({volost} волость)"
        elif district:
            district_line = f"Счетный участок: {district}"
        elif volost:
            district_line = f"Волость: {volost}"
        else:
            district_line = None
        header_lines = [
            title,
            f"Архив: {getattr(household, 'archive', None) or records.archive}",
            f"Фонд: {getattr(household, 'fund', None) or records.fund}",
            f"Опись: {getattr(household, 'inventory', None) or records.inventory}",
            f"Дело: {getattr(household, 'case', None) or records.case}",
        ]
        if district_line is not None:
            header_lines.append(district_line)
        header_lines.extend([
            f"Лист: {list_page}",
            # The census line names both numberings because a ревизская
            # сказка's «семья» and «двор» are not always the same count. An
            # ИР has only the one column, «Домоседовъ или дворовъ».
            f"{records.household_number_label}: {h_index}",
        ])
        hh_comment = getattr(household, "comment", None)
        if hh_comment:
            header_lines.append(f"Примечание: {hh_comment}")
        description_body = "\n".join(
            " " * 20 + line for line in header_lines
        )
        text_body_parts = [description_body, "", ""]  # two blank lines before table
        text_body_parts.append(" " * 20 + "---")
        # A source with a single age column says so: «Возраст в пред./текущей
        # ревизии» is a lie on an исповедная роспись, which has no previous
        # revision to compare against.
        table_header = (
            "№. Роль   Имя                    Возраст"
            if records.single_age_column else
            "№. Роль   Имя                    Возраст в пред./текущей ревизии"
        )
        text_body_parts.append(" " * 20 + table_header)
        text_body_parts.append("")

        for m in household.members:
            # Skip hidden members (manually-added reconstructions and
            # placeholder ancestors). They are not in the actual
            # revision document's table — legacy never enumerated them.
            if m.is_hidden():
                continue
            text_body_parts.extend(self._render_census_member_lines(
                m, household=household,
                single_age_column=records.single_age_column))

        # The per-member renderer appends a blank-line separator after
        # each member; for the last member that becomes a trailing
        # empty line before EOT, which legacy did not emit. Strip it.
        while text_body_parts and text_body_parts[-1] == "":
            text_body_parts.pop()

        text_body = "\n".join(text_body_parts)

        # Build profiles list: post-consolidation res_names for every member
        # that has an emitted profile.
        profiles_res_names: list[str] = []
        seen: set[str] = set()
        for m in household.members:
            if m.person is None:
                continue
            # Hidden members are skipped from the document text body
            # (above), but they still belong in the doc's
            # `profiles = [...]` list so the document attaches to
            # their consolidated timelines. The "Отсутствует в РС …"
            # comment is purely documentation; it doesn't drop the
            # reference.
            # Reconstruct what `_profile_from_person` would produce — simpler
            # to re-query the output: we already emitted the profile; scan
            # for its res_name by the (year, household_idx, member_num) tuple.
            # Cheaper: stash the emitted name. But the member's res_name was
            # derived deterministically; re-derive here.
            page_month = getattr(household, "record_month", None) or 0
            page_day = getattr(household, "record_day", None) or 0
            suffix_in_res_names = getattr(records, "suffix_in_res_names", False)
            res_suffix = archive_suffix if suffix_in_res_names else ""
            first_name = m.person.get_canonical_name() or m.person.name_modern or ""
            middle_name = m.person.patr_modern or ""
            # MUST mirror _profile_from_person's res_name_last fallback: this
            # builds the document's REFERENCES to those profiles, so if only one
            # side includes the derived maiden surname the document points at a
            # res_name that was never declared ("Reference to undeclared
            # resource") and the whole plan fails.
            last_name = (m.person.last_name_modern
                         or m.person.birth_last_name_modern or "")
            # MUST mirror `add_census_records`'s `doc` for the same reason as
            # the surname fallback above — a confession list keys its member
            # profiles on `ir`, and a document referencing `rs` names would
            # point at resources that were never declared.
            document_name = records.file_prefix
            raw_res_name = generate_res_name_2(
                year=year, month=page_month, day=page_day,
                first_name=first_name, middle_name=middle_name, last_name=last_name,
                document_name=document_name, role="family_member",
                record_number=f"{h_index}_{m.number}",
                suffix=res_suffix,
            )
            final = self.consolidation.move_to_new_name(raw_res_name)
            if final not in seen:
                seen.add(final)
                profiles_res_names.append(final)

        # Assemble the resource block manually (20-space indent for heredoc
        # content doesn't round-trip through `_document_resource`'s
        # 8-space helper).
        parish_location_block = _location(records.village)
        out = [
            f'resource "geni_document" "{doc_res_name}" {{',
            f'  title       = "{title}"',
            '  description = <<-EOT',
            description_body,
            '                EOT',
            '  text        = <<-EOT',
            text_body,
            '                EOT',
            '  date = {',
            f'    year = {year}',
            '  }',
            '  labels = [',
            '    "Census",',
            '  ]',
        ]
        if parish_location_block:
            out.append('  location = {')
            for ln in parish_location_block.split("\n"):
                ln = ln.strip()
                if ln:
                    out.append(f'    {ln}')
            out.append('  }')
        out.append('  profiles = [')
        for p in profiles_res_names:
            out.append(f'    geni_profile.{p}.id,')
        out.append('  ]')
        projects = self._projects_for_location(records.village)
        if projects:
            out.append(f'  projects = [{", ".join(projects)}]')
        out.append('}\n')
        self._outputs[filename] += "\n".join(out) + "\n"

    @staticmethod
    def _build_godparent_about(gp_person, village, year, names_in_mk, comment) -> str:
        """Build the `about` block for a birth-record godparent profile.
        Mirrors the legacy `god_parent_1_profile.about` format — header
        line, optional status line, and the shared "Комментарий из МК"
        block with `Имена в МК:` and any extra DSL comment.
        """
        lines = [
            f"<strong>МК {village} {year}:</strong> восприемник на крещении"
        ]
        if gp_person.status:
            lines.append(f"Титул/звание: {gp_person.status}")
        if names_in_mk or comment:
            lines.append("Комментарий из МК:")
            if names_in_mk:
                lines.append(f">Имена в МК: {names_in_mk}")
            if comment:
                lines.append(f">{comment}")
        return ("\n" + " " * 8).join(lines)

    @classmethod
    def _build_census_member_about(cls, *, village, year, h_index,
                                   status, comment, origin=None,
                                   member=None, occupation=None,
                                   marital_status=None, household=None,
                                   label="РС", label_genitive="РС",
                                   unit_label="семья") -> str:
        """Build the `about` block for a census member profile.

        Shape (matching legacy):
            <strong>{label} {village} {year}:</strong> семья {h_index}
            Возраст: {age}
            Титул/звание: {status}
            Род занятий: {occupation}
            Семейное положение: {marital_status}
            Роль в семье: № {n}, {role} {relative in genitive} (№ {ref})
            Комментарий из {label_genitive} {year} года:
            >{extracted comment lines}

        `label` / `label_genitive` default to "РС" (Ревизская сказка) but
        are overridden per source — e.g. the 1897 First General Census
        passes "1-я всеобщая перепись" / "1-й всеобщей переписи".

        Returns `""` when none of status / occupation / marital_status /
        role / emit-worthy comment line is present — upstream
        `_profile_from_person` skips the `about = { ... }` block when the
        string is empty.
        """
        gt_lines = cls._extract_census_about_gt_lines(
            comment, origin=origin, member=member,
        )
        # Auto-generated "ФИО/ИО/Имя в документе" line from the person's
        # original-spelling fields (mirrors MK "Имена в МК"). Prepended so it
        # is the first `>` line. Skipped for hidden members (not actually
        # recorded in the document).
        if (member is not None and not member.is_hidden()
                and member.person is not None):
            doc_line = _name_in_document(member.person)
            if doc_line:
                gt_lines = [doc_line, *gt_lines]
        # Document-recorded age. Skipped for hidden members (not actually
        # recorded in the document), like the ФИО line above.
        age = (member.age
               if member is not None and not member.is_hidden() else None)
        # Surface the document's own «Причина, основание убытия» column for ANY
        # recorded departure — "умер (1841)", "выдана замуж", "отдан в рекруты
        # (1789)". The census document renderer has always done this; the
        # profile's about used to be restricted to death WITH a year, which left
        # every other departure silent. Notably none of the 66 «выдана замуж»
        # members in the corpus carries a departure_year at all, so the year has
        # to be optional or the line could never appear for a bride.
        #
        # The age suppression stays narrower than the line, and deliberately: a
        # member who died BEFORE this revision has no current-revision age (the
        # census "56/-" convention repeats the PREVIOUS age in the slot, the
        # current column being a dash), so "Возраст: 56" would imply they were
        # alive at the revision. A living departure — married out, sent for a
        # soldier — was still aged by the scribe where the column was filled.
        departure_line = None
        if member is not None and not member.is_hidden():
            dep_reason = _resolve_departure_reason(member)
            dep_year = _resolve_departure_year(member)
            if dep_reason:
                departure_line = (
                    f"Причина, основание убытия: {dep_reason} ({dep_year})"
                    if dep_year is not None
                    else f"Причина, основание убытия: {dep_reason}"
                )
                if dep_reason == "умер" and dep_year is not None:
                    try:
                        if int(dep_year) < int(year):
                            age = None
                    except (TypeError, ValueError):
                        pass
        has_age = age not in (None, "", "?", "-")
        role_line = cls._census_role_line(member, household)
        if (not status and not occupation and not marital_status
                and not gt_lines and not has_age and not departure_line
                and not role_line):
            return ""
        lines = [f"<strong>{label} {village} {year}:</strong> {unit_label} {h_index}"]
        rendered_age = format_age(age) if has_age else None
        if rendered_age:
            # The previous revision's age, when the book recorded one. Both
            # halves of the census "prev/cur" age pair then reach the reader:
            # the gap between them is what dates a person, and it is the first
            # thing that exposes a bad merge of two same-named people.
            prev_rendered = (
                format_age(prev_raw)
                if (prev_raw := resolve_previous_age_raw(member)) is not None
                else None
            ) if member is not None and not member.is_hidden() else None
            # A DSL that compressed prev and cur into the single `age` field
            # (the source's "56/-" shape) would otherwise render the same value
            # twice; the document table suppresses the repeat the same way.
            if prev_rendered and prev_rendered != rendered_age:
                lines.append(
                    f"Возраст: {rendered_age} "
                    f"({prev_rendered}, в предыдущей ревизии)")
            else:
                lines.append(f"Возраст: {rendered_age}")
        elif departure_line:
            lines.append(departure_line)
        if status:
            lines.append(f"Титул/звание: {status}")
        if occupation:
            lines.append(f"Род занятий: {occupation}")
        if marital_status:
            lines.append(f"Семейное положение: {marital_status}")
        if role_line:
            lines.append(role_line)
        if gt_lines:
            lines.append(f"Комментарий из {label_genitive} {year} года:")
            for gl in gt_lines:
                lines.append(f">{gl}")
        return ("\n" + " " * 8).join(lines)

    @staticmethod
    def _census_role_line(member, household=None) -> str | None:
        """The «Роль в семье» about line: where this person stood in the
        household, named by the relative their role is measured against.

            Роль в семье: глава
            Роль в семье: жена Василия Семёновича

        Household member numbers are deliberately NOT rendered. They index the
        attached document's own table and mean nothing on a profile read on its
        own — and a Geni profile is usually read on its own, or reached from a
        relative, not from the document. The name identifies the relative
        unambiguously within a household; the number only located them.

        The relationship still resolves through `resolve_display_role`, shared
        with the table's `4. жена (3): …` rendering, so the two cannot disagree
        about who is whose wife.

        A `hidden=True` member — a reconstruction the book does not list — gets
        the same line. Their role is the one thing their about otherwise never
        says: without it the section reads only «Отсутствует в РС …; персона
        добавлена вручную», which explains that they are not in the book but
        not why they hang off this household. That is why DSL authors kept
        hand-writing «отец Зота» into the comment.

        Returns None — no line at all — when the role slot is empty: the
        pre-1745 bare name lists, where the source recorded no relationship.
        A role whose referenced member cannot be named falls back to the bare
        role word.
        """
        if member is None:
            return None
        role_word, ref = resolve_display_role(member, household)
        if not role_word:
            return None
        relative = None
        if ref is not None and household is not None:
            relative = next(
                (x for x in household.members if x.number == ref), None,
            )
        rel_name = genitive_person_name(relative.person) if relative else ""
        return f"Роль в семье: {role_word} {rel_name}".rstrip()

    @classmethod
    def _extract_census_about_gt_lines(cls, comment: str | None,
                                       origin: str | None = None,
                                       member=None) -> list[str]:
        """Split a DSL census-member `comment=` string into the `>`-
        prefixed lines that legacy emits in the census about block.

        Rules (derived from a legacy corpus sweep over rs_*.tf):
        - Drop `прошлая РС: N лет` segments — they appear in the text
          body but not the about block.
        - Drop `роль в оригинале: <phrase>` — consumed as the role
          word in the text body, not surfaced in the about block.
        - `прибыл: {reason} {YYYY}` → `{YYYY}: {reason}` (with any
          trailing ` YYYY из ORIGIN` / ` YYYY в DEST` tail stripped).
        - `убыл: {reason} {YYYY}` → `{YYYY}: {reason}` (same tail
          stripping), EXCEPT `убыл: умер {YYYY}` which is consumed
          by the death event — no `>YYYY: умер` about line.
        - `(Ф)ИО в документе: X` → kept as-is.
        - Any remaining non-empty segment is kept as-is (e.g. the
          manually-added-person marker text).

        When `member` carries typed `arrival_*` / `departure_*`
        kwargs, those win over the comment-regex fallback — mirrors
        the text-body rendering precedence.
        """
        if not comment and member is None:
            return []
        import re
        remaining = comment or ""
        # Hidden members carry a free-text comment documenting WHY the
        # person was added manually (e.g. "Отсутствует в РС 1834;
        # персона добавлена вручную..."). The legacy template inserts
        # `;` within that single logical message, so keep the whole
        # comment as one atomic segment instead of semicolon-splitting.
        if member is not None and member.is_hidden() and remaining.strip():
            return [remaining.strip()]

        # Parse прибыл:/убыл: markers out of `remaining` and collect
        # their (reason, year) tuples from the comment.
        comment_arrival: tuple[str, str | None] | None = None
        comment_departure: tuple[str, str | None] | None = None
        for marker, slot in (
            ("прибыл:", "arrival"),
            ("убыл:", "departure"),
        ):
            while marker in remaining:
                m = re.search(rf"{marker}\s*([^;]+?)(?:\s*;|$)", remaining)
                if not m:
                    break
                segment = m.group(1).strip()
                remaining = remaining[:m.start()] + remaining[m.end():]
                if segment and slot == "arrival" and comment_arrival is None:
                    reason, yr = cls._split_reason_trailing_year(segment, origin)
                    comment_arrival = (reason.strip(), yr)
                elif segment and slot == "departure" and comment_departure is None:
                    reason, yr = cls._split_reason_trailing_year(segment, origin)
                    # If the trailing tail is `в DEST` AND that DEST
                    # also surfaces as the member's destination (via
                    # typed field or comment tail), drop the duplicate
                    # tail from the gt line. Legacy keeps "в DEST"
                    # inside the reason when the destination wasn't
                    # split out (e.g. mid-reason with a trailing year).
                    member_dest = (
                        _resolve_destination(member)
                        if member is not None else None
                    )
                    if member_dest:
                        m_v = re.search(
                            r"\s+в\s+([А-ЯЁ][А-ЯЁа-яё\- ]+)\s*$",
                            reason,
                        )
                        if m_v and m_v.group(1).strip(" .,;") == member_dest:
                            reason = reason[:m_v.start()].rstrip()
                    comment_departure = (reason.strip(), yr)

        # Strip прошлая РС: N лет noise.
        remaining = re.sub(r"прошлая РС:\s*[^;]+;?\s*", "", remaining)
        # Strip `роль в оригинале: ...` — consumed as role-word above.
        remaining = re.sub(
            r"роль в оригинале:\s*[^;]+;?\s*", "", remaining,
        )

        # Resolve (reason, year) per slot: typed fields on member win.
        a_reason = (
            getattr(member, "arrival_reason", None)
            if member is not None else None
        )
        a_year = (
            getattr(member, "arrival_year", None)
            if member is not None else None
        )
        if a_reason is None and comment_arrival is not None:
            a_reason = comment_arrival[0] or None
        if a_year is None and comment_arrival is not None:
            a_year = (
                int(comment_arrival[1]) if comment_arrival[1] else None
            )
        d_reason = (
            getattr(member, "departure_reason", None)
            if member is not None else None
        )
        d_year = (
            getattr(member, "departure_year", None)
            if member is not None else None
        )
        if d_reason is None and comment_departure is not None:
            d_reason = comment_departure[0] or None
        if d_year is None and comment_departure is not None:
            d_year = (
                int(comment_departure[1]) if comment_departure[1] else None
            )

        # Pre-collect the remaining segments so we can detect a
        # descriptor that elaborates on `взята в жены` / `выдана замуж`
        # — legacy substitutes the descriptor for the bare reason in
        # that case.
        remaining_segments = [
            seg.strip(" ;\t") for seg in remaining.split(";")
            if seg.strip(" ;\t")
        ]
        # Descriptor prefixes per reason. The "старинная" / "взятая"
        # forms are the marriage-arrival descriptors; "выдана" is the
        # marriage-departure descriptor.
        descriptor_prefixes = {
            "взята в жены": ("взят", "старинная"),
            "выдана замуж": ("выдан",),
        }
        def _has_descriptor(reason: str | None) -> bool:
            prefixes = descriptor_prefixes.get(reason or "")
            if not prefixes:
                return False
            return any(s.startswith(p) for s in remaining_segments
                       for p in prefixes)

        out: list[str] = []
        # Emit arrival/departure reason lines first. With a year present
        # the legacy form is `>YYYY: reason`; year-less reasons (common
        # in early-RS sources where the arrival year is implicit) emit
        # as bare `>reason` so the about block doesn't silently drop the
        # only signal the DSL recorded. Suppress redundant arrival
        # reasons whose text is just "из <origin>" (origin is captured
        # separately as a location reference). Also suppress
        # `взята в жены` / `выдана замуж` when a descriptor segment
        # already conveys the same information (legacy parity).
        a_reason_redundant = (
            a_reason and origin and a_reason.strip() == f"из {origin}"
        ) or _has_descriptor(a_reason)
        # Suppress the year prefix when it's already embedded in `origin`
        # (mirror of the text-body suppression for anomalous source CSV
        # cells like "<place> <year>").
        a_year_redundant_in_origin = (
            a_year is not None
            and origin
            and str(a_year) in str(origin)
        )
        if (a_reason and a_year and not _has_descriptor(a_reason)
                and not a_year_redundant_in_origin):
            out.append(f"{a_year}: {a_reason}")
        elif a_reason and not a_reason_redundant:
            out.append(a_reason)
        if d_reason and d_reason != "умер" and not _has_descriptor(d_reason):
            if d_year:
                out.append(f"{d_year}: {d_reason}")
            else:
                out.append(d_reason)

        # Remaining semicolon-separated segments (free-text Пометки). Any
        # hand-written "… в документе:" segment is dropped here — the
        # name-as-written line is now auto-generated by `_name_in_document`
        # and prepended in `_build_census_member_about`.
        out.extend(
            seg for seg in remaining_segments
            if not re.match(r"(?:Ф?)?И(?:мя|О) в документе:", seg)
        )
        return out

    def _emit_head_of_family_stub_if_needed(
        self, *, filename, records, household, h_index, archive_suffix,
    ):
        """Emit a `unknown_rs_{h_index}_not_recorded_head_of_family` anchor
        when the household implicitly references an out-of-household parent
        (triggered by any BROTHER/SISTER member with ref=1 where member #1
        itself has no ref).

        Mirrors the earlier generator's virtual-father injection.
        """
        from verso.ru.dsl.records.census import CensusRole

        members = household.members
        if not members:
            return None
        # Member 1 must exist and carry no explicit ref (a head or
        # otherwise-unlinked first row).
        first = next((m for m in members if m.number == 1), None)
        if first is None or first.ref_member is not None:
            return None
        # If the household has a FATHER/MOTHER member of HEAD, the
        # head's parent generation is explicitly recorded — no virtual
        # head-of-family stub needed (the BROTHERS' father IS the
        # recorded FATHER member). Only consider MOTHER/FATHER members
        # whose `effective_ref` points at HEAD (member 1); a MOTHER
        # member with `ref_member=N` (N≠1) describes someone else's
        # mother (e.g. m2's mother where she is the wife of the head's
        # brother, not the head's mother).
        ascending_roles = (CensusRole.FATHER, CensusRole.MOTHER)
        def _is_head_parent(m):
            if m.role not in ascending_roles:
                return False
            eff_ref = m.ref_member if m.ref_member is not None else 1
            return eff_ref == 1
        if any(_is_head_parent(m) for m in members):
            return None
        # Look for a BROTHER or SISTER pointing at #1 (explicit or default)
        # AND lacking an explicit upward-link via `parent_member`. When
        # parent_member is set, the BROTHER's father is already
        # captured as a hidden ancestor in this household — no virtual
        # head-of-family stub needed.
        trigger = False
        for m in members:
            if m.role not in (CensusRole.BROTHER, CensusRole.SISTER):
                continue
            if getattr(m, "parent_member", None) is not None:
                continue
            # Hidden BROTHER/SISTER use `ref_member` to encode their
            # SPOUSE (not parent — that goes via parent_member). They're
            # still HEAD's sibling for the head_of_family stub trigger,
            # which represents the (unrecorded) shared ancestor.
            if m.is_hidden():
                trigger = True
                break
            effective_ref = m.ref_member if m.ref_member is not None else 1
            if effective_ref == 1:
                trigger = True
                break
        if not trigger:
            return None

        year = records.year
        page_month = getattr(household, "record_month", None) or 0
        page_day = getattr(household, "record_day", None) or 0
        # Head-of-family stub ALWAYS takes the archive_suffix when one is
        # defined for the file (independent of `suffix_in_res_names`,
        # which only gates member profile res_names). Legacy split these
        # two behaviors across `append_suffix_to_resource_name` and
        # `append_suffix_to_resource_name_2` flags.
        res_suffix = archive_suffix or ""
        stub_res_name = generate_res_name_2(
            year=year, month=page_month, day=page_day,
            first_name="unknown", middle_name="", last_name="",
            document_name="rs", role="head_of_family",
            record_number=f"{h_index}_not_recorded",
            suffix=res_suffix,
        )
        # The stub represents an implied ancestor the document never
        # enumerated — we don't know where they lived. Legacy emitted no
        # current_residence on the stub; mirror that.
        # When every visible member shares the same `origin=` (a
        # transferred-in family, e.g. all "Фамусово"), the unrecorded
        # ancestor was born there too — legacy emitted that as
        # `birth.location` on the stub.
        origins = {
            m.origin for m in members
            if not m.is_hidden() and m.origin
        }
        stub_birth = None
        if len(origins) == 1:
            origin_name = next(iter(origins))
            origin_loc = _location(origin_name)
            if origin_loc is not None:
                stub_birth = GeniEvent(date=None, location=origin_loc)
        stub = GeniProfile(
            res_name=stub_res_name,
            gender="male",
            alive=False,
            public=True,
            current_residence=None,
            birth=stub_birth,
            projects=self._projects_for_location(records.village),
            about=(
                f"<strong>РС {records.village} {year}:</strong> "
                f"семья {h_index}, глава семьи (явно не указан)"
            ),
        )
        self._emit_profile(filename, stub)
        return stub_res_name

    def _render_census_member_lines(self, m, household=None, *,
                                    single_age_column: bool = False) -> list[str]:
        """Render one `---\nN. role (ref): Name: prev/cur\n...` block
        for a single CensusHousehold member. Returns a list of lines
        already indented with 20 spaces.

        `single_age_column` comes from the records object: a source with one
        age column (an исповедная роспись) renders `69`, a revision tale
        `-/69`."""
        import re as _re
        ind = " " * 20
        # Role word + the member number it refers to. Shared with the profile
        # about-block's «Роль в семье» line (see `resolve_display_role`) so the
        # two renderings of the same relationship cannot drift apart.
        role_word, effective_ref = resolve_display_role(m, household)
        ref_part = f" ({effective_ref})" if effective_ref is not None else ""
        name_parts = []
        if m.person:
            first = m.person.get_canonical_name() or m.person.name_modern or ""
            mid = m.person.patr_modern or ""
            last = m.person.last_name_modern or ""
            name_parts = [x for x in (first, mid, last) if x]
        name_str = " ".join(name_parts) if name_parts else ""
        # Legacy renders empty/unknown age as "-". DSL uses "?" (or None)
        # for unknown; coerce both to "-" to match. When the DSL carries
        # an explicit numeric age, render it as-is — even for departed
        # members, because legacy preserved whatever was in the source
        # CSV's `Лет (текущая РС)` column (often non-empty for daughters
        # married out, sons sent to recruits, etc.).
        cur_age = m.age if m.age not in (None, "?", "") else "-"
        comment = m.comment or ""
        has_arrival = (
            "прибыл:" in comment
            or getattr(m, "arrival_reason", None) is not None
            or getattr(m, "arrival_year", None) is not None
        )
        # Prev age: prefer typed `previous_age` kwarg, fall back to
        # `прошлая РС: X лет` comment marker. The comment fallback may
        # carry non-integer strings (e.g. "60 лет" written verbatim),
        # so render that legacy shape when typed is unavailable.
        prev_age = "-"
        typed_prev = getattr(m, "previous_age", None)
        if typed_prev is not None:
            prev_age = str(typed_prev)
        elif "прошлая РС:" in comment:
            m2 = _re.search(r"прошлая РС:\s*([^;]+?)(?:\s*лет)?\s*(?:;|$)", comment)
            if m2:
                prev_age = m2.group(1).strip() or "-"
        # DSL authors sometimes store the prev-revision age into `m.age`
        # when the source CSV's "Лет (текущая РС)" column was empty —
        # compressing prev/cur into a single field. Detect this shape
        # (same value in both columns) and render as `prev/-` to mirror
        # legacy's empty-current rendering. Suppress the compression
        # only when an `прибыл:` arrival marker is present, since an
        # arrival means the DSL really intends both prev and cur to
        # carry the same age (a person joined the household at the
        # same age recorded later).
        if (
            prev_age not in ("", "-")
            and str(cur_age) == str(prev_age)
            and not has_arrival
        ):
            cur_age = "-"
        # A source with one age column renders one age. Writing `-/69` on an
        # исповедная роспись would claim the scribe left a previous-revision
        # cell empty, when the form has no such cell at all.
        if single_age_column:
            age_part = str(cur_age)
        else:
            age_part = f"{prev_age}/{cur_age}"
        lines = [
            f"{ind}---",
            f"{ind}{m.number}. {role_word}{ref_part}: {name_str}: {age_part}",
        ]
        if m.origin:
            lines.append(f"{ind}Населенный пункт откуда поступили/прибыли: {m.origin}")
        # Resolve the outgoing destination (typed `destination` wins
        # over the `убыл: ... в X` trailing-tail comment parse) and
        # emit its own text-body line — matches legacy's separate
        # "Населенный пункт куда отправлены/убыли:" column.
        destination_name = _resolve_destination(m)
        if destination_name:
            lines.append(
                f"{ind}Населенный пункт куда отправлены/убыли: "
                f"{destination_name}"
            )
        # Break down comment into the optional "прибыл:" / "убыл:" segments
        # and leave the rest as "Комментарий:". When the DSL populates
        # typed arrival/departure fields on the CensusMember, render from
        # those in preference to the comment-regex parse, but still strip
        # any legacy markers from `remaining_comment` so the Пометки tail
        # remains identical.
        remaining_comment = comment
        for marker, label, structured_reason, structured_year, is_departure in (
            ("прибыл:",
             "Причина, основание поступления/прибытия:",
             _resolve_arrival_reason(m),
             _resolve_arrival_year(m),
             False),
            ("убыл:",
             "Причина, основание убытия:",
             # For rendering we only want the *structured* reason — the
             # legacy comment-regex path handles its own reason text
             # through `_split_reason_trailing_year` below.
             getattr(m, "departure_reason", None),
             getattr(m, "departure_year", None),
             True),
        ):
            use_structured = (
                structured_reason is not None or structured_year is not None
            )
            if use_structured:
                if structured_reason:
                    # Suppress redundant arrival reason: when the
                    # text is "из <X>" and the member's origin is X,
                    # the origin is already shown on its own line.
                    redundant = (
                        not is_departure
                        and m.origin
                        and structured_reason.strip() == f"из {m.origin}"
                    )
                    # Suppress the `(YYYY)` parenthetical when the
                    # year is already embedded literally in `origin`
                    # (e.g. anomalous source CSV cell "<place> <year>"
                    # in the location column with the year column
                    # empty). The location line above already shows
                    # the year; repeating it here would diverge from
                    # legacy.
                    year_redundant_in_origin = (
                        not is_departure
                        and structured_year is not None
                        and m.origin
                        and str(structured_year) in str(m.origin)
                    )
                    effective_year = (
                        None if year_redundant_in_origin else structured_year
                    )
                    if not redundant:
                        suffix = f" ({effective_year})" if effective_year else ""
                        lines.append(f"{ind}{label} {structured_reason}{suffix}")
                if marker in remaining_comment:
                    mm = _re.search(
                        rf"{marker}\s*([^;]+?)(?:\s*;|$)", remaining_comment
                    )
                    if mm:
                        remaining_comment = (
                            remaining_comment[:mm.start()]
                            + remaining_comment[mm.end():]
                        )
            elif marker in remaining_comment:
                mm = _re.search(
                    rf"{marker}\s*([^;]+?)(?:\s*;|$)", remaining_comment
                )
                if mm:
                    segment = mm.group(1).strip()
                    if segment:
                        reason, year = self._split_reason_trailing_year(segment, m.origin)
                        # When a destination was resolved and the reason
                        # ends with " в {DEST}", drop the tail — legacy
                        # rendered the destination on its own line.
                        if is_departure and destination_name:
                            tail_m = _re.search(
                                r"\s+в\s+([А-ЯЁ][А-ЯЁа-яё\- ]+)$", reason,
                            )
                            if tail_m and tail_m.group(1).strip(
                                    " .,;") == destination_name:
                                reason = reason[:tail_m.start()].rstrip()
                        suffix = f" ({year})" if year else ""
                        lines.append(f"{ind}{label} {reason}{suffix}")
                    remaining_comment = (
                        remaining_comment[:mm.start()] + remaining_comment[mm.end():]
                    )
        # Strip trailing/leading semicolons and whitespace from remaining.
        remaining_comment = remaining_comment.strip(" ;\t")
        if "прошлая РС:" in remaining_comment:
            remaining_comment = _re.sub(
                r"прошлая РС:\s*[^;]+;?\s*", "", remaining_comment
            ).strip(" ;\t")
        # The "роль в оригинале:" marker is consumed by the role-word
        # substitution above; remove it from the remaining free-text so
        # it doesn't surface as Пометки.
        if "роль в оригинале:" in remaining_comment:
            remaining_comment = _re.sub(
                r"роль в оригинале:\s*[^;]+;?\s*", "", remaining_comment
            ).strip(" ;\t")
        # "ФИО/ИО/Имя в документе" is now AUTO-GENERATED from the person's
        # original-spelling fields (mirrors MK "Имена в МК"), rendered on the
        # `Комментарий:` line. Skipped for hidden members (not in the document).
        if not m.is_hidden() and m.person is not None:
            io_part = _name_in_document(m.person)
            if io_part:
                lines.append(f"{ind}Комментарий: {io_part}")
        # Any residual hand-written "… в документе:" segment is dropped (it is
        # now computed) so it never double-renders; the rest is free-text Пометки.
        remaining_comment = _re.sub(
            r"(?:Ф?)?И(?:мя|О) в документе:\s*[^;]+;?\s*", "", remaining_comment
        ).strip(" ;\t")
        if remaining_comment:
            lines.append(f"{ind}Пометки: {remaining_comment}")
        lines.append("")  # blank line separator
        return lines

    @staticmethod
    def _split_reason_trailing_year(segment: str, origin: str | None):
        """Split `"reason[ YYYY[ из ORIGIN]]"` into (reason, year|None).

        Legacy RS CSV stored year-of-arrival/departure in its own column,
        and the place-of-origin in another. When DSL authors inlined all
        three into the free-text comment, they appended them as
        ` YYYY из ORIGIN` (arrival) or ` YYYY` (departure).

        Strip that trailing metadata out so the reason text matches
        legacy, and return the year separately for the `(YYYY)` suffix.
        """
        import re as _re
        # " YYYY из <rest>" — absorb everything after "из" as the
        # origin-duplicate (legacy templates drop it entirely when the
        # origin column is already set; we drop unconditionally because
        # otherwise the text would duplicate a separate "Населенный
        # пункт откуда..." line).
        m = _re.search(r"\s+(\d{4})\s+из\s+[^;]+$", segment)
        if m:
            return segment[:m.start()].rstrip(), m.group(1)
        # Plain trailing year.
        m = _re.search(r"\s+(\d{4})\s*$", segment)
        if m:
            return segment[:m.start()].rstrip(), m.group(1)
        # Trailing " из <rest>" without a year — legacy still strips
        # when origin is already populated on the member (avoids the
        # doubled location line).
        if origin:
            m = _re.search(r"\s+из\s+[^;]+$", segment)
            if m:
                return segment[:m.start()].rstrip(), None
        return segment, None

    def get_output(self, filename: str) -> str:
        return self._outputs[filename]

    def iter_outputs(self):
        """Yield (filename, content) for every non-empty output file."""
        for name, content in self._outputs.items():
            if content:
                yield name, content

    def canonical_profiles(self) -> dict[str, GeniProfile]:
        """All translated profile objects by res_name: directly-emitted
        per-record profiles plus the consolidated canonicals. On a key
        collision the consolidated canonical wins (it is the merged,
        authoritative version). Call after `finalize()` so consolidated
        enrichment/overrides are applied. Read-only view for downstream
        projections (e.g. the familio translator)."""
        return {**self._profile_registry, **self._consolidated_profiles}

    def canonical_unions(self) -> dict[str, GeniUnion]:
        """All translated union objects by res_name: directly-emitted unions
        plus consolidated canonicals (consolidated wins on collision). Call
        after `finalize()`."""
        return {**self._union_registry, **self._consolidated_unions}

    def resolve_canonical(self, res_name: str) -> str:
        """Map a per-record profile res_name to its consolidated canonical
        res_name when it is in the consolidation move list, else return it
        unchanged. Lets a projection normalise union partner/child references
        (which may still be per-record names) onto the canonical names a kin
        registry keys on."""
        if self.consolidation.in_profile_move_list(res_name):
            return self.consolidation.move_to_new_name(res_name)
        return res_name
