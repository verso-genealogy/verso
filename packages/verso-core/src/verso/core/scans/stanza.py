"""An album's geometry, read from its stanza of `scans.toml` — never written.

`scans.toml` describes the photography of each дело: `[album."<title>"]` with where the writing begins and ends
(`top`, `bottom`), whether a frame is a spread (`frames`), the turn the frames need on top of their own tag
(`rotate`, per frame `rotate_frames`), the push a faded hand needs (`enhance`), and — in an album's own copy of
the file — the `village` directory whose `scans.toml` is the durable one. Its windows (`[[album."…".box]]`) and the
other keys are the review page's (Verso writes the file); this module reads only what the scan tools cut by, and
passes over the rest.

Which file and which album, as the tools have always chosen: the album directory's own `scans.toml` first, else the
village's (`--village`), else the one `--layout` names; the title given (exact, else the one album whose title
contains it), else the file's only album. `enhance` is asked of the album's own copy first and then of the durable
file its `village` points at, since a scratch copy of an album shadows the file Verso writes the look into.

Pure: `tomllib`, no Pillow.
"""
from __future__ import annotations

import tomllib
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from verso.core.scans.look import INKS, MAX_ENHANCE

__all__ = ["Stanza", "enhance_for", "for_album", "rotation"]

# The file an album directory and a village directory each keep.
FILE = "scans.toml"


@dataclass(frozen=True)
class Stanza:
    """The geometry of one photographed дело, as the scan tools read it."""
    title: str
    # "side" — one leaf per file; "spread" — one frame holds both leaves, whatever its name says.
    frames: str = "side"
    top: float | None = None
    bottom: float | None = None
    # Degrees counter-clockwise, on top of the frame's own tag; a frame's own entry REPLACES the album's.
    rotate: int = 0
    rotate_frames: tuple[tuple[str, int], ...] = ()
    # 1 is plain autocontrast; above it the faded-hand push (`look.legible`).
    enhance: float = 1.0
    village: str = ""

    def rotation_for(self, label: str) -> int:
        """The turn for the page `label`: its own entry, else the album's."""
        return dict(self.rotate_frames).get(label, self.rotate)


@dataclass(frozen=True)
class Stanzas:
    """The albums of one `scans.toml`, by title."""
    albums: Mapping[str, Stanza]

    def album(self, title: str) -> Stanza | None:
        """Exact title, else the one album whose title contains it."""
        if title in self.albums:
            return self.albums[title]
        hits = [a for name, a in self.albums.items() if title in name]
        return hits[0] if len(hits) == 1 else None


EMPTY = Stanzas(albums={})


def _enhance(body: Mapping[str, object]) -> float:
    """The stanza's push: a value of the wrong kind or out of range is dropped, and so is one beside an `ink` —
    two answers to one pale hand, of which the ink stands."""
    enhance, ink = body.get("enhance", 1.0), body.get("ink", "")
    if isinstance(enhance, bool) or not isinstance(enhance, (int, float)) or not 1 <= enhance <= MAX_ENHANCE:
        return 1.0
    if ink in INKS and enhance > 1:
        return 1.0
    return float(enhance)


def parse(text: str) -> Stanzas:
    """The albums of the TOML `text`. An empty or album-less file is no album."""
    data = tomllib.loads(text)
    albums: dict[str, Stanza] = {}
    for title, body in (data.get("album") or {}).items():
        if not isinstance(body, dict):
            continue
        per_frame = body.get("rotate_frames")
        albums[title] = Stanza(
            title=title,
            frames=body.get("frames", "side"),
            top=body.get("top"),
            bottom=body.get("bottom"),
            rotate=int(body.get("rotate", 0)) % 360,
            rotate_frames=tuple((str(label), int(degrees) % 360) for label, degrees in per_frame.items())
            if isinstance(per_frame, dict) else (),
            enhance=_enhance(body),
            village=body.get("village", ""),
        )
    return Stanzas(albums=albums)


def load(path: Path) -> Stanzas:
    """The albums of the file at `path`; none when there is no file."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return EMPTY
    return parse(text)


def find_file(directory: Path, village: Path | None = None) -> Path | None:
    """The album's own `scans.toml`, else the village's: a scratch copy of an album is read before the durable
    file, so it can be tried without touching the village's."""
    local = directory / FILE
    if local.exists():
        return local
    if village is not None and (village / FILE).exists():
        return village / FILE
    return None


def for_album(directory: Path, *, layout: str | None = None, village: str | None = None,
              album_title: str | None = None) -> tuple[Path | None, str | None, Stanzas]:
    """(the file read, the album's title, the file's albums) for the album in `directory`: `layout` names the file
    outright, else the album's own, else `village`'s; the title as given (the album's full title when it names
    one), else the file's only album."""
    path = Path(layout) if layout else find_file(directory, Path(village) if village else None)
    if path is None:
        return None, album_title, EMPTY
    stanzas = load(path)
    title = album_title
    if title is None and len(stanzas.albums) == 1:
        title = next(iter(stanzas.albums))
    elif title is not None:
        found = stanzas.album(title)
        title = found.title if found else title
    return path, title, stanzas


def rotation(directory: Path, *, layout: str | None = None, village: str | None = None,
             album_title: str | None = None) -> Callable[[str], int]:
    """Page label → declared turn, for the album in `directory`; 0 for every page without a stanza."""
    _, title, stanzas = for_album(directory, layout=layout, village=village, album_title=album_title)
    album = stanzas.album(title) if title else None
    return album.rotation_for if album else (lambda label: 0)


def durable_file(*, layout: str | None, village: str | None, album_village: str, album_dir: Path,
                 read_path: Path | None) -> Path:
    """The `scans.toml` that holds the album for good: `layout`, then `village`'s, then the village the album's
    own copy points at, and only then the file read — the album's own copy, when it is itself the durable one."""
    if layout:
        return Path(layout)
    if village:
        return Path(village) / FILE
    if album_village:
        return Path(album_village) / FILE
    return read_path if read_path is not None else album_dir / FILE


def enhance_for(directory: Path, *, layout: str | None, village: str | None, read_path: Path | None,
                title: str | None, album: Stanza | None) -> float:
    """The push the album's stanza declares for a faded hand: the album's own copy first, then the durable file
    (`durable_file`), which the copy shadows; 1 when neither says."""
    if album is not None and album.enhance > 1:
        return album.enhance
    durable = durable_file(layout=layout, village=village, album_village=(album.village if album else ""),
                           album_dir=directory, read_path=read_path)
    if title is None or durable == read_path:
        return 1.0
    kept = load(durable).album(title)
    return kept.enhance if kept else 1.0
