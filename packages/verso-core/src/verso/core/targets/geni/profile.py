from verso.core import plugins
from verso.core.targets.geni.about import strip_section_date_markers
from verso.core.targets.geni.event import GeniEvent


def _latin(name):
    """A name in Latin letters, as a person reads it — the enabled plugin's display transliteration (the res_names'
    one where it gives none); an empty name has nothing to spell and asks no plugin (a profile built without names
    needs none)."""
    return plugins.display_transliterator()(name) if name else name


class GeniProfile:
    def __init__(
            self,
            res_name: str = "",
            gender: str = "",
            first_name: str = "",
            middle_name: str = "",
            last_name: str = "",
            birth_last_name: str = "",
            nicknames: list[str] | None = None,
            title: str = "",
            alive: bool = False,
            public: bool = True,
            birth: GeniEvent | None = None,
            baptism: GeniEvent | None = None,
            death: GeniEvent | None = None,
            burial: GeniEvent | None = None,
            cause_of_death: str | None = None,
            current_residence: str | None = None,
            occupation: str | None = None,
            projects: list[str] | None = None,
            about: str = "",
            source_date: str | None = None,
            source_date_error: str | None = None,
            source: str | None = None,
            sources: list[str] | None = None,
    ):
        self.res_name = res_name
        self.gender = gender
        self.first_name = first_name
        self.middle_name = middle_name
        self.last_name = last_name
        self.birth_last_name = birth_last_name
        self.nicknames = nicknames or []
        self.title = title
        self.alive = alive
        self.public = public
        self.birth = birth if birth and (birth.date or birth.location) else None
        self.baptism = baptism or None
        self.death = death or None
        self.burial = burial or None
        self.cause_of_death = cause_of_death
        self.current_residence = current_residence
        self.occupation = occupation
        self.projects = projects or []
        self.about = about
        self.source_date = source_date
        # Reason the SOURCE's own dates for this person are inconsistent (a
        # christening the scribe dated before the birth, and the like). Carried
        # from the DSL record; never emitted to terraform. `verso date-order`
        # acknowledges such a profile instead of reporting a transcription that
        # is already faithful.
        self.source_date_error = source_date_error
        self.source = source
        self.sources = sources or []
        # Terraform lifecycle ignore_changes attribute names (e.g. ["projects"]).
        # Set by the translator from a consolidation hint; not a Geni field.
        self.lifecycle_ignore_changes: list[str] = []

    @property
    def first_name(self):
        return self._first_name

    @first_name.setter
    def first_name(self, new_value):
        self._first_name = new_value
        self.first_name_en = _latin(self.first_name)

    @property
    def middle_name(self):
        return self._middle_name

    @middle_name.setter
    def middle_name(self, new_value):
        self._middle_name = new_value
        self.middle_name_en = _latin(self.middle_name)

    @property
    def last_name(self):
        return self._last_name

    @last_name.setter
    def last_name(self, new_value):
        self._last_name = new_value
        self.last_name_en = _latin(self.last_name)

    @property
    def birth_last_name(self):
        return self._birth_last_name

    @birth_last_name.setter
    def birth_last_name(self, new_value):
        self._birth_last_name = new_value
        self.birth_last_name_en = _latin(self.birth_last_name)

    @property
    def nicknames(self):
        return self._nicknames

    @nicknames.setter
    def nicknames(self, new_value):
        self._nicknames = new_value or []
        self.nicknames_en = [_latin(nickname) for nickname in new_value]

    @property
    def full_name(self):
        # Returns the full name in the format "First Middle Last"
        surname = self.last_name or self.birth_last_name or ""
        return f"{self.first_name}{' ' + self.middle_name if self.middle_name else ''}{' ' + surname if surname else ''}".strip()

    def to_terraform(self) -> str:
        # Returns a Terraform resource block as a string
        import textwrap

        projects_str = "[" + ", ".join(self.projects) + "]" if self.projects else ""
        # The names' and the about's locale keys are the plugin's content profile, asked
        # only when there is something to key: a profile without either asks no plugin.
        keyed = self.first_name or self.middle_name or self.last_name or self.birth_last_name or self.about
        content = plugins.content() if keyed else plugins.ContentProfile(native="", latin="")
        # Normalize the about block to a uniform 8-space indent so it sits
        # cleanly inside the `trimspace(<<-EOT ...)` heredoc. Upstream merge /
        # append code (consolidation, memorial overrides) can leave some lines
        # flush at column 0; a single column-0 line drops the `<<-EOT` minimum
        # indent to 0, so Terraform strips nothing and every other line keeps a
        # stray 8-space prefix in the value Geni stores. Re-indenting every
        # non-empty line to exactly 8 spaces (blank lines stay empty, which
        # `<<-EOT` ignores) guarantees uniform output.
        about_body = "\n".join(
            f"        {ln.strip()}" if ln.strip() else ""
            for ln in strip_section_date_markers(self.about).split("\n")
        ) if self.about else ""
        return textwrap.dedent(f"""# geni_profile.{self.res_name} {self.full_name}
resource "geni_profile" "{self.res_name}" {{
  gender = "{self.gender}"
  alive  = {str(self.alive).lower()}
  public = {str(self.public).lower()}{f'''
  names = {{
    "{content.latin}" = {{{f'''
      first_name  = "{self.first_name_en}"''' if self.first_name_en else ''}{f'''
      middle_name = "{self.middle_name_en}"''' if self.middle_name_en else ''}{f'''
      last_name   = "{self.last_name_en}"''' if self.last_name_en else ''}{f'''
      birth_last_name = "{self.birth_last_name_en}"''' if self.birth_last_name_en else ''}{f'''
      nicknames   = [{', '.join(f'"{nickname}"' for nickname in self.nicknames_en)}]''' if self.nicknames_en else ''}
    }}
    "{content.native}" = {{{f'''
      first_name  = "{self.first_name}"''' if self.first_name else ''}{f'''
      middle_name = "{self.middle_name}"''' if self.middle_name else ''}{f'''
      last_name   = "{self.last_name}"''' if self.last_name else ''}{f'''
      birth_last_name = "{self.birth_last_name}"''' if self.birth_last_name else ''}{f'''
      nicknames   = [{', '.join(f'"{nickname}"' for nickname in self.nicknames)}]''' if self.nicknames else ''}
    }}
  }}''' if self.first_name or self.middle_name or self.last_name or self.birth_last_name else ''}{f'''
  current_residence = {{
{chr(10).join(f'    {ln.strip()}' if ln.strip() else '' for ln in self.current_residence.split(chr(10)))}
  }}''' if self.current_residence else ''}{f'''
  birth = {self.birth.to_terraform(indent="  ")}''' if self.birth else ''}{f'''
  baptism = {self.baptism.to_terraform(indent="  ")}''' if self.baptism else ''}{f'''
  death = {self.death.to_terraform(indent="  ")}''' if self.death else ''}{f'''
  burial = {self.burial.to_terraform(indent="  ")}''' if self.burial else ''}{f'''
  cause_of_death = "{self.cause_of_death}"''' if self.cause_of_death else ''}{f'''
  occupation = "{self.occupation}"''' if self.occupation else ''}{f'''
  projects = {projects_str}''' if projects_str else ''}{f'''
  about = {{
    "{content.native}" = trimspace(<<-EOT
{about_body}
        EOT
    )
  }}''' if self.about else ''}{f'''
  lifecycle {{
    ignore_changes = [{', '.join(self.lifecycle_ignore_changes)}]
  }}''' if self.lifecycle_ignore_changes else ''}
}}

""")

    def __str__(self):
        return f"GeniProfile({self.full_name})"
