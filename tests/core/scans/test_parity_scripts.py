"""`verso scans strips|quadrants|descreen` write what the scripts of the reading plugin they replace write: the
same files, the same bytes, the same stdout, the same exit — on the invented album (`tests.scans_album`), in one
run. The scripts stay in `plugins/verso-reading` until the skills name `verso scans` (they are this test's
reference); `cards`, verso-ru's, is held so in `tests/ru/scans/test_commands.py`."""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("PIL")

from tests.scans_album import draw_album

ROOT = Path(__file__).resolve().parents[3]
SKILLS = ROOT / "plugins" / "verso-reading" / "skills"
STRIPS = SKILLS / "metric-books" / "scripts" / "scan_strips.py"
QUADRANTS = SKILLS / "transcription" / "scripts" / "make_crops.py"
DESCREEN = SKILLS / "census" / "scripts" / "descreen_crop.py"


def _run(argv: list[str], cwd: Path, lang: str = "ru") -> tuple[int, str, str]:
    env = {**os.environ, "VERSO_LANG": lang, "PYTHONIOENCODING": "utf-8"}
    done = subprocess.run([sys.executable, *argv], cwd=cwd, env=env, capture_output=True, text=True,
                          encoding="utf-8", timeout=300, check=False)
    return done.returncode, done.stdout, done.stderr


def _verso(*args: str) -> list[str]:
    return ["-m", "verso.core.cli", "scans", *args]


def _files(directory: Path) -> dict[str, str]:
    return {p.relative_to(directory).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(directory.rglob("*")) if p.is_file()}


@pytest.fixture
def root(tmp_path: Path) -> Path:
    draw_album(tmp_path)
    return tmp_path


@pytest.mark.parametrize("flags", [
    ["--box", "0.0,0.1,0.2,0.95"],                                   # a column: left to right
    ["--box", "0.05,0.02,0.95,0.12", "--per", "2", "--size", "500"],  # a line: stacked, two to a sheet
    ["--box", "0.0,0.1,0.2,0.95", "--frames", "0002-0004"],
])
def test_strips_writes_what_the_script_writes(root: Path, flags: list[str]):
    script = _run([str(STRIPS), str(root / "album"), *flags, "--out", str(root / "a")], root)
    ours = _run(_verso("strips", str(root / "album"), *flags, "--out", str(root / "b")), root)
    assert script[0] == ours[0] == 0, (script, ours)
    assert script[1].replace(str(root / "a"), "OUT") == ours[1].replace(str(root / "b"), "OUT")
    assert _files(root / "a") == _files(root / "b") != {}


@pytest.mark.parametrize("args", [
    ["{root}/nowhere", "--box", "0,0,1,1"],
    ["{root}/album", "--box", "0,0,1,1", "--frames", "9000-9999"],
])
def test_strips_refuses_as_the_script_does(root: Path, args: list[str]):
    argv = [a.replace("{root}", str(root)) for a in args] + ["--out", str(root / "o")]
    script = _run([str(STRIPS), *argv], root)
    ours = _run(_verso("strips", *argv), root)
    assert script == ours and script[0] == 2


def test_a_bad_box_is_refused_in_the_scripts_words(root: Path):
    for box in ("0,0,1", "0.5,0,0.4,1"):
        script = _run([str(STRIPS), str(root / "album"), "--box", box, "--out", str(root / "o")], root)
        ours = _run(_verso("strips", str(root / "album"), "--box", box, "--out", str(root / "o")), root)
        assert script[0] == ours[0] == 2
        assert script[2].splitlines()[-1].split("error: ")[1] == ours[2].splitlines()[-1].split("error: ")[1]


def test_quadrants_writes_what_the_script_writes(root: Path):
    frames = [str(root / "album" / "0003_1об.jpg"), str(root / "album" / "0005_(2об-3).jpg")]
    script = _run([str(QUADRANTS), *frames, "--out", str(root / "a")], root)
    ours = _run(_verso("quadrants", *frames, "--out", str(root / "b")), root)
    assert script[0] == ours[0] == 0
    assert script[1].replace(str(root / "a"), "OUT") == ours[1].replace(str(root / "b"), "OUT")
    assert _files(root / "a") == _files(root / "b") and len(_files(root / "a")) == 8


@pytest.mark.parametrize("args", [[], ["-"], ["0.1,0.2,0.6,0.5", "1.5"], ["0.1,0.2,0.6,0.5", "2", "horizontal"],
                                  ["-", "1.0", "raw", "90"]])
def test_descreen_writes_what_the_script_writes(root: Path, args: list[str]):
    frame = root / "album" / "0003_1об.jpg"
    script = _run([str(DESCREEN), str(frame), *args], root)
    shutil.move(root / "album" / "crops", root / "a")
    ours = _run(_verso("descreen", str(frame), *args), root)
    assert script[0] == ours[0] == 0, (script, ours)
    assert script[1] == ours[1]
    assert _files(root / "a") == _files(root / "album" / "crops") != {}
