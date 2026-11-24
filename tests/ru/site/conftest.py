"""The site's tests read the records v1 of the all-kinds fixture (`tests/records_fixture.py`): invented
people, shelfmarks and villages, every record kind once."""
from __future__ import annotations

import copy
from collections.abc import Callable
from typing import Any

import pytest

from tests.records_fixture import namespace
from verso.core.records import ui as ui_schema
from verso.core.records.encode import encode_namespace
from verso.core.records.ids import Ids
from verso.ru.site import model
from verso.ru.site.records import Ui
from verso.ru.site.shell import Context

VILLAGE = "Маниловка"
BIRTHS = "r1:Маниловка/47-9-755/1900/birth"
MARRIAGES = "r1:Маниловка/47-9-755/1900/marriage"
DEATHS = "r1:Хлестаковка/47-9-755/1913/death"
HOUSEHOLDS = "r1:Заманиловка/735-265-53;стр-80/1828/household"
LISTED = "r1:Горюхино/1978-5-9700/1917/listed"
WWI = "r1:Маниловка/card/wwi"


@pytest.fixture(scope="session")
def file_node() -> dict[str, Any]:
    return encode_namespace(namespace(), village=VILLAGE, file="1900/all.py", sha256="", ids=Ids())


@pytest.fixture(scope="session")
def site(file_node: dict[str, Any]) -> model.Site:
    return model.load([file_node], village=VILLAGE)


@pytest.fixture(scope="session")
def ui() -> Ui:
    return Ui(ui_schema.load_ui())


@pytest.fixture
def ctx() -> Context:
    return Context(title="Село Маниловка", lang="ru")


@pytest.fixture
def changed(file_node: dict[str, Any]) -> Callable[[Callable[[dict[str, Any]], None]], model.Site]:
    """The site of the fixture after `change` has rewritten a copy of its file node."""
    def build(change: Callable[[dict[str, Any]], None]) -> model.Site:
        node = copy.deepcopy(file_node)
        change(node)
        return model.load([node], village=VILLAGE)
    return build
