"""Domain value objects for the familio.org projection.

These mirror the `dmalch/familio` provider's resource schema and render
themselves to HCL — the same self-rendering convention `GeniProfile` /
`GeniUnion` follow on the geni side. They hold data only; the DSL→familio
*mapping* policy lives in `projection.py`. Rendered output is single-space
`key = value`; column alignment is left to `terraform fmt` (run by the CLI).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def is_uuid(ref: str) -> bool:
    """True when `ref` is a bare familio person UUID (a parent that lives only on
    the familio tree, not a managed kin res_name)."""
    return bool(_UUID_RE.match(ref))


def _parent_ref(r: str) -> str:
    """A parent reference for the HCL `parents = [...]` list: a bare UUID literal
    for an unmanaged familio person, else a `familio_person.<res>.uuid` ref."""
    return f'"{r}"' if is_uuid(r) else f"familio_person.{r}.uuid"


def _heredoc(text: str) -> str:
    """Render a (possibly multi-line) free-text value as an indented-heredoc HCL
    expression, e.g. an event comment. Terraform template markers (`${`, `%{`)
    are escaped so names can't be misread as interpolation; `terraform fmt` (run
    by the CLI) tidies the indentation."""
    safe = text.replace("${", "$${").replace("%{", "%%{")
    body = "\n".join("    " + ln if ln else "" for ln in safe.split("\n"))
    return f"trimspace(<<-EOT\n{body}\n    EOT\n  )"


@dataclass(frozen=True)
class FamilioDate:
    """A familio complex-date block (provider v0.5+). `year` is required;
    `month`/`day` are optional. A date may additionally be approximate
    (`circa`) OR carry a `date_range` bound — `before` / `after` / `between` —
    but never both (familio rejects a range marked approximate). A `between`
    range carries its second endpoint via `end_year`/`end_month`/`end_day`
    (optionally `end_circa`). `calendar` is `gregorian` (the provider default,
    rendered only when set) or `julian` — our metric-book dates are Old Style."""

    year: int
    month: int | None = None
    day: int | None = None
    circa: bool = False
    date_range: str | None = None
    end_year: int | None = None
    end_month: int | None = None
    end_day: int | None = None
    end_circa: bool = False
    calendar: str | None = None

    def to_hcl(self) -> str:
        parts = [f"year = {self.year}"]
        if self.month is not None:
            parts.append(f"month = {self.month}")
        if self.day is not None:
            parts.append(f"day = {self.day}")
        if self.circa:
            parts.append("circa = true")
        if self.date_range:
            parts.append(f'range = "{self.date_range}"')
        if self.end_year is not None:
            parts.append(f"end_year = {self.end_year}")
        if self.end_month is not None:
            parts.append(f"end_month = {self.end_month}")
        if self.end_day is not None:
            parts.append(f"end_day = {self.end_day}")
        if self.end_circa:
            parts.append("end_circa = true")
        if self.calendar:
            parts.append(f'calendar = "{self.calendar}"')
        return "{ " + ", ".join(parts) + " }"


@dataclass(frozen=True)
class FamilioSource:
    """One «Источник» citation in a person's `sources` block. References a
    familio-catalogued entity by UUID: an archival `case` (дело), or a
    `catalog_person` index record (e.g. судимость `vss` / WWI `gwarmil`), which
    needs its `catalog_key`. The label/реквизиты are server-derived from the
    reference; only `comment` is a free note."""

    reference_uuid: str
    type: str                    # "case" | "catalog_person"
    catalog_key: str = ""        # required for catalog_person, omitted for case
    comment: str = ""

    def to_hcl(self) -> str:
        inner = [
            f'      reference_uuid = "{self.reference_uuid}"',
            f'      type           = "{self.type}"',
        ]
        if self.catalog_key:
            inner.append(f'      catalog_key    = "{self.catalog_key}"')
        if self.comment:
            inner.append(f"      comment        = {_heredoc(self.comment)}")
        return "    {\n" + "\n".join(inner) + "\n    }"


@dataclass
class FamilioPerson:
    """A `familio_person` resource. `gender` is the provider's only required
    field. `parents` holds the res_names (0–2) of the kin parents — rendered as
    `familio_person.<res>.uuid` references. `sources` lists the person's «Источники»
    citations. `uuid`, when set, drives a declarative `import {}` block so an
    already-existing familio person is adopted instead of duplicated."""

    res_name: str
    gender: str
    first_name: str = ""
    last_name: str = ""
    patronymic: str = ""
    birth_last_name: str = ""
    birth_date: FamilioDate | None = None
    death_date: FamilioDate | None = None
    christening_date: FamilioDate | None = None
    birth_comment: str = ""
    death_comment: str = ""
    christening_comment: str = ""
    biography: str = ""
    birth_place: str = ""          # HCL ref to the settlement UUID, e.g. local.settlement_*
    christening_place: str = ""
    death_place: str = ""          # familio's «Место смерти»; same local.settlement_* ref
    parents: tuple[str, ...] = ()
    sources: tuple[FamilioSource, ...] = ()
    uuid: str | None = None

    def _scalar_fields(self) -> list[tuple[str, str]]:
        out: list[tuple[str, str]] = [("gender", f'"{self.gender}"')]
        for key, val in (
            ("first_name", self.first_name),
            ("last_name", self.last_name),
            ("patronymic", self.patronymic),
            ("birth_last_name", self.birth_last_name),
        ):
            if val:
                out.append((key, f'"{val}"'))
        return out

    @staticmethod
    def _event_block(
        name: str,
        date: FamilioDate | None,
        place: str,
        comment: str,
        parents: tuple[str, ...] = (),
    ) -> str:
        """A nested life-event block `name = { date/place/comment/parents }`, or
        `""` when the event carries nothing. `place` is an HCL reference to the
        settlement UUID (a `local.settlement_*` ref), emitted unquoted. (provider
        ≥ 0.8.0 nests these under birth/death/christening.)"""
        inner: list[str] = []
        if date is not None:
            inner.append(f"    date = {date.to_hcl()}")
        if place:
            inner.append(f"    place = {place}")
        if comment:
            inner.append(f"    comment = {_heredoc(comment)}")
        if parents:
            refs = ", ".join(_parent_ref(r) for r in parents)
            inner.append(f"    parents = [{refs}]")
        if not inner:
            return ""
        return f"  {name} = {{\n" + "\n".join(inner) + "\n  }"

    def to_terraform(self) -> str:
        lines = [f"  {k} = {v}" for k, v in self._scalar_fields()]
        if self.biography:
            lines.append(f"  biography = {_heredoc(self.biography)}")
        for block in (
            self._event_block("birth", self.birth_date, self.birth_place,
                              self.birth_comment, self.parents),
            self._event_block("death", self.death_date, self.death_place,
                              self.death_comment),
            self._event_block("christening", self.christening_date,
                             self.christening_place, self.christening_comment),
        ):
            if block:
                lines.append(block)
        if self.sources:
            entries = ",\n".join(s.to_hcl() for s in self.sources)
            lines.append(f"  sources = [\n{entries},\n  ]")
        return (
            f'resource "familio_person" "{self.res_name}" {{\n'
            + "\n".join(lines)
            + "\n}\n\n"
        )

    def import_block(self) -> str:
        """The `import {}` block adopting an existing familio person, or `""`
        when this person is to be created fresh (no `uuid`)."""
        if not self.uuid:
            return ""
        return (
            "import {\n"
            f"  to = familio_person.{self.res_name}\n"
            f'  id = "{self.uuid}"\n'
            "}\n\n"
        )


@dataclass(frozen=True)
class FamilioMarriage:
    """A `familio_marriage` resource linking two kin partners. `marriage_date`
    is optional (omitted when the source union carries no dated marriage
    event)."""

    res_name: str
    partner_1: str
    partner_2: str
    marriage_date: FamilioDate | None = None
    comment: str = ""
    place: str = ""                # HCL ref to the settlement UUID, e.g. local.settlement_*

    def to_terraform(self) -> str:
        lines = [
            f'resource "familio_marriage" "{self.res_name}" {{',
            f"  partners = [familio_person.{self.partner_1}.uuid, "
            f"familio_person.{self.partner_2}.uuid]",
        ]
        if self.marriage_date is not None:
            lines.append(f"  marriage_date = {self.marriage_date.to_hcl()}")
        if self.place:
            lines.append(f"  place = {self.place}")
        if self.comment:
            lines.append(f"  comment = {_heredoc(self.comment)}")
        lines.append("}\n")
        return "\n".join(lines) + "\n"
