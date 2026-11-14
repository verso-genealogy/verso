"""Profile-consolidation dataclass (move/merge bookkeeping)."""
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any
if TYPE_CHECKING:
    pass
from verso.ru.targets.geni.translator.res_names import _strip_last_name_token




@dataclass
class Consolidation:
    """Optional per-village consolidation config.

    Matches the subset of the earlier generator's names config currently exercised by the
    translator. A village without a config file gets the default empty instance, which
    makes `in_profile_move_list` always return False and causes profiles to flow to
    per-year files only.

    `union_move_list_v2` maps a per-record union's res_name to the target
    consolidated-union res_name (populated from `unions_to_consolidate`'s
    `union_names` lists in legacy).

    `unions_to_consolidate` maps the target consolidated-union res_name to
    hints (`undocumented_partner`, `undocumented_children`, `exclude_children`,
    `override`) applied after merging.
    """
    profile_move_list: dict[str, Any] = field(default_factory=dict)
    union_move_list_v2: dict[str, Any] = field(default_factory=dict)
    unions_to_consolidate: dict[str, Any] = field(default_factory=dict)
    # Per-consolidation-target "preference" hints from the legacy
    # `profiles_to_consolidate[target]['preference']`. Keyed by target
    # res_name (e.g. 'domna_konstantinovna'); value is a dict with
    # optional 'first_name' / 'nicknames' / 'last_name' etc. Used by
    # `_merge_consolidated` to pin the canonical value when per-record
    # profiles disagree.
    profile_preferences: dict[str, Any] = field(default_factory=dict)
    # Per-consolidation-target "ignore" lists — legacy's
    # `profiles_to_consolidate[target]['ignore']`. List of dicts with
    # attr→value pairs (first_name / middle_name / last_name /
    # birth_last_name); when an incoming per-record profile attribute
    # matches an ignored value, the merge silently drops the variant
    # (no overwrite, no nicknames append).
    profile_ignores: dict[str, Any] = field(default_factory=dict)
    # Per-consolidation-target "override" hints — legacy's
    # `profiles_to_consolidate[target]['override']`. Unlike preference,
    # override UNCONDITIONALLY replaces the existing field value. Applied
    # during finalize after all merges. Values may include first_name,
    # middle_name, last_name, birth_last_name, nicknames, birth, death,
    # current_residence.
    profile_overrides: dict[str, Any] = field(default_factory=dict)

    # additional_info is a list of supplementary GeniProfile objects per
    # consolidation target. Each one carries fields legacy folds into
    # the consolidated profile (last_name, birth_last_name, precise
    # birth/death events) using the same fill-in-if-missing semantics as
    # per-record merges — overrides still win. Mirrors legacy
    # `profiles_to_consolidate[*]['additional_info']`.
    profile_additional_info: dict[str, Any] = field(default_factory=dict)

    # Per-target terraform lifecycle ignore_changes attribute lists —
    # `profiles_to_consolidate[*]['lifecycle_ignore_changes']`. The escape
    # hatch for co-author location-derived `projects` drift: the ForceNew
    # replace can't delete such profiles ("Error deleting profile") and an
    # additional_info projects pin can't link them ("Error linking profile
    # to project" / access denied), so the only stable state is to ignore
    # the attribute's diffs entirely.
    profile_lifecycle_ignores: dict[str, Any] = field(default_factory=dict)

    # Known canonical-name substitutions applied by the translator (via
    # names.csv). Legacy `profile_move_list` keys were built with the older
    # spelling; translator emits the canonical spelling. Expand move_list
    # keys so lookups succeed for either spelling.
    _RES_NAME_SPELLING_ALIASES: tuple[tuple[str, str], ...] = (
        ("illarion", "ilarion"),        # Илларион (двойная Л) → Иларион (одна Л)
        ("illarionovna", "ilarionovna"),
        ("illarionovich", "ilarionovich"),
        # Patronymic canonical → orthographic (the new generator emits
        # union res_names using the partner profile's orthographic name
        # fields, while `union_move_list_v2` keys in
        # generate_config_names.py use the canonical spelling).
        ("terentievich", "terentevich"),
        ("terentievna", "terentevna"),
        ("savelievich", "savel'evich"),
        ("savelievna", "savel'evna"),
        ("kondratievich", "kondrat'evich"),
        ("kondratievna", "kondrat'evna"),
        ("zinovievich", "zinov'evich"),
        ("zinovievna", "zinov'evna"),
        ("ermolaevich", "ermilovich"),  # Ермолаевич ↔ Ермилович (variant)
        ("ermolaevna", "ermilovna"),
        # Имя basename: legacy orthographic → canonical. Used by
        # ascending-role census unions whose res_name is built from the
        # parent's canonical patronymic (e.g. Несторовна) while legacy
        # union_move_list_v2 keys still spell it Нестеровна. Direction:
        # `old_tok` must match the existing v2 key, `new_tok` is the
        # form we want to alias to it.
        ("nesterovna", "nestorovna"),
        ("nesterovich", "nestorovich"),
    )

    def __post_init__(self):
        # Config keys that actually MATCHED a produced res_name during this
        # translation, reported as their ORIGINAL spelling (not the alias or
        # stripped form that did the matching). A config entry absent from
        # these sets named a record the corpus does not produce, so it folds
        # nothing — see `verso.ru.consolidation.stale_stubs` (CST001), which is the
        # only consumer. Recording is free and never influences behaviour.
        self.hit_profile_keys: set[str] = set()
        self.hit_union_keys: set[str] = set()
        # alias / stripped spelling -> the original config key it came from.
        self._profile_key_origin: dict[str, str] = {
            k: k for k in self.profile_move_list}
        self._union_key_origin: dict[str, str] = {
            k: k for k in self.union_move_list_v2}

        # Expand both move_lists with known canonical-name alias keys so
        # profile and union lookups succeed for either spelling.
        for old_tok, new_tok in self._RES_NAME_SPELLING_ALIASES:
            for key, target in list(self.profile_move_list.items()):
                if old_tok in key:
                    alias = key.replace(old_tok, new_tok)
                    if alias != key and alias not in self.profile_move_list:
                        self.profile_move_list[alias] = target
                        self._profile_key_origin[alias] = \
                            self._profile_key_origin.get(key, key)
            for key, target in list(self.union_move_list_v2.items()):
                if old_tok in key:
                    alias = key.replace(old_tok, new_tok)
                    if alias != key and alias not in self.union_move_list_v2:
                        self.union_move_list_v2[alias] = target
                        self._union_key_origin[alias] = \
                            self._union_key_origin.get(key, key)
        # Index of move_list keys with their last_name-like token stripped.
        # Value None marks an ambiguous stripped form (two different move_list
        # keys stripped to the same shape pointing to different targets).
        # Used as a fallback when the literal lookup misses.
        self._stripped_index: dict[str, str | None] = {}
        for key, target in self.profile_move_list.items():
            stripped = _strip_last_name_token(key)
            if stripped == key:
                continue
            if stripped in self._stripped_index:
                if self._stripped_index[stripped] != target:
                    self._stripped_index[stripped] = None  # ambiguous
            else:
                self._stripped_index[stripped] = target
                self._profile_key_origin.setdefault(
                    stripped, self._profile_key_origin.get(key, key))
        # Every canonical the config folds records into — whatever it is
        # called, a Заманиловка canonical keeping its first record's name
        # included.
        self._targets: frozenset[str] = frozenset(self.profile_move_list.values())

    def _match(self, res_name: str) -> tuple[str, str] | None:
        """(the move-list key `res_name` matched, its consolidated target), or
        None if no unambiguous match. Tries, in order:
          1. literal profile_move_list;
          2. stripped res_name against literal profile_move_list;
          3. literal res_name against the stripped_index.
        Ambiguous stripped entries (value None) are treated as a miss so
        the profile stays in its per-year file.
        """
        if res_name in self.profile_move_list:
            return res_name, self.profile_move_list[res_name]
        stripped = _strip_last_name_token(res_name)
        if stripped != res_name and stripped in self.profile_move_list:
            return stripped, self.profile_move_list[stripped]
        if res_name in self._stripped_index:
            target = self._stripped_index[res_name]
            if target is not None:
                return res_name, target
        return None

    def _resolve_target(self, res_name: str) -> str | None:
        """Return the consolidated target for `res_name`, or None — recording
        which config entry the match came from (`stale_stubs` reads that)."""
        found = self._match(res_name)
        if found is None:
            return None
        self._record_profile_hit(found[0])
        return found[1]

    def config_name_for(self, res_name: str) -> str | None:
        """The `profile_names` entry that folds `res_name`, as the config
        writes it, or None when nothing does. A rename of a name token
        (`illarion` → `ilarion`) leaves the config spelling behind the res_name
        the translator now mints; the fold still applies, and a reader holding
        the config's string needs this to find the record. Records no hit."""
        found = self._match(res_name)
        if found is None:
            return None
        return self._profile_key_origin.get(found[0], found[0])

    def _record_profile_hit(self, matched_key: str) -> None:
        self.hit_profile_keys.add(
            self._profile_key_origin.get(matched_key, matched_key))

    def union_redirect_target(self, res_name: str) -> str | None:
        """The `union_move_list_v2` target for a per-record union's res_name,
        or None. Records the hit so `stale_stubs` can tell a config entry that
        matched nothing from one that did — go through this rather than
        indexing `union_move_list_v2` directly."""
        if res_name not in self.union_move_list_v2:
            return None
        self.hit_union_keys.add(self._union_key_origin.get(res_name, res_name))
        return self.union_move_list_v2[res_name]

    def is_target(self, res_name: str) -> bool:
        """Whether `res_name` is a canonical the config folds records into."""
        return res_name in self._targets

    def in_profile_move_list(self, res_name: str) -> bool:
        return self._resolve_target(res_name) is not None

    def move_to_new_name(self, res_name: str) -> str:
        target = self._resolve_target(res_name)
        return target if target is not None else res_name
