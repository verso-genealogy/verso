"""verso.ru.scans.album — how an album's pages are numbered (by лист, else by frame) and each page's image; the part
presets of `crops`; and that the scan tools stand apart from the DSL."""
from __future__ import annotations

import ast
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

import pytest

from verso.ru.scans.album import load_pages, open_page, page_size
from verso.ru.scans.cli.crops import DEFAULT_SCALE, PART_WINDOWS, crop_window
from verso.ru.scans.folio import Page, parse_frame

FOLIO_NAMES = ["001_обложка.jpg", "118_57.jpg", "119_57об.jpg", "120_58.jpg"]
PHONE_NAMES = ["IMG_20000101_120000.jpg", "IMG_20000101_120012.jpg"]


def directory_of(names: list[str]) -> tempfile.TemporaryDirectory[str]:
    tmp = tempfile.TemporaryDirectory()
    for name in names:
        (Path(tmp.name) / name).write_bytes(b"")
    return tmp


class LoadPages(unittest.TestCase):
    def test_folio_names_are_read_by_folio(self):
        with directory_of(FOLIO_NAMES) as path:
            pages, by_frame = load_pages(Path(path))
        self.assertFalse(by_frame)
        self.assertEqual(["кадр1", "57", "57об", "58"], [p.label for p in pages])

    def test_phone_names_fall_back_to_frames(self):
        # Before this fallback existed an album named as the phone wrote it parsed to nothing, and every
        # subcommand quietly produced an empty result.
        with directory_of(PHONE_NAMES) as path:
            pages, by_frame = load_pages(Path(path))
        self.assertTrue(by_frame)
        self.assertEqual(["кадр1", "кадр2"], [p.label for p in pages])

    def test_frames_can_be_forced_over_folio_names(self):
        with directory_of(FOLIO_NAMES) as path:
            pages, by_frame = load_pages(Path(path), force_frames=True)
        self.assertTrue(by_frame)
        self.assertEqual(4, len(pages))
        self.assertFalse(any(p.is_folio for p in pages))

    def test_non_images_do_not_become_pages(self):
        with directory_of([*PHONE_NAMES, "notes.txt"]) as path:
            pages, _ = load_pages(Path(path))
        self.assertEqual(2, len(pages))

    def test_empty_directory_is_frame_mode_with_nothing_in_it(self):
        with directory_of([]) as path:
            pages, by_frame = load_pages(Path(path))
        self.assertTrue(by_frame)
        self.assertEqual([], pages)


class CropWindow(unittest.TestCase):
    """The part presets are what keeps a sweep legible; pin them."""

    def test_no_part_is_the_full_leaf(self):
        args = Namespace(part=None, x0=None, x1=None, scale=None)
        self.assertEqual((0.0, 1.0, DEFAULT_SCALE), crop_window(args))

    def test_part_preset_is_used(self):
        args = Namespace(part=3, x0=None, x1=None, scale=None)
        self.assertEqual(PART_WINDOWS[3], crop_window(args))

    def test_explicit_flags_override_the_preset(self):
        args = Namespace(part=1, x0=0.1, x1=0.8, scale=1.0)
        self.assertEqual((0.1, 0.8, 1.0), crop_window(args))

    def test_with_count_puts_the_left_edge_back(self):
        # Verifying a DSL номер against the book needs the счётъ column, which every part preset drops.
        args = Namespace(part=1, x0=None, x1=None, scale=None, with_count=True)
        x0, x1, scale = crop_window(args)
        self.assertEqual(0.0, x0)
        self.assertEqual(PART_WINDOWS[1][1:], (x1, scale))

    def test_explicit_x0_still_wins_over_with_count(self):
        args = Namespace(part=1, x0=0.3, x1=None, scale=None, with_count=True)
        self.assertEqual(0.3, crop_window(args)[0])

    def test_absent_with_count_is_not_an_error(self):
        args = Namespace(part=2, x0=None, x1=None, scale=None)
        self.assertEqual(PART_WINDOWS[2], crop_window(args))


def test_a_bare_number_is_still_read_as_a_folio():
    # Deliberate: `063.jpg` of one album IS л. 63, and nothing in the name parts it from a file numbered 63 — a
    # name carries a лист or it does not, and a phone's timestamp does not.
    assert [p.label for p in parse_frame("063.jpg")] == ["63"]
    assert [p.label for p in parse_frame("061.png")] == ["61"]
    assert [p.number for p in parse_frame("20000101_120000.jpg")] == [0]


def test_a_frame_standing_up_in_an_album_of_spreads_is_one_page(tmp_path: Path):
    # The image's own shape decides: a spread lies on its side, a single page stands — after the file's
    # orientation tag and the album's declared turn.
    Image = pytest.importorskip("PIL.Image")
    Image.new("RGB", (150, 115)).save(tmp_path / "021_(011об-012).jpg")    # a spread, named whole
    Image.new("RGB", (98, 150)).save(tmp_path / "023_(013).jpg")           # one page, standing
    lying = Image.new("RGB", (150, 98))                                    # one page, tagged to stand
    exif = lying.getexif()
    exif[0x0112] = 6
    lying.save(tmp_path / "024_(013а).jpg", exif=exif)
    (tmp_path / "025_(014).jpg").write_bytes(b"")                          # unreadable: taken at its name

    pages, _ = load_pages(tmp_path, expand=True)
    assert [(p.label, p.half) for p in pages] == [
        ("11об", "L"), ("12", "R"), ("13", ""), ("13а", ""), ("14", "L"), ("14об", "R")]


def test_an_album_turned_a_quarter_reads_the_shape_turned(tmp_path: Path):
    Image = pytest.importorskip("PIL.Image")
    # Standing as stored, lying as the album declares it read: a spread.
    Image.new("RGB", (98, 150)).save(tmp_path / "001_(41об).jpg")
    assert [p.label for p in load_pages(tmp_path, expand=True, turn=90)[0]] == ["41об", "42"]
    assert [p.label for p in load_pages(tmp_path, expand=True)[0]] == ["41об"]


@pytest.mark.parametrize("half", ["", "L", "R"])
@pytest.mark.parametrize("rotate", [0, 90, 33])
def test_a_pages_size_is_its_images(tmp_path: Path, rotate: int, half: str):
    Image = pytest.importorskip("PIL.Image")
    frame = Image.new("RGB", (301, 157), "white")
    exif = frame.getexif()
    exif[0x0112] = 6
    frame.save(tmp_path / "f.jpg", exif=exif)
    page = Page(1, "", False, 1, "f.jpg", half)
    assert page_size(tmp_path, page, rotate) == open_page(tmp_path, page, rotate).size


def _imports(path: Path) -> set[str]:
    out: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            out |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module)
    return out


def test_no_dsl_imports():
    """The scan tools read images and filenames: nothing of the DSL, the domain or the records — and nothing of
    those reads them."""
    import verso.ru
    root = Path(verso.ru.__file__).parent
    scans = sorted((root / "scans").rglob("*.py"))
    assert scans
    for path in scans:
        assert {m for m in _imports(path) if m.startswith("verso.ru.") and not m.startswith(
            ("verso.ru.scans", "verso.ru.messages"))} == set(), path
    for path in sorted(root.rglob("*.py")):
        if "scans" in path.relative_to(root).parts or path.name == "plugin.py":
            continue
        assert not {m for m in _imports(path) if m.startswith("verso.ru.scans")}, path
