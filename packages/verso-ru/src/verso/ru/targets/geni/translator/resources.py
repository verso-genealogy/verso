"""Terraform resource literal emission helpers and constants."""
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    pass
from verso.ru.gender import Gender
from verso.core.targets.geni.date import GeniDate
from verso.core.targets.geni.event import GeniEvent



GENDER_TF = {Gender.MALE: "male", Gender.FEMALE: "female"}


CONSOLIDATED_PROFILES_CHUNK = 400



def _event(day, month, year, location, circa=False):
    """Construct a GeniEvent; returns None if nothing meaningful to emit."""
    if not any([day, month, year, location]):
        return None
    date = GeniDate(day=day, month=month, year=year, circa=circa) if (day or month or year) else None
    return GeniEvent(date=date, location=location)



def _document_resource(*, res_name, title, description, text, date_day, date_month,
                       date_year, labels, location, profiles, projects,
                       source_url=None, content_type=None, file=None, file_name=None):
    """Render a minimal `geni_document` terraform resource block.

    `source_url` (an external page Geni snapshots to a PDF proof) and
    `content_type` are optional; when set they emit the corresponding
    attributes. All metric-book/census callers omit them.

    `file` re-hosts an actual scan: it is a path **relative to the village
    terraform module**, read at plan time via `filebase64("${path.module}/…")`
    and uploaded as the document body (with `file_name` + `content_type`). It is
    mutually exclusive with `source_url` and `text` on the provider
    (ExactlyOneOf), so when `file` is set neither of those is emitted.
    """
    date_lines = []
    if date_day:
        date_lines.append(f"    day   = {date_day}")
    if date_month:
        date_lines.append(f"    month = {date_month}")
    if date_year:
        date_lines.append(f"    year  = {date_year}")
    date_block = "\n".join(date_lines)

    labels_block = "\n".join(f'    "{label}",' for label in labels)
    profiles_block = "\n".join(f"    geni_profile.{p}.id," for p in profiles)
    location_block = ""
    if location:
        # Strip the places' per-line indent (corpus/places.toml, `render_body`) before re-indenting
        # at the document's depth (4 spaces inside a 2-space-key block).
        loc_lines = [ln.strip() for ln in location.split("\n")]
        loc_body = "\n".join(f"    {ln}" if ln else "" for ln in loc_lines)
        location_block = f"\n  location = {{\n{loc_body}\n  }}"
    projects_block = ""
    if projects:
        projects_block = f"\n  projects = [{', '.join(projects)}]"
    source_block = ""
    if file:
        # Re-hosted scan: file + file_name + content_type. `file` is the path
        # relative to the village terraform module, read at plan time.
        # `filebase64(...)` is a TF expression, so it is emitted unquoted.
        if content_type:
            source_block += f'  content_type = "{content_type}"\n'
        if file_name:
            source_block += f'  file_name    = "{file_name}"\n'
        source_block += f'  file         = filebase64("${{path.module}}/{file}")\n'
    else:
        if content_type:
            source_block += f'  content_type = "{content_type}"\n'
        if source_url:
            source_block += f'  source_url   = "{source_url}"\n'
    # `text`, `file` and `source_url` are mutually exclusive on the provider
    # (ExactlyOneOf). Only emit the `text` heredoc when there is body text and
    # no file upload — a source_url/file document carries its content in
    # `description` + the URL/scan.
    text_block = f'  text        = <<-EOT\n{text}\n    EOT\n' if text and not file else ""
    # Omit the `date` block entirely when no date parts are known (e.g. an
    # undated external-source record) — an empty `date = {}` is noise.
    date_attr = f'  date = {{\n{date_block}\n  }}\n' if date_block else ""

    return (
        f'resource "geni_document" "{res_name}" {{\n'
        f'  title       = "{title}"\n'
        f'{source_block}'
        f'  description = <<-EOT\n{description}\n    EOT\n'
        f'{text_block}'
        f'{date_attr}'
        f'  labels = [\n{labels_block}\n  ]'
        f'{location_block}\n'
        f'  profiles = [\n{profiles_block}\n  ]'
        f'{projects_block}\n'
        f'}}\n\n'
    )
