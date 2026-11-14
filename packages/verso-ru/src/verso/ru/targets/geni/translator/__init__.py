"""DSL-to-Terraform translator package (split from tf_translator.py)."""
from verso.ru.targets.geni.translator.about_sections import _ABOUT_SECTION_HEADER, _DOC_ANCHOR, _SHORT_COMMENT_PATTERNS, _about_kind_priority, _extract_short_comment, _sort_about_sections
from verso.ru.targets.geni.translator.census_resolvers import _age_to_years, _resolve_arrival_reason, _resolve_arrival_year, _resolve_departure_reason, _resolve_departure_year, _resolve_destination, _resolve_parent_ref, _resolve_previous_age
from verso.ru.targets.geni.translator.comments import _comment_for_union, _comment_for_unions, _mk_doc_name_line, _name_in_document, _name_in_mk, _names_in_mk, _shallow_person_without_patr
from verso.ru.targets.geni.translator.consolidation import Consolidation
from verso.ru.targets.geni.translator.generator import TerraformGenerator
from verso.ru.targets.geni.translator.res_names import _build_subfamily_union_res_name, _location, _strip_last_name_token, generate_res_name_2
from verso.ru.targets.geni.translator.resources import CONSOLIDATED_PROFILES_CHUNK, GENDER_TF, _document_resource, _event
from verso.ru.targets.geni.translator.sorting import SORT_OVERRIDE, _chronological_key, _month_num

__all__ = [
    "CONSOLIDATED_PROFILES_CHUNK",
    "GENDER_TF",
    "SORT_OVERRIDE",
    "_ABOUT_SECTION_HEADER",
    "_DOC_ANCHOR",
    "_SHORT_COMMENT_PATTERNS",
    "Consolidation",
    "TerraformGenerator",
    "_about_kind_priority",
    "_age_to_years",
    "_build_subfamily_union_res_name",
    "_chronological_key",
    "_comment_for_union",
    "_comment_for_unions",
    "_document_resource",
    "_event",
    "_extract_short_comment",
    "_location",
    "_mk_doc_name_line",
    "_month_num",
    "_name_in_document",
    "_name_in_mk",
    "_names_in_mk",
    "_resolve_arrival_reason",
    "_resolve_arrival_year",
    "_resolve_departure_reason",
    "_resolve_departure_year",
    "_resolve_destination",
    "_resolve_parent_ref",
    "_resolve_previous_age",
    "_shallow_person_without_patr",
    "_sort_about_sections",
    "_strip_last_name_token",
    "generate_res_name_2",
]
