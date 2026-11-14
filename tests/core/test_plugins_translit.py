"""The two roles of a transliteration on toy plugins: the res_names' (`transliterator`) and the names a person reads
(`display_transliterator`) — the second falls back to the first where no plugin gives one."""
from __future__ import annotations

from pathlib import Path

import pytest

from tests.core.toy import TOY
from verso.core import plugins, workspace
from verso.core.plugins import Plugin, PluginError
from verso.core.targets.geni.profile import GeniProfile

SHOWN = Plugin(name="shown", package="tests.core", display_transliterate=lambda: str.title)
SHOWN2 = Plugin(name="shown2", package="tests.core", display_transliterate=lambda: str.swapcase)


def _root(path: Path, names: str) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    (path / "verso.toml").write_text(f"schema = 4\nplugins = [{names}]\n", encoding="utf-8")
    return path


def test_display_falls_back_to_address(tmp_path: Path):
    with plugins.adding(TOY, entry_points=False), workspace.use(_root(tmp_path, '"toy"')):
        assert plugins.display_transliterator()("анна") == "АННА"


def test_display_of_the_plugin_that_gives_one(tmp_path: Path):
    with plugins.adding(TOY, SHOWN, entry_points=False), workspace.use(_root(tmp_path, '"toy", "shown"')):
        assert plugins.transliterator()("анна") == "АННА"
        assert plugins.display_transliterator()("анна") == "Анна"


def test_two_display_transliterators_are_refused(tmp_path: Path):
    with plugins.adding(TOY, SHOWN, SHOWN2, entry_points=False), \
            workspace.use(_root(tmp_path, '"toy", "shown", "shown2"')), \
            pytest.raises(PluginError, match=r"two plugins give a display transliteration: shown, shown2 — keep one$"):
        plugins.display_transliterator()


def test_geni_profile_latin_is_display(tmp_path: Path):
    with plugins.adding(TOY, SHOWN, entry_points=False), workspace.use(_root(tmp_path, '"toy", "shown"')):
        profile = GeniProfile(res_name="x", first_name="анна", nicknames=["маша"])
        assert profile.first_name_en == "Анна"
        assert profile.nicknames_en == ["Маша"]


ELSEWHERE = Plugin(name="elsewhere", package="tests.core", display_transliterate=lambda: lambda name: "zz")


def test_consolidation_conflicts_reads_address(tmp_path: Path):
    """A dropped surname is matched against the consolidation key — a res_name, spelled by the address role."""
    from verso.core.targets.geni.consolidation_conflicts import _looks_like_birth_name  # pyright: ignore[reportPrivateUsage]
    with plugins.adding(TOY, ELSEWHERE, entry_points=False), workspace.use(_root(tmp_path, '"toy", "elsewhere"')):
        assert _looks_like_birth_name("анна", "x_анна_y")
