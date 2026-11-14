"""What a Geni profile writes is content, not the interface: its locale keys are the
plugin's content profile, and no language of the interface moves a byte of it."""
from __future__ import annotations

import pytest

from verso.core import plugins
from verso.core.targets.geni.profile import GeniProfile


def _profile() -> GeniProfile:
    return GeniProfile(res_name="anna", gender="female", first_name="Анна", last_name="Петрова",
                       nicknames=["Аннушка"], about="Крещена в 1850 г.")


def test_ru_content_profile():
    assert plugins.content() == plugins.ContentProfile(native="ru", latin="en-US")


def test_geni_profile_is_the_same_in_every_language(monkeypatch: pytest.MonkeyPatch):
    texts = []
    for lang in ("en", "ru"):
        monkeypatch.setenv("VERSO_LANG", lang)
        texts.append(_profile().to_terraform())
    assert texts[0] == texts[1]
    assert '"ru" = {' in texts[0] and '"en-US" = {' in texts[0] and '"ru" = trimspace(' in texts[0]
