"""An invented album of a metric book, drawn by Pillow — the fixture of the scan tools (`verso scans`), and the
golden outputs of the App's commands they replace.

Nothing here is a photograph: every leaf is drawn from a seeded random, the same bytes on every run. The album
(`album/`) is named as an archive names its frames — a cover, `0002_1.jpg`, `0003_1об.jpg`, a leaf whose frame
lies on its side and says so by its EXIF tag (orientation 6), and a spread `0005_(2об-3).jpg` —, its leaf 1 shot
upside down and declared so in its `scans.toml` stanza (`rotate_frames`), with the album's `top` and `enhance`. A
phone's album (`phone/`, `IMG_0001.jpg` …) carries no лист. A third (`faded/`) points its stanza at a village's
durable file (`village/scans.toml`), which holds its `enhance`. Each record of a leaf opens with a dark number in
the счётъ column, so `rows` finds its marks.

    python -m tests.scans_album golden     # in the App's venv: each case of CASES through
                                           # `python -m verso.app.scans.mk_scans`, VERSO_LANG=en and ru →
                                           # tests/golden/scans/<case>-<lang>.json
    python -m tests.scans_album golden-library   # each case of LIBRARY_CASES through `python -m verso.core.cli
                                           # scans` of the verso this venv imports →
                                           # tests/golden/scans-library/<case>-<lang>.json

The library's cases are the subcommands that replaced the reading plugin's scripts — `strips`, `quadrants`,
`descreen` and `cards` (`cards/`, three invented farm-census cards): their goldens were captured at the verso
commit where a test held them byte for byte to those scripts, and they hold the outputs since the scripts went.

A golden file is `{app_commit, argv, lang, stdout, stderr, exit, files, pixels}`: the argv with `<DIR>` for the
album's root, what the command printed (the root again `<DIR>`), its exit code, and every file it wrote — its
SHA-256, and the SHA-256 of its decoded pixels (`pixels`), which a platform whose JPEG coder differs still
matches. A library golden names its `commit` instead of `app_commit`, and adds each image's size (`sizes`).
This module imports nothing of verso: the App's venv runs it.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

GOLDEN = Path(__file__).resolve().parent / "golden" / "scans"
TITLE = "Маниловка 1900"
FADED_TITLE = "Собакевичи 1901"
# A leaf as the camera saw it: ~600 px across, as a reading-room scan of a small дело.
LEAF = (600, 820)
PAPER = (236, 226, 204)
INK = (52, 40, 34)

ALBUM_TOML = f'[album."{TITLE}"]\ntop = 0.12\nenhance = 1.6\nrotate_frames = {{ "1" = 180 }}\n'
FADED_TOML = f'[album."{FADED_TITLE}"]\nframes = "side"\nvillage = "village"\n'
VILLAGE_TOML = f'[album."{FADED_TITLE}"]\nenhance = 1.7\n'


def _leaf(seed: int, records: int, *, top: float = 0.12) -> Any:
    """One leaf: a printed header, the column rules, and `records` records — a number in the счётъ column at the
    height of each record's first line, and its lines of writing across the other columns."""
    from PIL import Image, ImageDraw
    rnd = random.Random(seed)
    w, h = LEAF
    im = Image.new("RGB", LEAF, PAPER)
    draw = ImageDraw.Draw(im)
    for x in range(int(w * 0.08), int(w * 0.92), 22):                  # the running header
        draw.rectangle((x, int(h * 0.03), x + rnd.randint(8, 16), int(h * 0.05)), fill=INK)
    draw.line((0, int(h * top) - 4, w, int(h * top) - 4), fill=INK, width=2)
    for fraction in (0.18, 0.32, 0.55, 0.78):                           # the column rules
        draw.line((int(w * fraction), int(h * top), int(w * fraction), h), fill=(120, 110, 100), width=1)
    span = (0.95 - top) / records
    for index in range(records):
        y = int(h * (top + 0.02 + span * index))
        draw.rectangle((int(w * 0.05), y, int(w * 0.05) + 14 + 6 * (index % 3), y + 16), fill=INK)
        for line in range(rnd.randint(2, 3)):
            ly = y + 4 + line * 22
            x = int(w * 0.2) + rnd.randint(0, 12)
            while x < int(w * 0.94):
                word = rnd.randint(18, 60)
                draw.line((x, ly + rnd.randint(-2, 2), min(x + word, int(w * 0.95)), ly + rnd.randint(-2, 2)),
                          fill=INK, width=3)
                x += word + rnd.randint(8, 18)
    return im


