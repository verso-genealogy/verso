"""A village's record sets fed to a `TerraformGenerator`: the DSL→domain translation.

Moved verbatim out of `verso.ru.cli.generate_tf` before 0.1.0. The generator's own entry point
(`verso.ru.cli.generate_tf.main`) writes the tree; everything else that asks what a
village translates to — the consolidation checks, the facts loader, the familio and
timeline generators, the review ratchet — calls `translate_village`. It sits beside
`make_consolidation`, which builds the translator's `Consolidation` from a village's
config (verbatim from `verso.core.pipeline.config`).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from verso.ru import corpus_data
from verso.core import ratchet
from verso.ru.dsl.records.births import BirthRecords
from verso.ru.dsl.records.census import CensusRecords
from verso.ru.dsl.records.deaths import DeathRecords
from verso.ru.dsl.records.external_sources import ExternalSourceRecords
from verso.ru.dsl.records.marriages import MarriageRecords
from verso.ru.dsl.records.name_lists import NameListRecords
from verso.core.pipeline.config import village_config
from verso.core.pipeline.load import discover_records
from verso.core.records.ids import RecordIds


def _ignore_event_date(profile, event_name: str):
    """The GeniDate of `profile`'s named event for an `ignore` entry, or None
    when that event isn't set on the ignore GeniProfile."""
    event = getattr(profile, event_name, None)
    return event.date if event is not None else None


def make_consolidation(gcn):
    """Build a `Consolidation` from a village's `generate_config_names` module.

    Extracts the per-target preference / override / additional_info / ignore
    hints from `profiles_to_consolidate` plus the three move lists. Shared by
    the geni and familio generation entry points so both observe identical
    consolidation behaviour (the familio projection keys on the SAME canonical
    res_names the geni consolidation produces)."""
    from verso.ru.targets.geni.translator import Consolidation

    profile_preferences: dict[str, Any] = {}
    profile_overrides: dict[str, Any] = {}
    profile_additional_info: dict[str, Any] = {}
    profile_lifecycle_ignores: dict[str, Any] = {}
    profile_ignores: dict[str, Any] = {}
    profile_move_from_names: dict[str, str] = {}
    for target, cfg_entry in getattr(gcn, "profiles_to_consolidate", {}).items():
        if not isinstance(cfg_entry, dict):
            continue
        for stub in cfg_entry.get("profile_names", []) or []:
            if isinstance(stub, str):
                profile_move_from_names[stub] = target
        pref = cfg_entry.get("preference")
        if pref is not None:
            profile_preferences[target] = {
                "first_name": getattr(pref, "first_name", None),
                "middle_name": getattr(pref, "middle_name", None),
                "last_name": getattr(pref, "last_name", None),
                "birth_last_name": getattr(pref, "birth_last_name", None),
                "nicknames": list(getattr(pref, "nicknames", []) or []),
            }
        override = cfg_entry.get("override")
        if override is not None:
            # Pass the raw GeniProfile object through; translator
            # selectively copies fields it supports.
            profile_overrides[target] = override
        add_infos = cfg_entry.get("additional_info")
        if add_infos:
            profile_additional_info[target] = list(add_infos)
        lifecycle_ignores = cfg_entry.get("lifecycle_ignore_changes")
        if lifecycle_ignores:
            profile_lifecycle_ignores[target] = list(lifecycle_ignores)
        ignores = cfg_entry.get("ignore")
        if ignores:
            profile_ignores[target] = [
                {
                    "first_name": getattr(p, "first_name", None),
                    "middle_name": getattr(p, "middle_name", None),
                    "last_name": getattr(p, "last_name", None),
                    "birth_last_name": getattr(p, "birth_last_name", None),
                    "title": getattr(p, "title", None),
                    # Event-date ignores (suppress a known-spurious
                    # birth/death/baptism/burial date conflict during
                    # consolidation-conflict validation). `GeniProfile`
                    # wraps each in a `GeniEvent`; we pass the `GeniDate`.
                    "birth.date": _ignore_event_date(p, "birth"),
                    "death.date": _ignore_event_date(p, "death"),
                    "baptism.date": _ignore_event_date(p, "baptism"),
                    "burial.date": _ignore_event_date(p, "burial"),
                }
                for p in ignores
            ]
    merged_move_list = dict(gcn.profile_move_list)
    for stub, target in profile_move_from_names.items():
        merged_move_list.setdefault(stub, target)
    return Consolidation(
        profile_move_list=merged_move_list,
        union_move_list_v2=dict(getattr(gcn, "union_move_list_v2", {})),
        unions_to_consolidate=dict(getattr(gcn, "unions_to_consolidate", {})),
        profile_preferences=profile_preferences,
        profile_overrides=profile_overrides,
        profile_additional_info=profile_additional_info,
        profile_lifecycle_ignores=profile_lifecycle_ignores,
        profile_ignores=profile_ignores,
    )


