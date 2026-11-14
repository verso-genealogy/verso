"""verso.core.pipeline.config — one loader for a village's consolidation config, on toy villages."""
from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest

from verso.ru.pipeline.translate import translate_village
from verso.core.pipeline.config import CONFIG_FILE, load_config, village_config


def _village(root: Path, name: str, config: str | None) -> Path:
    """One birth (father, mother, child) and, when given, a consolidation config."""
    village = root / name
    (village / "1800").mkdir(parents=True)
    (village / "1800" / "test_births_1800.py").write_text(textwrap.dedent('''
        from calendar import Month
        from verso.ru.dsl import birth, birth_month, birth_records
        from verso.ru.dsl import Gender, person

        test_births_1800 = birth_records(
            "A", "1", "1", "1", "Тестовка", "N", 1800,
            *birth_month(Month.MARCH,
                birth(1, Gender.MALE, 10, 11,
                      child=person("Иван"),
                      father=person("Петр", "Сидоров"),
                      mother=person("Марья", "Петрова"))),
        )
    '''), encoding="utf-8")
    if config is not None:
        (village / CONFIG_FILE).write_text(config, encoding="utf-8")
    return village


def test_translating_two_villages_in_one_process_reads_each_ones_config(tmp_path: Path):
    a = _village(tmp_path, "А", 'profile_move_list = {"stub_a": "canon_a"}\n')
    b = _village(tmp_path, "Б", 'profile_move_list = {"stub_b": "canon_b"}\n')
    gen_a, _ = translate_village(a)
    gen_b, _ = translate_village(b)
    assert gen_a.consolidation.profile_move_list.get("stub_a") == "canon_a"
    assert gen_b.consolidation.profile_move_list.get("stub_b") == "canon_b"
    assert "stub_a" not in gen_b.consolidation.profile_move_list


def test_translating_one_village_twice_gives_the_same_tree(tmp_path: Path):
    a = _village(tmp_path, "А", 'profile_move_list = {"stub_a": "canon_a"}\n')
    first = list(translate_village(a)[0].iter_outputs())
    second = list(translate_village(a)[0].iter_outputs())
    assert first and first == second


def test_the_config_loader_leaves_sys_path_and_sys_modules_alone(tmp_path: Path):
    a = _village(tmp_path, "А", 'profile_move_list = {"stub_a": "canon_a"}\n')
    path_before = list(sys.path)
    village_config(a)
    translate_village(a)
    assert sys.path == path_before
    assert not [m for m in sys.modules if m.startswith("generate_config_names")]


def test_load_config_takes_any_path(tmp_path: Path):
    path = tmp_path / "x y" / "other.py"
    path.parent.mkdir()
    path.write_text("profile_move_list = {'s': 'c'}\n", encoding="utf-8")
    assert load_config(path).profile_move_list == {"s": "c"}


def test_village_config_is_none_without_the_file(tmp_path: Path):
    assert village_config(_village(tmp_path, "А", None)) is None


def test_load_config_names_what_is_missing(tmp_path: Path):
    with pytest.raises(FileNotFoundError, match=r"нет конфига консолидации: .*generate_config_names\.py"):
        load_config(tmp_path / CONFIG_FILE)


def test_a_config_that_is_no_python_file_is_refused_in_russian(tmp_path: Path):
    path = tmp_path / "generate_config_names.txt"
    path.write_text("x = 1\n", encoding="utf-8")
    with pytest.raises(ImportError, match=r"не загрузить конфиг консолидации: .*generate_config_names\.txt"):
        load_config(path)