def _save(im: Any, path: Path, **kwargs: Any) -> None:
    im.save(path, quality=90, **kwargs)


def draw_album(root: Path) -> None:
    """The three albums and the village's file under `root`."""
    from PIL import Image, ImageDraw
    album = root / "album"
    album.mkdir(parents=True)
    cover = Image.new("RGB", LEAF, (90, 70, 50))
    ImageDraw.Draw(cover).rectangle((150, 300, 450, 360), fill=(200, 190, 160))
    _save(cover, album / "0001_обложка.jpg")
    _save(_leaf(1, 5).rotate(180), album / "0002_1.jpg")              # shot upside down: the stanza turns it
    _save(_leaf(2, 4), album / "0003_1об.jpg")
    lying = _leaf(3, 6).rotate(90, expand=True)                        # lies on its side; its tag stands it up
    exif = Image.Exif()
    exif[0x0112] = 6
    _save(lying, album / "0004_2.jpg", exif=exif.tobytes())
    spread = Image.new("RGB", (LEAF[0] * 2, LEAF[1]), PAPER)
    spread.paste(_leaf(4, 5), (0, 0))
    spread.paste(_leaf(5, 5), (LEAF[0], 0))
    _save(spread, album / "0005_(2об-3).jpg")
    (album / "scans.toml").write_text(ALBUM_TOML, encoding="utf-8")

    phone = root / "phone"
    phone.mkdir()
    for index in range(1, 4):
        _save(_leaf(10 + index, 3 + index), phone / f"IMG_{index:04d}.jpg")

    faded = root / "faded"
    faded.mkdir()
    _save(_leaf(21, 4), faded / "0001_1.jpg")
    _save(_leaf(22, 5), faded / "0002_1об.jpg")
    (faded / "scans.toml").write_text(FADED_TOML, encoding="utf-8")
    village = root / "village"
    village.mkdir()
    (village / "scans.toml").write_text(VILLAGE_TOML, encoding="utf-8")


def draw_cards(root: Path) -> Path:
    """Three invented card frames under `root/cards`: a table over a header on a wide spread."""
    from PIL import Image, ImageDraw
    album = root / "cards"
    album.mkdir(parents=True)
    for index in range(3):
        im = Image.new("RGB", (880, 670), (230, 222, 200))
        draw = ImageDraw.Draw(im)
        for row in range(8):
            draw.line((20, 40 + 25 * row, 560, 40 + 25 * row), fill=(60, 50, 40), width=2)
        draw.rectangle((680, 250, 780, 285), outline=(60, 50, 40), width=3)
        draw.text((690, 255), f"{index + 7}", fill=(20, 20, 20))
        draw.text((820, 8), f"{index + 41}", fill=(80, 80, 80))
        im.save(album / f"card_{index:02d}.jpg", quality=90)
    return album


