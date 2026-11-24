"""The site's tests read the records v1 of the all-kinds fixture (`tests/records_fixture.py`): invented
people, shelfmarks and villages, every record kind once."""
from __future__ import annotations

from typing import Any

import pytest

from tests.records_fixture import namespace
from verso.core.records.encode import encode_namespace
from verso.core.records.ids import Ids
from verso.ru.site import model


@pytest.fixture(scope="module")
def file_node() -> dict[str, Any]:
    return encode_namespace(namespace(), village="Маниловка", file="1900/all.py", sha256="", ids=Ids())


@pytest.fixture(scope="module")
def site(file_node: dict[str, Any]) -> model.Site:
    return model.load([file_node], village="Маниловка")
