"""`verso site`: a village's site from its DSL files, or from an export of them.

The village is the mini corpus's (tests/village_fixture.py): invented books of 1858–1900.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

import village_fixture
from verso.core.pipeline.records import export_village
from verso.ru.cli.site import main


def _village(tmp_path: Path) -> Path:
    return village_fixture.root(tmp_path) / "Маниловка"


def _digest(out: Path) -> dict[str, str]:
    return {path.relative_to(out).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(out.rglob("*")) if path.is_file()}


def test_the_site_of_a_villages_dsl(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = tmp_path / "site"
    assert main(["--village", str(_village(tmp_path)), "--out", str(out), "--strict"]) == 0
    said = capsys.readouterr()
    assert "страниц" in said.out and said.err == ""
    book = (out / "books" / "hlestakovka" / "755-473-169" / "1900" / "birth" / "index.html").read_text(encoding="utf-8")
    assert "Рождения 1900 — Хлестаковка" in book and "Тимоѳей" in book and "не вычитано" in book
    assert (out / "books" / "manilovka" / "10-4-4044" / "1858" / "household" / "index.html").is_file()
    assert "<title>Маниловка</title>" in (out / "index.html").read_text(encoding="utf-8")


def test_an_export_makes_the_site_the_dsl_makes(tmp_path: Path) -> None:
    village = _village(tmp_path)
    assert main(["--village", str(village), "--out", str(tmp_path / "from-dsl")]) == 0
    export_village(village, tmp_path / "records")
    assert main(["--village", str(village), "--out", str(tmp_path / "from-json"),
                 "--records", str(tmp_path / "records")]) == 0
    assert _digest(tmp_path / "from-dsl") == _digest(tmp_path / "from-json")


def test_a_directory_that_holds_something_is_refused(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = tmp_path / "site"
    out.mkdir()
    (out / "mine.txt").write_text("keep", encoding="utf-8")
    assert main(["--village", str(_village(tmp_path)), "--out", str(out)]) == 2
    assert "не пуст" in capsys.readouterr().err and (out / "mine.txt").read_text(encoding="utf-8") == "keep"


def test_a_file_that_does_not_import_fails_a_strict_build(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    village = _village(tmp_path)
    (village / "1900" / "manilovka_births_1900.py").write_text("import nothing_such\n", encoding="utf-8")
    assert main(["--village", str(village), "--out", str(tmp_path / "lax")]) == 0
    assert main(["--village", str(village), "--out", str(tmp_path / "strict"), "--strict"]) == 1
    assert "пропущено файлов: 1" in capsys.readouterr().err


def test_the_settlements_details_reach_the_pages(tmp_path: Path) -> None:
    out = tmp_path / "site"
    assert main(["--village", str(_village(tmp_path)), "--out", str(out), "--title", "Село Маниловка",
                 "--summary", "Село на реке.", "--repo-url", "https://example.org/repo",
                 "--site-url", "https://example.org/site", "--revision", "abc1234",
                 "--license", "CC BY 4.0", "--license-url", "https://example.org/license"]) == 0
    front = (out / "index.html").read_text(encoding="utf-8")
    assert '<p class="summary">Село на реке.</p>' in front and "собрано из abc1234" in front
    assert '<a href="https://example.org/license" rel="license noopener">CC BY 4.0</a>' in front
    assert (out / "sitemap.xml").is_file()


def test_a_directory_of_prose_that_is_not_there_is_refused(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--village", str(_village(tmp_path)), "--out", str(tmp_path / "site"),
                 "--docs", str(tmp_path / "no-such-docs")]) == 2
    assert "no-such-docs" in capsys.readouterr().err and not (tmp_path / "site").exists()
