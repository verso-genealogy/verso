"""Which written parent status a newborn's сословие rests on.

`Birth.__init__` gives a newborn without a written status the one
`child_status_for` derives from a parent — the father's when he has a status,
else the mother's — and `Death.__init__` does the same for the deceased from the
first FATHER relative with a status, else the first MOTHER. Both run BEFORE
`RecordDefaults` fills anything, so only a status WRITTEN on the parent feeds
the derivation; a newborn whose parents are left to the defaults takes the
book's `status_male` / `status_female` itself.

So a parent's `status=` that repeats the book's default is not always
redundant. In one birth record the mother's «законная жена казенного
крестьянина» is the only status written in it; it makes the girl
«казенная крестьянская дочь», and without it she would be «казенная крестьянка».
VSR001 and `single_line_calls` asked only whether the parent's own value would
survive, and offered to remove it — which is how Verso's «Умолчания книги…»
came to refuse adding `status_mother` to that book: the removal the checks
demanded moved the child.

Not a module check — nothing here reports anything.
"""

import ast
from collections.abc import Collection, Mapping

from verso.ru.domain.statuses import child_status_for
from verso.ru.gender import Gender
# The checks' own reading of a person() node, so this one cannot drift from it.
from verso.ru.linters.checks.census_redundancy import _call_func_name, _person_arg
from verso.ru.linters.checks.census_status_redundancy import _STATUS_INDEX
from verso.ru.linters.checks.file_bindings import string_constants
from verso.ru.linters.checks.status_words import words_of

# birth(record_num, gender, …) / death(record_num, gender, …)
_GENDER_INDEX = 1


class _Unknown:
    """A status the AST cannot resolve to words: it may derive anything."""


UNKNOWN = _Unknown()

Derived = str | None | _Unknown


def _person(node: ast.expr | None) -> ast.Call | None:
    return node if isinstance(node, ast.Call) and _call_func_name(node) == "person" else None


def _kwarg(node: ast.Call, name: str) -> ast.expr | None:
    return next((kw.value for kw in node.keywords if kw.arg == name), None)


def _status(person: ast.Call) -> ast.expr | None:
    return _person_arg(person, _STATUS_INDEX, "status")


def _gender(record: ast.Call) -> Gender | None:
    node = _kwarg(record, "gender")
    if node is None and len(record.args) > _GENDER_INDEX:
        node = record.args[_GENDER_INDEX]
    if isinstance(node, ast.Attribute) and node.attr in Gender.__members__:
        return Gender[node.attr]
    return None


def _relatives(record: ast.Call, relationship: str) -> list[ast.Call]:
    listed = _kwarg(record, "relatives")
    if not isinstance(listed, (ast.List, ast.Tuple)):
        return []
    found: list[ast.Call] = []
    for element in listed.elts:
        if not (isinstance(element, ast.Call) and _call_func_name(element) == "relative"):
            continue
        person = _person(element.args[0] if element.args else _kwarg(element, "person"))
        rel = element.args[1] if len(element.args) > 1 else _kwarg(element, "relationship")
        if person is not None and isinstance(rel, ast.Attribute) and rel.attr == relationship:
            found.append(person)
    return found


def _chain(record: ast.Call) -> tuple[ast.Call | None, list[ast.Call]]:
    """The newborn (or the deceased) and the parents it may derive from, in
    the order its record's `__init__` consults them."""
    verb = _call_func_name(record)
    if verb == "birth":
        parents = [_person(_kwarg(record, "father")), _person(_kwarg(record, "mother"))]
        return _person(_kwarg(record, "child")), [p for p in parents if p is not None]
    if verb == "death":
        return (_person(_kwarg(record, "deceased")),
                _relatives(record, "FATHER") + _relatives(record, "MOTHER"))
    return None, []


def _derived(source: ast.Call | None, gender: Gender | None, texts: Mapping[str, str]) -> Derived:
    """What `child_status_for` gives the newborn from `source`'s written status."""
    if source is None:
        return None
    words = words_of(_status(source), texts)
    if words is None or gender is None:
        return UNKNOWN
    derived = child_status_for(words, gender)
    return str(derived) if derived is not None else None


def load_bearing_parent(record: ast.Call, redundant: Collection[ast.Call],
                        bindings: Mapping[str, ast.expr]) -> ast.Call | None:
    """The parent of birth / death `record` whose written status must stay
    although it repeats the book's default, or None.

    `redundant` holds the persons whose written status the calling check takes
    for a repetition of the default. Every such status is removed together —
    the check flags each one, and Verso's defaults dialog strips them in one
    round — so the question is whether the newborn's derived status survives
    all of them going. If it does not, the parent the derivation reads is kept;
    removing the others then changes nothing, since that parent is the one
    consulted first. A status the AST cannot resolve is kept rather than
    guessed at."""
    child, parents = _chain(record)
    if child is None or _status(child) is not None:
        return None
    written = [p for p in parents if _status(p) is not None]
    if not written or written[0] not in redundant:
        return None
    texts = string_constants(bindings)
    gender = _gender(record)
    remaining = (p for p in written if p not in redundant)
    before = _derived(written[0], gender, texts)
    after = _derived(next(remaining, None), gender, texts)
    if isinstance(before, _Unknown) or isinstance(after, _Unknown) or before != after:
        return written[0]
    return None


def derives_status(record: ast.Call, bindings: Mapping[str, ast.expr]) -> bool:
    """Whether the newborn (or the deceased) of `record` would take a status
    derived from a parent's were its own not written — so its own, though it
    repeats the book's default, is not redundant. True where the AST cannot
    tell."""
    _, parents = _chain(record)
    source = next((p for p in parents if _status(p) is not None), None)
    return _derived(source, _gender(record), string_constants(bindings)) is not None