# The cases: a name and the subcommand's argv, `<DIR>` the album's root. The same argv runs `verso-scans` (the
# App's) and `verso scans` (the library's). Each runs on an album drawn afresh: `spread`, `zoom` and `rows` write
# beside the frames by default, and a file left there is a page of the next case's album.
CASES: list[tuple[str, list[str]]] = [
    ("check", ["check", "<DIR>/album"]),
    ("check-range", ["check", "<DIR>/album", "--first", "1", "--last", "3"]),
    ("check-outside", ["check", "<DIR>/album", "--first", "2", "--last", "4"]),
    ("check-phone", ["check", "<DIR>/phone"]),
    ("check-whole", ["check", "<DIR>/faded"]),
    ("headers", ["headers", "<DIR>/album", "--out", "<DIR>/headers"]),
    ("headers-rows", ["headers", "<DIR>/album", "--out", "<DIR>/headers", "--rows", "2", "--strip", "0.3"]),
    ("headers-frames", ["headers", "<DIR>/album", "--out", "<DIR>/headers", "--frames"]),
    ("headers-phone", ["headers", "<DIR>/phone", "--out", "<DIR>/headers"]),
    ("crops", ["crops", "<DIR>/album", "--out", "<DIR>/crops"]),
    ("crops-part1", ["crops", "<DIR>/album", "--out", "<DIR>/crops", "--part", "1"]),
    ("crops-verso", ["crops", "<DIR>/album", "--out", "<DIR>/crops", "--verso-only", "--part", "3", "--grey"]),
    ("crops-count", ["crops", "<DIR>/album", "--out", "<DIR>/crops", "--part", "2", "--with-count",
                     "--from", "2", "--to", "3", "--enhance", "1.6", "--top", "0.1"]),
    ("crops-window", ["crops", "<DIR>/album", "--out", "<DIR>/crops", "--x0", "0.3", "--x1", "0.7", "--scale", "1.2"]),
    ("crops-phone", ["crops", "<DIR>/phone", "--out", "<DIR>/crops", "--from", "2"]),
    ("crops-phone-verso", ["crops", "<DIR>/phone", "--out", "<DIR>/crops", "--verso-only"]),
    ("spread", ["spread", "<DIR>/album", "--folio", "1об"]),
    ("spread-band", ["spread", "<DIR>/album", "--folio", "2", "--band", "0.2", "0.6", "--scale", "1.5",
                     "--enhance", "1.6", "--out", "<DIR>/s.jpg"]),
    ("spread-no-recto", ["spread", "<DIR>/album", "--folio", "3"]),
    ("spread-no-page", ["spread", "<DIR>/album", "--folio", "7"]),
    ("spread-phone", ["spread", "<DIR>/phone", "--folio", "1"]),
    ("zoom", ["zoom", "<DIR>/album", "--folio", "1об", "--part", "1", "--col", "godparents", "--row", "2", "3"]),
    ("zoom-box", ["zoom", "<DIR>/album", "--folio", "1", "--box", "0.1", "0.2", "0.6", "0.5", "--colour",
                  "--tag", "b", "--scale", "2"]),
    ("zoom-enhance", ["zoom", "<DIR>/album", "--folio", "3", "--part", "3", "--col", "age", "--enhance", "1",
                      "--top", "0.2", "--pad", "0.05", "--scale", "3", "--out", "<DIR>/z.jpg"]),
    ("zoom-spread-half", ["zoom", "<DIR>/album", "--folio", "2об", "--part", "2", "--col", "bride", "--scale", "2"]),
    ("zoom-phone", ["zoom", "<DIR>/phone", "--folio", "2", "--scale", "2"]),
    ("zoom-phone-village", ["zoom", "<DIR>/phone", "--folio", "кадр3", "--village", "<DIR>/village",
                            "--album-title", "Собакевичи", "--scale", "2"]),
    ("zoom-faded", ["zoom", "<DIR>/faded", "--folio", "1об", "--part", "3", "--col", "cause", "--scale", "2"]),
    ("zoom-layout", ["zoom", "<DIR>/faded", "--folio", "1", "--layout", "<DIR>/village/scans.toml", "--scale", "2"]),
    ("zoom-no-page", ["zoom", "<DIR>/album", "--folio", "9"]),
    ("zoom-no-page-phone", ["zoom", "<DIR>/phone", "--folio", "9"]),
    ("zoom-bad-column", ["zoom", "<DIR>/album", "--folio", "1", "--col", "name"]),
    ("zoom-bad-box", ["zoom", "<DIR>/album", "--folio", "1", "--box", "1", "2", "30", "40"]),
    ("rows", ["rows", "<DIR>/album", "--part", "1", "--folio", "1об", "2"]),
    ("rows-one", ["rows", "<DIR>/album", "--part", "3", "--folio", "1", "--x0", "0.02", "--x1", "0.98",
                  "--top", "0.1", "--bottom", "0.95", "--out", "<DIR>/r.jpg"]),
    ("rows-count", ["rows", "<DIR>/album", "--part", "2", "--folio", "3", "--count", "0.0", "0.2"]),
    ("rows-phone", ["rows", "<DIR>/phone", "--part", "1", "--folio", "1", "3"]),
    ("rows-faded", ["rows", "<DIR>/faded", "--part", "1", "--folio", "1", "1об", "--village", "<DIR>/village"]),
    ("rows-bad-leaf", ["rows", "<DIR>/album", "--part", "1", "--folio", "1", "--x0", "0.6", "--x1", "0.4"]),
    ("rows-no-page", ["rows", "<DIR>/album", "--part", "1", "--folio", "8"]),
]
LANGS = ("en", "ru")

