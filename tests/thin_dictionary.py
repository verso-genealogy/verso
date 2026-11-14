"""A workspace whose names lexicon is the tests' own, less some names and with the sex of others turned over.

The linters on records JSON read the names lexicon of the workspace they are given (owner decision Д2), which is
not always the workspace that wrote the file: a `Person` refuses a name its own lexicon lacks, so NAM001 and NAM002 are
seen on a file exported elsewhere, and a lexicon that gives a name the other sex shows the sex-reading codes
(NAM003, NAM004, GND001, NGA, RLA, CPL) what the writer's lexicon never showed them. `thin_workspace` builds such a
workspace from the fixture's: the tests' names layer copied, and above it a layer of removal rows (a names row whose
bases are `-` takes the key out of the stack, its forms with it) and of the names with their sex turned over; the
corpus (statuses, places) is linked to the fixture's so the catalog stays the one.
"""
from __future__ import annotations

from pathlib import Path

from verso.core import workspace
from verso.ru.gender import Gender
from verso.ru.naming.gender_inference import get_gender_from_name

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "workspace"
_NAMES_HEADER = "sex\tname\tbases\tcanonical\tsource\tnote\n"
_SEXES = {Gender.MALE: "M", Gender.FEMALE: "F"}
_FLIPPED = {Gender.MALE: "F", Gender.FEMALE: "M"}


def _sex_of(name: str) -> Gender | None:
    with workspace.use(FIXTURE):
        return get_gender_from_name(name)


def thin_workspace(root: Path, *, drop: frozenset[str] = frozenset(), flip: frozenset[str] = frozenset(),
                   names: bool = True) -> Path:
    """`root` made a workspace like the tests' own, its lexicon without the names in `drop` (their forms go with
    them) and with the sex of those in `flip` the other one; `names=False`: a workspace of schema 4 with no `[names]` —
    the one kind of workspace that has no names lexicon at all (a workspace of schema 6 has the base)."""
    root.mkdir(parents=True)
    lines = ["schema = 4" if not names else "schema = 6", "villages = []", 'plugins = ["ru"]', ""]
    if names:
        lines += ["[names]", 'layers = ["names-layer", "names-thin"]', ""]
        (root / "names-layer").symlink_to((FIXTURE / "names-layer").resolve())
        removals = [f"{sex}\t{name}\t-\t\tfixture\t" for name in sorted(drop) for sex in ("M", "F", "")]
        turned: list[str] = []
        for name in sorted(flip):
            sex = _sex_of(name)
            if sex is not None:
                removals.append(f"{_SEXES[sex]}\t{name}\t-\t\tfixture\t")
                turned.append(f"{_FLIPPED[sex]}\t{name}\t\t\tfixture\t")
        thin = root / "names-thin"
        thin.mkdir()
        (thin / "names.tsv").write_text(_NAMES_HEADER + "".join(f"{row}\n" for row in sorted(removals + turned)),
                                        encoding="utf-8")
    lines += ["[corpus]", 'dir = "corpus"', ""]
    (root / "verso.toml").write_text("\n".join(lines), encoding="utf-8")
    (root / "corpus").symlink_to((FIXTURE / "corpus").resolve())
    return root
