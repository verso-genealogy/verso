"""familio.org projection: a narrow, kin-only view of the translated genealogy.

The geni side (`verso.core.targets.geni`) publishes EVERY person in a village's metric
books to Geni. familio is a second, separate publishing target that receives
only the researcher's (and spouse's) blood relatives plus the spouses they
married. It reuses the geni translator's consolidated `GeniProfile` /
`GeniUnion` domain model (read via `TerraformGenerator.canonical_profiles()` /
`canonical_unions()`), filters it to a curated kin registry, and remaps it onto
the much narrower `dmalch/familio` provider schema.

Modules:
- `model`      — `FamilioPerson` / `FamilioMarriage` / `FamilioDate` value
                 objects that render themselves to HCL.
- `projection` — `project_kin(...)`: the DSL→familio mapping policy.
"""
