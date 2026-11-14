"""Tests for verso.ru.familio.lint_kin (FKN001 stale-kin check)."""

from __future__ import annotations

from pathlib import Path

from verso.ru.familio.lint_kin import lint_file, main


def _write_village(tmp_path: Path, *, move_list: str, kin: str) -> Path:
    (tmp_path / "generate_config_names.py").write_text(
        "profile_move_list: dict[str, str] = {\n" + move_list + "}\n"
        "unions_to_consolidate: dict[str, object] = {}\n"
        "profiles_to_consolidate = {}\n",
        encoding="utf-8",
    )
    kin_path = tmp_path / "familio_kin.py"
    kin_path.write_text("KIN: dict[str, str | None] = {\n" + kin + "}\n", encoding="utf-8")
    return kin_path


def test_flags_kin_key_that_is_a_folded_stub(tmp_path: Path) -> None:
    kin_path = _write_village(
        tmp_path,
        move_list='    "_1897_06_16_ivan_alekseevich_zhevakin_mk_births_21_child": "ivan_alekseevich_zhevakin",\n',
        kin='    "_1897_06_16_ivan_alekseevich_zhevakin_mk_births_21_child": None,\n',
    )
    findings = lint_file(kin_path)
    assert len(findings) == 1
    f = findings[0]
    assert f.code == "FKN001"
    assert f.severity == "error"
    assert "ivan_alekseevich_zhevakin" in f.message  # suggests the canonical
    assert f.line == 2  # inside the KIN dict


def test_clean_when_kin_keys_are_canonicals_or_unfolded(tmp_path: Path) -> None:
    kin_path = _write_village(
        tmp_path,
        move_list='    "_1897_06_16_ivan_alekseevich_zhevakin_mk_births_21_child": "ivan_alekseevich_zhevakin",\n',
        # canonical target + an unfolded standalone per-record stub → both fine
        kin='    "ivan_alekseevich_zhevakin": None,\n'
            '    "_1906_11_26_ivan_alekseevich_zhevakin_mk_births_23_child": None,\n',
    )
    assert lint_file(kin_path) == []


def test_missing_kin_var_reports_fkn000(tmp_path: Path) -> None:
    (tmp_path / "generate_config_names.py").write_text(
        "profile_move_list: dict[str, str] = {}\n", encoding="utf-8"
    )
    kin_path = tmp_path / "familio_kin.py"
    kin_path.write_text("SOMETHING_ELSE = {}\n", encoding="utf-8")
    findings = lint_file(kin_path)
    assert len(findings) == 1 and findings[0].code == "FKN000"


def test_main_exit_codes(tmp_path: Path) -> None:
    bad = _write_village(
        tmp_path,
        move_list='    "_x_stub": "canon",\n',
        kin='    "_x_stub": None,\n',
    )
    assert main(["prog", str(bad)]) == 1
    good = _write_village(
        tmp_path,
        move_list='    "_x_stub": "canon",\n',
        kin='    "canon": None,\n',
    )
    assert main(["prog", str(good)]) == 0
