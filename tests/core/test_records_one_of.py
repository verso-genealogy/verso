"""A field that holds a value of one of several types (`OneOf`): the vocabulary names it `a|b`, the encoder writes a
value by the first type that takes it, the decoder reads it back by the first that does, the schema allows each —
the mechanism a plugin uses to move a field from one type to another while the old one is still read."""
from __future__ import annotations

import pytest

from verso.core.records import FormatError
from verso.core.records.decode import decode_value
from verso.core.records.encode import encode_value
from verso.core.records.fields import OneOf, parse_fields
from verso.core.records.schema import type_schema

pytestmark = pytest.mark.usefixtures("toy_workspace")

BOOL_OR_STR = OneOf(("bool", "str"))


def test_the_vocabulary_names_a_field_of_several_types_with_a_bar():
    (field,) = parse_fields("flag:bool|str", {})
    assert field.type == BOOL_OR_STR
    (field,) = parse_fields("count:int|str=''", {})
    assert (field.type, field.default) == (OneOf(("int", "str")), "")


@pytest.mark.parametrize("value", [True, False, "так в книге"])
def test_each_type_is_written_and_read_back_as_itself(value: object) -> None:
    written = encode_value(value, BOOL_OR_STR, "flag")
    assert written == value
    assert decode_value(written, BOOL_OR_STR, "flag") == value
    assert type(decode_value(written, BOOL_OR_STR, "flag")) is type(value)


def test_none_is_none_in_either_direction():
    assert encode_value(None, BOOL_OR_STR) is None and decode_value(None, BOOL_OR_STR) is None


def test_a_value_of_no_listed_type_is_refused_naming_them_all():
    with pytest.raises(FormatError, match=r"flag: int .*bool \| str"):
        encode_value(3, BOOL_OR_STR, "flag")
    with pytest.raises(FormatError, match="flag"):
        decode_value(3, BOOL_OR_STR, "flag")


def test_the_schema_allows_each_type_and_null():
    from jsonschema import Draft202012Validator
    schema = {"$defs": {}, **type_schema(BOOL_OR_STR)}
    check = Draft202012Validator(schema)
    assert all(check.is_valid(v) for v in (True, "x", None))
    assert not check.is_valid(3)


def test_the_decoder_names_the_types_as_the_encoder_does():
    with pytest.raises(FormatError) as refused:
        decode_value(3, BOOL_OR_STR, "flag")
    assert "bool | str" in str(refused.value) and "OneOf" not in str(refused.value)


def test_a_refusal_says_why_each_type_did_not_take_the_value():
    """A value of the right shape for one type, wrong inside — its cause, not only «none of them»."""
    from verso.core.records.fields import ListOf

    ints_or_text = OneOf((ListOf("int"), "str"))
    with pytest.raises(FormatError) as refused:
        decode_value([1, "два"], ints_or_text, "counts")
    assert "counts[1]" in str(refused.value)
    with pytest.raises(FormatError) as refused:
        encode_value([1, "два"], ints_or_text, "counts")
    assert "counts[1]" in str(refused.value)


def test_the_first_type_that_takes_a_value_is_the_one_it_is():
    """The order the vocabulary writes is the order tried: a text a member's code reads as is that member where
    the enum comes first, and stays a text where the text does."""
    from enum import Enum

    class Side(Enum):
        LEFT = "left"

    assert decode_value("left", OneOf((Side, "str")), "side") is Side.LEFT
    assert decode_value("left", OneOf(("str", Side)), "side") == "left"


def test_a_code_no_member_has_is_a_reason_and_the_next_type_is_tried():
    from enum import Enum

    class Side(Enum):
        LEFT = "left"

    assert decode_value("right", OneOf((Side, "str")), "side") == "right"
    with pytest.raises(FormatError) as refused:
        decode_value("right", OneOf((Side, "int")), "side")
    assert "right" in str(refused.value) and "left" in str(refused.value)
