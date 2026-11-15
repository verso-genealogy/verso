"""The task of marking a leaf: where each record lies, not what it says.

The answer is the frame of every record (`box_2d`, `[ymin, xmin, ymax, xmax]` in thousandths of
the leaf), its number, its kind and whether it runs over a leaf's edge.
"""
from __future__ import annotations

from typing import Any

from verso.ru.reading.task import closed, prompt_text

MARK_LINE = "Найди на листе все записи и верни их рамки в JSON по схеме."
KINDS = ("birth", "marriage", "death")


def output_schema() -> dict[str, Any]:
    record = closed({
        "number": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        "kind": {"type": "string", "enum": list(KINDS)},
        "gender": {"anyOf": [{"type": "string", "enum": ["male", "female"]}, {"type": "null"}]},
        "box_2d": {"type": "array", "items": {"type": "integer"}, "minItems": 4, "maxItems": 4},
        "continues": {"type": "boolean"},
        "continued": {"type": "boolean"},
    })
    return closed({"records": {"type": "array", "items": record},
                   "doubtful": {"type": "array", "items": {"type": "string"}}})


def system_prompt() -> str:
    return prompt_text("marking.md").strip() + "\n"
