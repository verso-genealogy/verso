<!-- Written by tools/reference.py from the code — do not edit; `make reference`. -->

# Commands

`verso <command> [args]` runs the command's module as a program; `verso --help` lists them. `--workspace DIR` names the workspace for that command.


## The core

| Command | Module | What it does |
|---|---|---|
| `verso records-schema` | `verso.core.records.schema` | records-v1.json — the JSON Schema of the records JSON, built from the field table. |
| `verso scans` | `verso.core.scans.cli` | The scan tools on frames already on disk, a directory of an album's images (`verso scans <subcommand>`). |
| `verso tools` | `verso.core.tools` | Where terraform and geni are: PATH first, then the workspace's `[tools] path`. |
| `verso ui-schema` | `verso.core.records.ui` | ui-v1.json — the review page's schema, built from the vocabulary and a plugin's hints. |
| `verso workspace` | `verso.core.workspace` | Where the corpus is: the one place the library finds its data. |

## Plugin `ru`

| Command | Module | What it does |
|---|---|---|
| `verso age-conflicts` | `verso.ru.consolidation.age_conflicts` | Flag a canonical parent whose age at a child's birth is implausible. |
| `verso all-persons` | `verso.ru.cli.all_persons` | Aggregates all persons from year-record files under a village directory into village.db. |
| `verso apply-converge` | `verso.ru.consolidation.apply_converge` | Drive a village's terraform tree to convergence: plan → gate → apply → repeat. |
| `verso audit-matches` | `verso.ru.consolidation.batches.audit_matches` | Pre-apply audit: surface Geni-side pending tree/record/smart matches that touch profiles managed by this Terraform project. |
| `verso audit-unions` | `verso.ru.consolidation.batches.audit_unions` | Pre-apply audit: for every union the plan wants to create, ask Geni whether the same couple already has a union there. |
| `verso candidates` | `verso.ru.consolidation.candidates` | Proactively find consolidation candidates — for the persons of one year's record type (`--tf-file terraform/geni/mk_1840_birth.tf`, or `--year 1840 --type birth`), or for the whole village (`--sweep`, `verso candidates --sweep`). |
| `verso canonicalize-legacy-tf` | `verso.ru.cli.canonicalize_legacy_tf` | Canonicalize legacy Terraform files to match translator output. |
| `verso conflict-capture` | `verso.ru.consolidation.conflict_capture` | Inspect Geni merge data-conflicts and preserve external contributors' data. |
| `verso date-order` | `verso.ru.consolidation.date_order` | Flag a canonical profile whose christening/death/burial is dated before an earlier life event — whole-tree analog of Geni's «Event occurred before birth date» inconsistency. |
| `verso dead-code` | `verso.ru.linters.dead_code` | Things declared and never read. |
| `verso death-age` | `verso.ru.consolidation.death_age` | Flag a death record whose stated age disagrees with a birth record of the same child in the same village. |
| `verso detector` | `verso.ru.consolidation.detector` | Detect duplicate Geni profiles in a terraform plan and suggest consolidation entries for `generate_config_names.py`. |
| `verso document-sync` | `verso.ru.consolidation.document_sync` | Apply pending geni_document changes the Geni OAuth API cannot manage. |
| `verso drift` | `verso.ru.consolidation.drift` | Categorize external Geni drift from a saved Terraform plan. |
| `verso dsl-surface` | `verso.ru.dsl.surface` | The DSL's surface — every name the facade and its catalogs give, written down. |
| `verso dsllint` | `verso.ru.linters.dsllint` | Unified DSL linter wrapper — runs all DSL linters and outputs unified JSON. |
| `verso echz` | `verso.ru.cli.echz` | Download scans from a КАИСА electronic reading room (ЭЧЗ). |
| `verso estate-conflicts` | `verso.ru.consolidation.estate_conflicts` | Flag a consolidated profile whose source records disagree about its ESTATE. |
| `verso export-csv` | `verso.ru.cli.export_csv` | `verso export-csv` — a village's CSVs, written from its DSL files. |
| `verso export-records` | `verso.ru.cli.export_records` | export-records: a village's record sets as records-v1 JSON. |
| `verso facts` | `verso.ru.cli.facts` | Extract assertions from a village's records and ask a rule about them. |
| `verso facts-snapshot` | `verso.ru.cli.facts_snapshot` | The findings snapshot — a ratchet on the checks that read the assertions. |
| `verso familio-spravochnik` | `verso.ru.cli.familio_spravochnik` | Assemble a Familio submission ``.xlsx`` справочник from a parish's records. |
| `verso fetch-record` | `verso.ru.cli.fetch_record` | Fetches a specific record from both the Google Sheet and CSV by key, displaying all fields side-by-side for easy comparison. |
| `verso find-person` | `verso.ru.cli.find_person` | Search village.db by name fragment, with optional year/type filters. |
| `verso fix-combined-name-patronymic` | `verso.ru.cli.fix_combined_name_patronymic` | Fix: split 'Name Patronymic' stored as one string into separate name_orig + patr_orig/patr_old fields. |
| `verso fix-ich-patronymics` | `verso.ru.cli.fix_ich_patronymics` | Fix: remove explicit modern-form patronymic from deceased/child when father is specified. |
| `verso generate-familio-tf` | `verso.ru.cli.generate_familio_tf` | Generate `familio_*.tf` for a village's blood-relatives. |
| `verso generate-tf` | `verso.ru.cli.generate_tf` | Generate terraform `.tf` files for a village from its DSL Python records. |
| `verso generate-timeline` | `verso.ru.cli.generate_timeline` | Render a village's blood-relatives as a genealogy timeline — one HTML page. |
| `verso import-sheets` | `verso.ru.importers.google_sheets` | Import a birth, marriage or death sheet of Google Sheets as a DSL year file (formats `familio-extended` and `familio-standard`). |
| `verso lint-config` | `verso.ru.consolidation.lint_config` | Static linter for a village's generate_config_names.py. |
| `verso lint-kin` | `verso.ru.familio.lint_kin` | Static linter for a village's ``familio_kin.py`` KIN registry. |
| `verso merge-plan` | `verso.ru.consolidation.merge_plan` | The Geni-side work a consolidation apply needs, read off a saved plan. |
| `verso migrate-statuses` | `verso.ru.cli.migrate_statuses` | Migrate DSL files to use statuses constants. |
| `verso moved-blocks` | `verso.ru.consolidation.moved_blocks` | Turn a plan's rename-induced destroy+create pairs into `moved {}` blocks. |
| `verso name-variants` | `verso.ru.consolidation.name_variants` | Flag a loose record whose SURNAME the canonical of that name already carries. |
| `verso names` | `verso.ru.cli.names` | Add, remove, check and explain a name in the names layers; `layer-diff` writes a layer from the old tables. |
| `verso names-csv` | `verso.ru.linters.names_csv` | Integrity check for `names.csv` itself — the table, not the DSL that reads it. |
| `verso reconcile` | `verso.ru.consolidation.reconcile` | Find the canonical a name-list entry or an external card is a duplicate of. |
| `verso remove-duplicates` | `verso.ru.cli.remove_duplicates` | Remove duplicate records from names.csv using smart deduplication. |
| `verso review-ratchet` | `verso.ru.cli.review_ratchet` | The review ratchet: `<village>/unreviewed_on_geni.tsv` (`verso.core.ratchet`). |
| `verso show-record` | `verso.ru.cli.show_record` | Show the original source record for a given village/year/type/record number. |
| `verso sibling-spacing` | `verso.ru.consolidation.sibling_spacing` | Flag two children of one couple born impossibly close together. |
| `verso site` | `verso.ru.cli.site` | site: a village's records as a static site — its books record by record, an index of the names, a search. |
| `verso split-couples` | `verso.ru.consolidation.split_couples` | Flag one couple spread over two or more unions held by DIFFERENT profiles. |
| `verso stale` | `verso.ru.cli.stale` | Fail when a GENERATED artifact is stale with respect to its DSL source. |
| `verso stale-claims` | `verso.ru.consolidation.stale_claims` | Flag a comment that calls a record the earliest one, when an earlier record of the same person is now in the corpus. |
| `verso stale-moved` | `verso.ru.consolidation.stale_moved` | SMB001 — consolidation entries whose `moved` / `removed` blocks no longer address anything in terraform state. |
| `verso stale-notes` | `verso.ru.notes.stale_notes` | Notes a proofread has made stale. |
| `verso stale-stubs` | `verso.ru.consolidation.stale_stubs` | CST001/CST002 — consolidation-config entries that name a record the DSL no longer produces. |
| `verso statuses-toml` | `verso.ru.cli.statuses_toml` | The workspace's corpus statuses as `statuses.toml`. |
| `verso strip-dead-overrides` | `verso.ru.consolidation.strip_dead_overrides` | Codemod: delete ROV001 dead `override` fields from a village config. |
| `verso svyatcy` | `verso.ru.cli.svyatcy` | The святцы: import the table, and ask it while reading a scan. |
| `verso translit` | `verso.ru.cli.translit` | Show, add, remove and check the transliteration's rules; move the corpus's old `transliteration.toml` into a layer. |
| `verso tree-conflicts` | `verso.ru.consolidation.tree_conflicts` | Triage Geni **tree conflicts** and wire their resolution back into the config. |
| `verso triage-unions` | `verso.ru.consolidation.triage_unions` | Triage the geni_union deletes/replaces in a consolidation plan. |
| `verso union-duplicates` | `verso.ru.consolidation.union_duplicates` | Flag two same-named people sitting inside ONE union — probably one person. |
| `verso upgrade-dsl` | `verso.ru.cli.upgrade_dsl` | `verso upgrade-dsl` — a village's DSL files from v0 to v1. |
| `verso validate-import` | `verso.ru.importers.validation` | Validates the google_sheets_importer.py pipeline end-to-end by comparing the final Familio CSV output against the source Google Sheet data. |
| `verso verify-batch` | `verso.ru.consolidation.batches.verify` | Verify that a saved terraform plan only mutates allowlisted fields. |
| `verso verify-plan` | `verso.ru.consolidation.verify_plan` | Pre-apply safety gate for a consolidation plan. |
