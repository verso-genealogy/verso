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
}


def _computed(key: str) -> bool:
    return LINTER_KEY.match(key) is not None or key.startswith("ui.") or key in DEPRECATED


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
