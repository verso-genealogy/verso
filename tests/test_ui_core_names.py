"""The core's interface schema names no record kind: the guard of LAY006 in its form, read
against the Russian books' vocabulary — here, beside the plugin, since tests/core blocks it."""
from __future__ import annotations

import ast
from pathlib import Path

from verso.core.records import ui


def _ru_words() -> set[str]:
    """Every record kind, role and JSON key of the Russian books' vocabulary."""
    from verso.core.records.fields import PERSON, role_of
    from verso.ru.records.vocabulary import VOCABULARY

    words: set[str] = set()
    for cls, spec in VOCABULARY.specs.items():
        words.add(spec.code)
        for f in spec.fields:
            words.add(VOCABULARY.json_keys[cls][f.name])
            if f.type == PERSON:
                words.add(role_of(f.name)[0].replace("_", ""))
    words.update(VOCABULARY.item_roles.values())
    words.update(VOCABULARY.item_roles)
    return words


def test_the_core_names_no_record_kind():
    """The guard of LAY006 in its form: no string of ui.py is a word of the Russian books'
    vocabulary but the ui-v1 format's own words, which `FORMAT` declares."""
    source = Path(ui.__file__).read_text(encoding="utf-8")
    literals = {node.value for node in ast.walk(ast.parse(source))
                if isinstance(node, ast.Constant) and isinstance(node.value, str)}
    leaked = (literals - set(ui.FORMAT)) & _ru_words()
    assert not leaked
    # FORMAT holds the format's words and nothing a plugin names that the format does not.
    assert set(ui.FORMAT) & _ru_words() <= {"person", "gender", "side", "role", "year", "day", "month",
                                            "number", "hidden", "age", "catalog", "page", "label", "labels",
                                            "records"}
