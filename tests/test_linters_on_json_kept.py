"""What a node wrote is read once a lint call (`walk.keeping_written`): every rule asks it of the same nodes."""
from __future__ import annotations

from typing import Any

from verso.ru.linters.on_json import walk


def test_what_a_node_wrote_is_kept_for_the_block_alone():
    """Inside the block a node's answer is kept — each caller given its own copy —, and nothing of it outlives the
    block: a node changed after it is read anew."""
    node: dict[str, Any] = {"written": {"comment": "одно"}}
    assert walk._kept_written.get() is None                       # pyright: ignore[reportPrivateUsage]
    with walk.keeping_written():
        first = walk.FileView.written("person", node)
        assert first == {"comment": "одно"}
        first["comment"] = "чужое"                                 # a caller's change reaches no other caller
        assert walk.FileView.written("person", node) == {"comment": "одно"}
        with walk.keeping_written():                               # a block inside keeps the outer one's
            assert walk.FileView.written("person", node) == {"comment": "одно"}
    assert walk._kept_written.get() is None                       # pyright: ignore[reportPrivateUsage]
    node["written"]["comment"] = "другое"
    assert walk.FileView.written("person", node) == {"comment": "другое"}


def test_a_node_read_as_two_classes_is_kept_as_each():
    """The answer is the node's read as one class: the same node asked as another is asked anew."""
    node: dict[str, Any] = {"written": {"comment": "одно"}}
    with walk.keeping_written():
        assert walk.FileView.written("person", node) == walk.FileView.written("member", node) == {"comment": "одно"}
        assert len(walk._kept_written.get() or {}) == 2           # pyright: ignore[reportPrivateUsage]
