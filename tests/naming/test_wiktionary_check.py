"""The Wiktionary comparison (`tools/names_build/wiktionary_check.py`) on an invented dump: never on the real
one in a test — that is a download, and its text is CC BY-SA."""
from __future__ import annotations

import gzip
import json
from pathlib import Path

from tools.names_build import wiktionary_check as check
from verso.ru.gender import Gender
from verso.ru.naming.layer_files import FilesLayer
from verso.ru.naming.lexicon import FormsEntry, NameEntry

M, F = Gender.MALE, Gender.FEMALE


def _entry(word: str, category: str, genitive: str, *patronymics: tuple[str, str]) -> str:
    return json.dumps({
        "word": word, "lang_code": "ru", "pos": "noun", "categories": [{"name": category}],
        "forms": [{"form": genitive, "tags": ["singular", "genitive"]}, {"form": "x", "tags": ["plural", "genitive"]}],
        "related": [{"word": p, "raw_tags": ["Ближайшее родство", t]} for t, p in patronymics]}, ensure_ascii=False)


def test_the_check_finds_what_differs(tmp_path: Path) -> None:
    base = FilesLayer(tmp_path / "base", name="base", writable=True)
    base.put(NameEntry(M, "Зюзей", source="mk"))
    base.put(NameEntry(M, "Зюзий", source="mk"))
    base.put(NameEntry(F, "Зюза", source="mk"))
    base.put(NameEntry(F, "Зюзана", source="mk"))
    base.put(FormsEntry(M, "Зюзий", patronymic_m="Зюзьевич", source="editor"))
    dump = tmp_path / "dump.jsonl.gz"
    with gzip.open(dump, "wt", encoding="utf-8") as f:
        f.write(_entry("Зюзей", "Мужские имена/ru", "Зю́зея", ("отчество мужчины", "Зю́зеевич"),
                       ("отчество женщины", "Зюзеевна")) + "\n")
        f.write(_entry("Зюзий", "Мужские имена/ru", "Зюзия", ("отчество мужчины", "Зюзиевич")) + "\n")
        f.write(_entry("Зюза", "Женские имена греческого происхождения/ru", "Зюзи") + "\n")
        f.write(_entry("Зюзана", "Женские имена/ru", "Зюз\u00e1ны") + "\n")  # a Latin á for a stressed а
        f.write(json.dumps({"word": "Зюзя", "lang_code": "uk", "categories": ["Мужские имена/uk"]}) + "\n")
    counts, differences = check.compare(base.load(), check.read_dump(check._lines(dump)))
    assert differences == [
        ("F", "Зюза", "genitive", "Зюзы", "Зюзи", "other", "base", "rule"),
        ("M", "Зюзий", "patronymic_m", "Зюзьевич", "Зюзиевич", "-иевич/-ьевич", "base", "editor"),
    ]
    assert counts["names in the dump"] == 4 and counts["genitive: same"] == 3 and counts["patronymic_f: same"] == 1
