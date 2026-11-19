"""verso.ru's catalogs against its code (`i18n.problems`)."""
from __future__ import annotations

import re
from pathlib import Path

import verso.ru
from verso.core import i18n

# A linter's message is `CODE.variant`, built by `issue()`/`says()` from the code and the variant; a
# label of the review page, `ui.*`, is named by the hints (ui-hints.toml, ui-v1.json) and the
# page, never by the code — tests/test_ui_hints.py holds them to the schema.
LINTER_KEY = re.compile(r"^[A-Z]{2,4}\d{3}\.")


#: Keys no code calls any more that stay in the catalogs, a catalog key being public (docs/compatibility.md),
#: until the minor version that may remove them; each with its reason.
DEPRECATED = {
    "statuses.unknown_key": "0.1.20: an unknown key of statuses.toml is corpus_data.unknown_key's (the same "
                            "text); kept until 0.2",
    # 0.1.45: the six single-record reports of `facts-check` print a finding in the words of its signal
    # (`facts.signal.*`, `verso.ru.cli.facts.format_signals`), the words a record's card says; the lines the
    # reports printed from before are called by nothing. Kept until 0.2.
    **{key: "0.1.45: said by facts.signal.* (format_signals); kept until 0.2" for key in (
        "cli.facts.name_days.finding", "cli.facts.name_days.lookalikes", "cli.facts.name_days.note",
        "cli.facts.wedding_calendar.note", "cli.facts.wedding_calendar.pascha",
        "cli.facts.wedding_calendar.other_months", "cli.facts.wedding_calendar.other_days",
        "cli.facts.lags.finding", "cli.facts.lags.baptism_note", "cli.facts.lags.burial_note",
        "cli.facts.wedding_ages.under_age", "cli.facts.wedding_ages.gap", "cli.facts.wedding_ages.note",
        "cli.facts.wedding_ages.groom", "cli.facts.wedding_ages.bride",
        "cli.facts.abbr.born", "cli.facts.abbr.christened", "cli.facts.abbr.died", "cli.facts.abbr.buried")},
}


# A signal's message is `facts.signal.<check>.<name>`, built by `verso.ru.facts.signals.signal_of` from the check
# and what it found; tests/test_facts_signals.py holds the catalogs to the table of them, none missing or left over.
SIGNAL_KEY = "facts.signal."


def _computed(key: str) -> bool:
    return (LINTER_KEY.match(key) is not None or key.startswith(("ui.", SIGNAL_KEY)) or key in DEPRECATED)


def test_catalogs_have_no_problems():
    assert i18n.problems("verso.ru", Path(verso.ru.__file__).parent, computed=_computed) == []


_CYRILLIC = re.compile(r"[А-Яа-яЁёѢѣІіѲѳѴѵ]")
_QUOTED = re.compile(r"«[^«»]*(?:«[^«»]*»[^«»]*)*»|\"[^\"]*\"")
#: English text that names a source's word unquoted, and why.
_UNQUOTED = {
    "MRA001.father_groom": "the roles as the record names them, in brackets",
    "MRA001.father_bride": "the roles as the record names them, in brackets",
    "MRA001.mother_groom": "the roles as the record names them, in brackets",
    "MRA001.mother_bride": "the roles as the record names them, in brackets",
    "WSD001.outside": "«поручитель», the record's word for a surety",
    "WSD006.too_many_groom": "Familio's «справочник», the name of its file",
    "WSD006.too_many_bride": "Familio's «справочник», the name of its file",
    "cli.echz.not_in_reading_room": "the shelfmark as the archive writes it",
    "CAI004.departed": "«сказка», the source's name",
    "PAF001.full_form": "the patronymic's forms, «полуотчество», as the sources name them",
    "AGE001.unit": "the CSV's columns (Лет, Месяцев, …) as they are named",
    "AGE001.unit_death": "the CSV's columns (Лет, Месяцев, …) as they are named",
    "NCSV005.gender": "names.csv's values of «Пол»",
    "scans.frames_by_position": "the book's own words (лист, л., об, ч., кадр), moved byte for byte from verso-app's scan tools",
    "scans.crops.verso_only": "the book's own words (лист, л., об, ч., кадр), moved byte for byte from verso-app's scan tools",
    "scans.spread.no_folios": "the book's own words (лист, л., об, ч., кадр), moved byte for byte from verso-app's scan tools",
    "scans.spread.no_recto": "the book's own words (лист, л., об, ч., кадр), moved byte for byte from verso-app's scan tools",
    "scans.help.frames": "the book's own words (лист, л., об, ч., кадр), moved byte for byte from verso-app's scan tools",
    "scans.help.verso_only": "the book's own words (лист, л., об, ч., кадр), moved byte for byte from verso-app's scan tools",
    "scans.help.part": "the parts of a metric book by their own titles (родившихся, …), moved byte for byte from verso-app",
    "scans.help.with_count": "the book's счётъ column and its номер, moved byte for byte from verso-app",
    "scans.help.spread_folio": "the book's own words (лист, л., об, ч., кадр), moved byte for byte from verso-app's scan tools",
    "scans.help.folio": "the book's own words (лист, л., об, ч., кадр), moved byte for byte from verso-app's scan tools",
    "scans.help.zoom_part": "the parts of a metric book by their own titles (родившихся, …), moved byte for byte from verso-app",
    "scans.zoom.no_presets": "the book's own words (лист, л., об, ч., кадр), moved byte for byte from verso-app's scan tools",
    "scans.zoom.no_column": "the book's own words (лист, л., об, ч., кадр), moved byte for byte from verso-app's scan tools",
    "scans.rows.bad_key": "the record list's own keys (м12, ж3) and the book's parts (ч.), as the reader types them",
    "scans.rows.no_page": "the book's own words (лист, л., об, ч., кадр), moved byte for byte from verso-app's scan tools",
    "scans.rows.found": "the book's part (ч.) and its счётъ column, moved byte for byte from verso-app",
    "scans.rows.help_rows": "the book's счётъ column, moved byte for byte from verso-app",
    "scans.rows.help_folios": "the book's own words (лист, л., об, ч., кадр), moved byte for byte from verso-app's scan tools",
    "scans.rows.help_count": "the book's счётъ column, moved byte for byte from verso-app",
    "facts.signal.note_default": "the note a card writes INTO a record («так в подлиннике»): a word of the record, not of the "
                                 "interface — the same in every language",
}


def test_english_catalog_has_no_cyrillic():
    """Verso.ru speaks English in English — a Cyrillic word in an English message is a word of
    the sources, quoted («…» or "…"), or named in `_UNQUOTED` with the reason."""
    import tomllib
    from tools.i18n_extract import _flatten

    data = tomllib.loads((Path(verso.ru.__file__).parent / "locales" / "en.toml").read_text(encoding="utf-8"))
    data.pop("schema", None)
    data.pop("untranslated", None)
    flat: dict[str, object] = {}
    _flatten(data, "", flat)
    found = [key for key, value in flat.items() if key not in _UNQUOTED and not key.startswith("forms.")
             and _CYRILLIC.search(_QUOTED.sub("", str(value)))]
    assert found == []