def feed_all_records(gen, village_dir, years: list[int] | None,
                     skipped: list[tuple[Path, Exception]], *,
                     admit_all_unreviewed: bool = False,
                     seen: list[tuple[str, Any, ratchet.RecordPrint]] | None = None,
                     ids: RecordIds | None = None) -> None:
    """Discover every DSL record container under `village_dir` and route it to
    the matching `gen.add_*_records` method, in legacy iteration order. `years`
    restricts discovery; `skipped` collects files that failed to import; `ids`
    counts the records' ids as they are discovered (`discover_records`)."""
    for dsl_path, _, records in discover_records(
            str(village_dir), year=years or None, skipped=skipped,
            admit_all_unreviewed=admit_all_unreviewed, seen=seen, ids=ids):
        # Cat A1: DSL files whose basename starts with `other_` carry
        # records from a secondary parish (Неелово / Ябедные Пепелищи) that
        # appeared in the main village's residents' lives; route them to
        # `mk_YEAR_other_{type}.tf` matching legacy's 10 files.
        if dsl_path.name.startswith("other_"):
            records._other_parish = True  # type: ignore[attr-defined]  # dynamic routing flag
        gen.fed_sources.append((dsl_path.name, records))
        if isinstance(records, BirthRecords):
            gen.add_birth_records(records)
        elif isinstance(records, MarriageRecords):
            gen.add_marriage_records(records)
        elif isinstance(records, DeathRecords):
            gen.add_death_records(records)
        elif isinstance(records, CensusRecords):
            # Covers исповедные росписи too: an ИР re-labels the same
            # emitter through `CONFESSION_LIST` (file_prefix /
            # household_label / …), it is not a separate record type.
            gen.add_census_records(records)
        elif isinstance(records, ExternalSourceRecords):
            gen.add_external_source_records(records)
        elif isinstance(records, NameListRecords):
            gen.add_name_list_records(records)


def translate_village(village_dir, years: list[int] | None = None, *,
                      strict: bool = False, use_consolidation: bool = True,
                      admit_all_unreviewed: bool = False,
                      seen: list[tuple[str, Any, ratchet.RecordPrint]] | None = None,
                      ids: RecordIds | None = None):
    """Run the full DSL→domain translation for a village and `finalize()`.

    Loads `generate_config_names.py` (when present) into a `Consolidation`,
    discovers + feeds all DSL records, and finalizes the generator. Returns
    `(gen, skipped)`. This is the reusable translation core: `main()` inlines
    an equivalent flow (with geni-specific moved-block + output handling),
    while `generate_familio_tf` calls this to obtain the consolidated
    `GeniProfile` / `GeniUnion` domain model via `gen.canonical_profiles()` /
    `gen.canonical_unions()`.

    `use_consolidation=False` ignores the village's config entirely, so
    `canonical_profiles()` returns the RAW per-record res_names the DSL emits
    before any folding. That is the corpus you want when asking "what did this
    name become" (`verso.ru.consolidation.stale_stubs --suggest`): a stale entry's
    counterpart is usually itself folded, so it is absent from the consolidated
    set and the question looks unanswerable.

    Raises `RuntimeError` when `strict` and any DSL file was skipped (a skipped
    file silently drops its records — callers project a partial tree otherwise).

    `admit_all_unreviewed` / `seen`: the ratchet's seeding pass (`discover_records`).
    `ids`: every record's id, counted as the records are discovered.
    """
    from verso.ru.targets.geni.translator import TerraformGenerator

    village_dir = Path(village_dir)
    consolidation = None
    gcn = village_config(village_dir) if use_consolidation else None
    if gcn is not None:
        consolidation = make_consolidation(gcn)
    settings = corpus_data.village(village_dir)
    gen = TerraformGenerator(
        village_dir=str(village_dir),
        consolidation=consolidation,
        projects=list(settings.projects),
        extra_project_rules=dict(settings.project_rules),
        prev_revision=settings.prev_revision,
    )
    skipped: list[tuple[Path, Exception]] = []
    feed_all_records(gen, village_dir, years, skipped,
                     admit_all_unreviewed=admit_all_unreviewed, seen=seen, ids=ids)
    if strict and skipped:
        raise RuntimeError(
            f"{len(skipped)} DSL file(s) skipped due to import failure: "
            + ", ".join(str(p) for p, _ in skipped)
        )
    gen.finalize()
    return gen, skipped