LIBRARY_GOLDEN = GOLDEN.parent / "scans-library"
# The library's cases, on the albums and the cards drawn afresh. `strips` labels its strips in a system font (Arial,
# DejaVu Sans, else Pillow's own), so only its names, sizes and output are the same on every platform.
LIBRARY_CASES: list[tuple[str, list[str]]] = [
    ("strips-column", ["strips", "<DIR>/album", "--box", "0.0,0.1,0.2,0.95", "--out", "<DIR>/strips"]),
    ("strips-line", ["strips", "<DIR>/album", "--box", "0.05,0.02,0.95,0.12", "--per", "2", "--size", "500",
                     "--out", "<DIR>/strips"]),
    ("strips-frames", ["strips", "<DIR>/album", "--box", "0.0,0.1,0.2,0.95", "--frames", "0002-0004",
                       "--out", "<DIR>/strips"]),
    ("strips-no-album", ["strips", "<DIR>/nowhere", "--box", "0,0,1,1", "--out", "<DIR>/strips"]),
    ("strips-no-frame", ["strips", "<DIR>/album", "--box", "0,0,1,1", "--frames", "9000-9999", "--out", "<DIR>/strips"]),
    ("strips-bad-box", ["strips", "<DIR>/album", "--box", "0.5,0,0.4,1", "--out", "<DIR>/strips"]),
    ("quadrants", ["quadrants", "<DIR>/album/0003_1об.jpg", "<DIR>/album/0005_(2об-3).jpg", "--out", "<DIR>/q"]),
    ("descreen", ["descreen", "<DIR>/album/0003_1об.jpg"]),
    ("descreen-band", ["descreen", "<DIR>/album/0003_1об.jpg", "0.1,0.2,0.6,0.5", "1.5"]),
    ("descreen-horizontal", ["descreen", "<DIR>/album/0003_1об.jpg", "0.1,0.2,0.6,0.5", "2", "horizontal"]),
    ("descreen-raw", ["descreen", "<DIR>/album/0003_1об.jpg", "-", "1.0", "raw", "90"]),
    ("cards", ["cards", "<DIR>/cards", "<DIR>/out"]),
    ("cards-table", ["cards", "<DIR>/cards", "<DIR>/out", "--table", "0:0:0.7:0.4"]),
    ("cards-zoom", ["cards", "<DIR>/cards", "<DIR>/out", "--zoom", "1:0.2:0.1:0.6:0.4"]),
    ("cards-no-image", ["cards", "<DIR>/village", "<DIR>/out"]),
]
#: Whose bytes hang on the platform's fonts: compared by name, size and output only.
FONT_BOUND = {"strips"}


def argv_for(argv: list[str], root: Path) -> list[str]:
    return [arg.replace("<DIR>", str(root)) for arg in argv]


def blank(text: str, root: Path) -> str:
    """`text` with the album's root written `<DIR>`."""
    for form in {str(root.resolve()), str(root)}:
        text = text.replace(form, "<DIR>")
    return text


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def tree(root: Path) -> dict[str, str]:
    """Every file under `root` by its path from it, and its SHA-256."""
    return {p.relative_to(root).as_posix(): _sha(p.read_bytes()) for p in sorted(root.rglob("*")) if p.is_file()}


def written(root: Path, before: dict[str, str]) -> dict[str, str]:
    """The files under `root` a run wrote or changed: not in `before`, or not as `before` had them."""
    return {name: sha for name, sha in tree(root).items() if before.get(name) != sha}


def pixels(path: Path) -> str:
    """The SHA-256 of an image's decoded pixels, its mode and size; of the file's bytes when it is no image."""
    from PIL import Image
    try:
        with Image.open(path) as im:
            im.load()
            return _sha(f"{im.mode} {im.size}".encode() + im.tobytes())
    except Exception:
        return _sha(path.read_bytes())


def size(path: Path) -> list[int] | None:
    """An image's size, width and height; None when the file is no image."""
    from PIL import Image
    try:
        with Image.open(path) as im:
            return list(im.size)
    except Exception:
        return None


