package com.genealogy.dsllint.lint

/**
 * Files the linters read as shared context but that are NOT themselves DSL record files
 * (so they never carry annotations). Editing one changes what `dsllint.py` reports for
 * *every* DSL file — e.g. adding a `Status` constant to `verso/ru/dsl/statuses.py` makes
 * `single_line_calls` newly suggest it in place of a matching string literal.
 *
 * The [DslLintAnnotator] only re-lints a file when *that* file changes, so a dependency
 * edit would otherwise leave open DSL files showing stale results until they are edited,
 * reopened, or the IDE restarts. [DslLintDependencyWatcher] watches these and forces a
 * re-lint of the open DSL files.
 *
 * Matched by exact base name (path-independent, like [com.genealogy.dsllint.DslFileDetector]),
 * so the IDE's temp-file linting and nested projects both work. Add another base name here
 * to have its edits trigger a re-lint too.
 *
 * Current entries — each is a vocabulary the linters load at import time, so adding or
 * renaming an entry in one changes what `dsllint.py` reports for every DSL file:
 * - `statuses.py` (`verso/ru/dsl/`, and the landlords' in `corpus/` since 0.1.0) — the `Status`
 *   constants. `single_line_calls` suggests them in place of matching string literals, and
 *   `parent_status` derives every сословие from their names.
 * - `places.toml` (`corpus/`) — the settlement table.
 *   `unmapped_location` (ULC001) flags a residence missing from it, so adding a settlement
 *   should clear the warning on every open record that mentions it.
 * - `causes_of_death.py` (`verso/ru/dsl/`) — the cause constants `single_line_calls` offers
 *   in place of a matching literal (with its replace-kwarg quick fix).
 * - `marital_status.py` (`verso/ru/dsl/`) — the семейное-положение vocabulary. `MST001`
 *   flags a literal that is NOT in it, so adding a value should clear the error.
 * - `estates.toml` (`corpus/`) — the corpus's landlords and parishes. RTV001/RTV002
 *   read them, so a landlord's village added there should clear the warning.
 *
 * NB base-name matching is deliberately loose: `marital_status.py` is both the domain
 * vocabulary above and the linter `verso/ru/linters/checks/marital_status.py`, so editing
 * either triggers a re-lint. That is harmless — editing a check also changes what it
 * reports — but keep it in mind when adding a name that collides with a module elsewhere.
 */
object DslLintDependencies {
    private val DEPENDENCY_BASE_NAMES = setOf(
        "statuses.py",
        "locations.py",
        "places.toml",
        "causes_of_death.py",
        "marital_status.py",
        "estates.toml",
    )

    fun isDependencyFile(pathOrName: String): Boolean {
        val baseName = pathOrName.substringAfterLast('/').substringAfterLast('\\')
        return baseName in DEPENDENCY_BASE_NAMES
    }
}
