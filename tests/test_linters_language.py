"""The linters find the same whatever the interface speaks: the words they match a record
against are the sources', never the catalog's, so a finding's code, params, token and line under
English are those under Russian — only its message reads otherwise."""
from __future__ import annotations

import re
from typing import Any

from tests.test_linter_issue import _before, _issues
from verso.core import i18n

_TMP = re.compile(r"[^'\"]*verso-sample-[^/]+/")  # each run copies the sample into a directory of its own


def _neutral(rel: str) -> list[tuple[Any, ...]]:
    out: list[tuple[Any, ...]] = []
    for issue in _issues(rel):
        message = issue["message"]
        out.append((issue.get("line"), issue.get("linter"), getattr(message, "code", None),
                    _TMP.sub("", repr(getattr(message, "params", None))), getattr(message, "token", None)))
    return out


def test_linters_find_the_same_in_either_language():
    samples = sorted(_before())
    assert samples
    for rel in samples:
        with i18n.use("ru"):
            ru = _neutral(rel)
        with i18n.use("en"):
            en = _neutral(rel)
        assert en == ru, rel