def _app_commit() -> str:
    import verso.app  # pyright: ignore[reportMissingImports] — the App's venv runs this
    where = Path(verso.app.__file__).resolve().parent
    done = subprocess.run(["git", "-C", str(where), "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                          check=True)
    return done.stdout.strip()


def capture(name: str, argv: list[str], lang: str, commit: str) -> dict[str, Any]:
    """One case run through the App's `verso-scans`, on an album drawn afresh."""
    with tempfile.TemporaryDirectory(prefix="scans-golden-") as scratch:
        root = Path(scratch)
        draw_album(root)
        before = tree(root)
        env = {**os.environ, "VERSO_LANG": lang, "PYTHONIOENCODING": "utf-8"}
        env.pop("VERSO_WORKSPACE", None)
        done = subprocess.run([sys.executable, "-m", "verso.app.scans.mk_scans", *argv_for(argv, root)],
                              cwd=root, env=env, capture_output=True, text=True, encoding="utf-8")
        files = written(root, before)
        return {"app_commit": commit, "case": name, "argv": argv, "lang": lang,
                "stdout": blank(done.stdout, root), "stderr": blank(done.stderr, root), "exit": done.returncode,
                "files": files, "pixels": {f: pixels(root / f) for f in files}}


def golden() -> int:
    commit = _app_commit()
    if GOLDEN.exists():
        shutil.rmtree(GOLDEN)
    GOLDEN.mkdir(parents=True)
    for name, argv in CASES:
        for lang in LANGS:
            record = capture(name, argv, lang, commit)
            (GOLDEN / f"{name}-{lang}.json").write_text(
                json.dumps(record, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
            print(f"{name}-{lang}: exit {record['exit']}, {len(record['files'])} file(s)")
    return 0


def _library_commit() -> str:
    import verso.core
    where = Path(verso.core.__file__).resolve().parent
    done = subprocess.run(["git", "-C", str(where), "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                          check=True)
    return done.stdout.strip()


def capture_library(name: str, argv: list[str], lang: str, commit: str) -> dict[str, Any]:
    """One library case run through `verso scans`, on the albums and the cards drawn afresh."""
    with tempfile.TemporaryDirectory(prefix="scans-golden-") as scratch:
        root = Path(scratch)
        draw_album(root)
        draw_cards(root)
        before = tree(root)
        env = {**os.environ, "VERSO_LANG": lang, "PYTHONIOENCODING": "utf-8"}
        env.pop("VERSO_WORKSPACE", None)
        done = subprocess.run([sys.executable, "-m", "verso.core.cli", "scans", *argv_for(argv, root)],
                              cwd=root, env=env, capture_output=True, text=True, encoding="utf-8")
        files = written(root, before)
        return {"commit": commit, "case": name, "argv": argv, "lang": lang,
                "stdout": blank(done.stdout, root), "stderr": blank(done.stderr, root), "exit": done.returncode,
                "files": files, "pixels": {f: pixels(root / f) for f in files},
                "sizes": {f: size(root / f) for f in files}}


def golden_library() -> int:
    commit = _library_commit()
    if LIBRARY_GOLDEN.exists():
        shutil.rmtree(LIBRARY_GOLDEN)
    LIBRARY_GOLDEN.mkdir(parents=True)
    for name, argv in LIBRARY_CASES:
        for lang in LANGS:
            record = capture_library(name, argv, lang, commit)
            (LIBRARY_GOLDEN / f"{name}-{lang}.json").write_text(
                json.dumps(record, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
            print(f"{name}-{lang}: exit {record['exit']}, {len(record['files'])} file(s)")
    return 0


def matches_golden(golden: dict[str, Any], root: Path, before: dict[str, str], code: int, out: str,
                   err: str) -> list[str]:
    """How a run under `root` differs from its golden; empty when it does not. A file of other bytes matches by
    its decoded pixels off the platform the golden was captured on (macOS); a font-bound subcommand's files match
    by name and size."""
    wrong: list[str] = []
    if (code, blank(out, root), blank(err, root)) != (golden["exit"], golden["stdout"], golden["stderr"]):
        wrong.append(f"exit/stdout/stderr: {(code, blank(out, root), blank(err, root))!r}")
    files = written(root, before)
    if sorted(files) != sorted(golden["files"]):
        return [*wrong, f"files: {sorted(files)} != {sorted(golden['files'])}"]
    for name, sha in files.items():
        if golden["argv"][0] in FONT_BOUND:
            if size(root / name) != golden["sizes"][name]:
                wrong.append(f"{name}: size {size(root / name)} != {golden['sizes'][name]}")
        elif sha != golden["files"][name]:
            if pixels(root / name) != golden["pixels"][name]:
                wrong.append(f"{name}: other pixels than the golden's")
            elif os.uname().sysname == "Darwin":
                wrong.append(f"{name}: other bytes than the golden's, on the platform it was captured on")
    return wrong


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("golden", help="capture the App's outputs into tests/golden/scans")
    sub.add_parser("golden-library", help="capture the library's outputs into tests/golden/scans-library")
    draw = sub.add_parser("draw", help="draw the albums under DIR")
    draw.add_argument("directory", type=Path)
    args = parser.parse_args(argv)
    if args.command == "golden":
        return golden()
    if args.command == "golden-library":
        return golden_library()
    draw_album(args.directory)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
