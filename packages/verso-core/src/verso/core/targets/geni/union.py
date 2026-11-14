from enum import Enum

from verso.core.targets.geni.event import GeniEvent


class UnionOrigin(Enum):
    """What the record a union was minted from says the union is.

    The translator knows this when it builds the union and nowhere else, so
    it says so on the union rather than leaving the union consolidation to
    read it back out of the res_name (which a record number such as «1а» or a
    missing one defeats). A union minted as anything not named here — a
    godparent's or a relative's, the groom's parents' — carries no origin.
    """

    BIRTH = "birth"                  # the newborn's parents, as the birth record names them
    MARRIAGE = "marriage"            # the groom and the bride
    DEATH = "death"                  # the deceased and the relative the burial names
    ROLL = "roll"                    # a family of a household roll, as the roll lists it
    ROLL_ANCESTOR = "roll-ancestor"  # a head's parents the roll implies — our reconstruction


def _ref(name: str | None) -> str:
    """Return the Terraform reference expression for a partner or child name.

    Three forms:
    - ``data.geni_profile.<x>`` → ``data.geni_profile.<x>.id,``  (data source)
    - ``profile-NNNN``          → ``"profile-NNNN",``             (raw Geni id)
    - ``<resource_name>``       → ``geni_profile.<resource_name>.id,``
    """
    if not name:
        return ""
    if name.startswith("data.geni_profile."):
        return f"{name}.id,"
    if "profile-" in name:
        return f'"{name}",'
    return f"geni_profile.{name}.id,"


class GeniUnion:
    def __init__(
            self,
            res_name: str = "",
            partner_1: str | None = None,
            partner_2: str | None = None,
            children: set[str] | None = None,
            partner_1_profile: str | None = None,
            partner_2_profile: str | None = None,
            children_profiles: set[str] | None = None,
            marriage: GeniEvent | None = None,
            foster_children: set[str] | None = None,
            origin: UnionOrigin | None = None,
    ):
        self.res_name = res_name  # type: ignore[assignment]  # routed through property setter
        self.partner_1 = partner_1
        self.partner_2 = partner_2
        self.children = children or set()
        # Non-biological children linked to this union with the Geni "foster"
        # relationship modifier (приёмыш). Disjoint from `children`; the provider
        # emits them into the union's `foster_children` set.
        self.foster_children = foster_children or set()
        self.partner_1_profile = partner_1_profile
        self.partner_2_profile = partner_2_profile
        self.children_profiles = children_profiles or set()
        self.marriage = marriage
        # Provenance for the union consolidation; never rendered.
        self.origin = origin

    @property
    def res_name(self) -> str:
        return self._res_name

    @res_name.setter
    def res_name(self, value: str) -> None:
        self._res_name = value

    def to_terraform(self) -> str:
        import textwrap

        p1 = _ref(self.partner_1)
        p2 = _ref(self.partner_2)
        return textwrap.dedent(f"""resource "geni_union" "{self.res_name}" {{
  partners = [{f'''
    {p1}''' if p1 else ''}{f'''
    {p2}''' if p2 else ''}
  ]{f'''
  children = [
    {chr(10).join(f'    {_ref(child)}' for child in sorted(self.children) if child).strip()}
  ]''' if self.children else ''}{f'''
  foster_children = [
    {chr(10).join(f'    {_ref(child)}' for child in sorted(self.foster_children) if child).strip()}
  ]''' if self.foster_children else ''}{f'''
  marriage = {self.marriage.to_terraform(indent="  ")}''' if self.marriage else ''}
}}

""")

    def __str__(self):
        return f"GeniUnion(res_name={self.res_name}, partner_1={self.partner_1}, partner_2={self.partner_2}, children={self.children})"
