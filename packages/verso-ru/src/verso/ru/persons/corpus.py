"""The people of a corpus: every DSL file under its root read for `verso.ru.persons.people`,
kept by the files' stamps (the App's contract L8 with the library, from Verso's service before 0.1.0).

The first index runs every DSL module (a few seconds — Verso's `serve` builds it in
the background); after that a file whose (mtime, size) moved re-runs alone, a file
gone takes its people with it, and the stamps are looked at no more often than
`recheck` seconds — `touched()` makes the next question look at once (a file saved).
A file that does not import names nobody until it does.
"""
from __future__ import annotations

import threading
import time
from pathlib import Path

from verso.ru.persons.people import PeopleIndex, Sighting, sightings_of
from verso.core.pipeline.load import dsl_files, load_module, village_dirs


class PeopleCorpus:
    def __init__(self, root: Path, *, recheck: float = 5.0) -> None:
        self.root = root.resolve()
        self._recheck = recheck
        self._files: dict[Path, tuple[tuple[int, int], list[Sighting]]] = {}
        self._index: tuple[float, PeopleIndex] | None = None
        self._lock = threading.Lock()

    def index(self) -> PeopleIndex:
        """Every person the corpus names with a patronymic or a surname, and the
        status and place written beside them — read off the BUILT records, since
        most statuses and places are a constant or a book's default."""
        with self._lock:
            now = time.monotonic()
            if self._index is not None and now - self._index[0] < self._recheck:
                return self._index[1]
            changed = self._index is None
            seen: set[Path] = set()
            for village in village_dirs(self.root):
                for path in dsl_files(village):
                    seen.add(path)
                    st = path.stat()
                    stamp = (st.st_mtime_ns, st.st_size)
                    cached = self._files.get(path)
                    if cached is None or cached[0] != stamp:
                        try:
                            found = sightings_of(vars(load_module(path)), village=village.name,
                                                 year=int(path.parent.name),
                                                 file=path.relative_to(self.root).as_posix())
                        except Exception:  # a file that does not import names nobody yet
                            found = []
                        self._files[path] = (stamp, found)
                        changed = True
            for gone in set(self._files) - seen:
                del self._files[gone]
                changed = True
            if changed or self._index is None:
                self._index = (now, PeopleIndex(s for _, found in self._files.values() for s in found))
            else:
                self._index = (now, self._index[1])
            return self._index[1]

    def touched(self) -> None:
        """A file was written: the next `index()` looks at the stamps at once."""
        with self._lock:
            self._index = None if self._index is None else (0.0, self._index[1])
