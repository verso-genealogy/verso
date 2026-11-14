"""The records export's code fingerprint reads the core and the enabled plugins' code."""
from __future__ import annotations

import pytest

from verso.core.pipeline import records


@pytest.mark.usefixtures("toy_workspace")
def test_the_fingerprint_reads_the_core_and_the_enabled_plugins():
    assert records.library() == ("verso.core", "tests.core")
    assert records.code_fingerprint() == records.code_fingerprint_of(("verso.core", "tests.core"))
    assert records.code_fingerprint_of(("verso.core",)) != records.code_fingerprint()
