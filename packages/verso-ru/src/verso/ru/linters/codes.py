"""The linters' codes: which linter says which, and how its text writes the code.

A code is public (AGENTS.md «What is public»): a finding's identity, its key in the baseline, what
an IDE and Verso answer by. Each linter's codes are `LINTER_CODES`; the prefix a message's text
opens with is `PREFIX` — `bracket` («[CPL002] …»), `bare` («ESC001 …», as those linters always
wrote), `none` (the linters that wrote no code, and the parser's and the registry's own codes) —
so that a finding reads byte for byte as it did before the codes were structured. One prefix for
every code is a declared change of its own, after 0.1.0.
"""
from __future__ import annotations

from typing import Literal

Style = Literal["bracket", "bare", "none"]

LINTER_CODES: dict[str, tuple[str, ...]] = {
    "single_line_calls": ("SLC001", "SLC002", "SLC003", "SLC004", "SLC005"),
    "genders": ("GND001",),
    "names": ("NAM001", "NAM002", "NAM003", "NAM004", "NAM005"),
    "relationship_ref": ("REL001", "REL002"),
    "ages": ("AGE001", "AGE002"),
    "hidden_flag": ("HID001", "HID002"),
    "parent_member": ("PM001", "PM002"),
    "birth_redundancy": ("BRD001", "BRD002", "BRD003", "BRD004", "BRD005", "BRD006"),
    "deaths_residence": ("DRA001", "DRA002"),
    "deaths_relatives": ("DRL001",),
    "deaths_burial_date": ("DBD001", "DBD002"),
    "marriage_residence": ("MRA001",),
    "parent_status": ("PSA001", "PSA002", "PSA003", "PSA004"),
    "census_redundancy": ("CRD001", "CRD002", "CRD003", "CRD004", "CRD005", "CRD006"),
    "census_status_redundancy": ("CSR001",),
    "census_age": ("CAI001", "CAI002", "CAI003", "CAI004", "CAI005"),
    "census_member_lines": ("CML001",),
    "census_parent_link": tuple(f"CPL{n:03}" for n in range(1, 13)),
    "residence_title": ("RTV001", "RTV002"),
    "unmapped_location": ("ULC001",),
    "external_sources": ("ESC001", "ESC002", "ESC003", "ESC004"),
    "name_lists": ("NLC001",),
    "patronymic_form": ("PAF001",),
    "name_gender_agreement": ("NGA001", "NGA002"),
    "marital_status": ("MST001",),
    "status_redundancy": ("VSR001",),
    "status_orthography": ("SOR001",),
    "relative_attachment": ("RLA001", "RLA002", "RLA003"),
    "reviewed_redundancy": ("RVR001",),
    "retractions": ("RET001", "RET002", "RET003"),
    "witness_side": ("WSD001", "WSD002"),
    "witness_side_advisory": ("WSD003", "WSD004", "WSD005", "WSD006"),
    "civil_register": ("ZGS001", "ZGS002"),
    "civil_register_advisory": ("ZGS003", "ZGS004", "ZGS005"),
    "dsl_imports": ("IMP001",),
    "divorces": ("DVC001",),
    # Not a DSL check: the names layers' own (`checks/lexicon.py`), run over a layer's files.
    "lexicon": ("LEX001", "LEX002", "LEX003", "LEX004", "LEX005", "LEX006", "LEX007", "LEX008", "LEX009", "LEX010"),
}

# The parser's and the registry's own codes, any linter's: a file that does not parse, a check
# that crashed.
COMMON_CODES = ("SYN001", "SYN002", "LNT001")

_BARE = frozenset({"ESC001", "ESC002", "ESC003", "ESC004", "MST001", "PM001", "PM002"})
_NONE = frozenset({*LINTER_CODES["single_line_calls"], *LINTER_CODES["genders"], *LINTER_CODES["names"],
                   *LINTER_CODES["relationship_ref"], "AGE002", *LINTER_CODES["hidden_flag"],
                   *LINTER_CODES["birth_redundancy"], *LINTER_CODES["census_redundancy"],
                   *LINTER_CODES["census_status_redundancy"], *COMMON_CODES})

PREFIX: dict[str, Style] = {code: "bare" if code in _BARE else "none" if code in _NONE else "bracket"
                            for code in (*(c for codes in LINTER_CODES.values() for c in codes), *COMMON_CODES)}
