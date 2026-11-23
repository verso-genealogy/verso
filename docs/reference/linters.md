<!-- Written by tools/reference.py from the code — do not edit; `make reference`. -->

# Linters

`dsllint` runs every check over DSL files (`--json` for tools). A code is hard (fails at once) or advisory (held by the baseline ratchet).

`dsllint --json` prints, per file and linter, its findings: `level`, `line`, `message`, then `code`, `params` (what the DSL wrote; a part said in words is `{key, params}`) and `token` (what the finding is about, or `null`), then `col`/`end_col` and `fix` where the check has them. A finding is its code and params, in no language; its message is the catalog's text in the interface's language.

The baseline ratchet (`dsllint --baseline FILE`) keeps a row per advisory finding: `CODE <tab> KEY <tab> FILE <tab> excerpt`, `KEY = sha256(file, code, params as JSON with sorted keys, nth)[:16]` — `nth` its occurrence among identical ones — under the line `# baseline v2`; only CODE and KEY are matched. A file without that line (v1, keyed by the message) is refused, and `--update-baseline` writes it anew.

| Module | Codes | What it checks |
|---|---|---|
| `ages` | AGE001, AGE002 | AST-based linter to validate `age`, `groom_age`, and `bride_age` literals on `death(...)` and `marriage(...)` DSL calls (and a card's `age=`), written as keywords or in their positional places. |
| `birth_redundancy` | BRD001, BRD002, BRD003, BRD004, BRD005, BRD006 | AST-based linter that flags redundant surname *and* residence kwargs on a `birth()` record's `mother` / `child` when the generator would auto-derive the identical value. |
| `census_age` | CAI001, CAI002, CAI003, CAI004, CAI005 | AST-based linters (CAI001–CAI005) that WARN on internally inconsistent census `member(...)` age data. |
| `census_member_lines` | CML001 | AST-based linter (CML001) requiring every `member()` in a census record to start its own line. |
| `census_parent_link` | CPL001, CPL002, CPL003, CPL004, CPL005, CPL006, CPL007, CPL008, CPL009, CPL010, CPL011, CPL012 | AST-based linters (CPL001-CPL012) that WARN on census members whose parent/spouse link is silently lost — or silently invented — in the generated tree. |
| `census_redundancy` | CRD001, CRD002, CRD003, CRD004, CRD005, CRD006 | CRD001 — AST linter that flags redundant surname / patronymic arguments on a census `member()`'s `person()` when `CensusHousehold.__init__` would auto-derive the identical value from the household head / husband / father. |
| `census_status_redundancy` | CSR001 | CSR001 — AST linter that flags a redundant explicit ``status=`` on a census ``member()``'s ``person()`` when the enclosing ``census_records(..., defaults=RecordDefaults(...))`` would apply the identical status by default. |
| `civil_register` | ZGS001, ZGS002, ZGS003, ZGS004, ZGS005 | AST-based linter (ZGS001–ZGS005) for a book of the civil registry — `civil=True`. |
| `deaths_burial_date` | DBD001, DBD002 | AST-based linter for the two dates of a `death()` record: death and burial. |
| `deaths_relatives` | DRL001 | AST-based linter guarding the ONE-relative limit of `death()` records. |
| `deaths_residence` | DRA001, DRA002 | AST-based linter that checks residence alignment between the deceased and the relative(s) named in a `death()` record. |
| `dsl_imports` | IMP001 | IMP001 — a DSL file imports the DSL's facade and nothing else (DSL v1). |
| `external_sources` | ESC001, ESC002, ESC003, ESC004 | AST-based linter for external-source DSL records (`criminal_record()` / `wwi_record()` / `wwii_record()` from verso.ru.dsl). |
| `file_bindings` | — | What a DSL file binds at its top level, for the checks that follow a name. |
| `genders` | GND001 | AST-based linter to check gender-role constraints in genealogy DSL records. |
| `hidden_flag` | HID001, HID002 | AST-based linter that flags the legacy implicit `hidden` sentinels on census `member()` / `CensusMember(...)` calls. |
| `lexicon` | LEX001, LEX002, LEX003, LEX004, LEX005, LEX006, LEX007, LEX008, LEX009, LEX010 | The names layers' own check, not a DSL one — a layer's three TSV files read in the sum of the layers under it. |
| `marital_status` | MST001 | AST-based linter (MST001) for the `marital_status=` (семейное положение) field on census members and WWI/WWII external-source records. |
| `marriage_residence` | MRA001 | AST-based linter (MRA001) for residence alignment inside a marriage record. |
| `name_gender_agreement` | NGA001, NGA002 | AST-based advisory linter (NGA001, NGA002): a person's surname or patronymic in the other gender's form. |
| `name_lists` | NLC001 | AST linter for name-list DSL records (`name_list_records()` / `listed_person()` from verso.ru.dsl). |
| `names` | NAM001, NAM002, NAM003, NAM004, NAM005 | Lint script to check first names and patronymics in person() calls. |
| `newborn_status` | — | Which written parent status a newborn's сословие rests on. |
| `parent_member` | PM001, PM002 | AST-based linter for `parent_member` misuse on census `member()` / `CensusMember(...)` calls. |
| `parent_status` | PSA001, PSA002, PSA003, PSA004 | AST-based linter (PSA001–PSA003) checking that a parent and their child share one сословие across birth, marriage and death records. |
| `patronymic_form` | PAF001 | AST-based advisory linter (PAF001) for the *form* of a patronymic vs. |
| `relationship_ref` | REL001, REL002 | AST-based linter to validate `relationship_ref` strings on `relative()` calls inside DSL records (birth/marriage/death) against a fixed allowlist. |
| `relative_attachment` | RLA001, RLA002, RLA003 | RLA001–RLA003 — AST linter for how a ``relative()`` attaches to its subject inside a birth / marriage / death record. |
| `residence_title` | RTV001, RTV002 | AST-based linter: a person's status against the village they live in. |
| `retractions` | RET001, RET002, RET003 | AST-based linter (RET001–RET003) for an age retraction that retracts nothing. |
| `reviewed_redundancy` | RVR001 | RVR001 — a ``reviewed=`` that restates the value it would already inherit. |
| `shared_ast` | — | One parse and one walk of a DSL file, shared by every check that reads it. |
| `single_line_calls` | SLC001, SLC002, SLC003, SLC004, SLC005 | Lint script to check that person() calls are on a single line, and that known status string constants are used instead of inline literals. |
| `status_orthography` | SOR001 | AST-based linter (SOR001): a classification field in pre-reform orthography. |
| `status_redundancy` | VSR001 | VSR001 — AST linter that flags a redundant explicit ``status=`` on a person in a VITAL record (birth / marriage / death) when the enclosing ``*_records(..., defaults=RecordDefaults(...))`` would apply the identical status by default — written in the call, or bound by name at the top of the file (``defaults=DEFAULTS``, as every Глуповы Горы book does). |
| `status_words` | — | What a `status=` says, and how a finding names the person it is about. |
| `translit` | — | The layers' linter over a layer's transliteration rules (`translit.tsv`, `verso.ru.naming.translit_layers`). |
| `unmapped_location` | ULC001 | AST-based linter (ULC001) that WARNS when a DSL record names a place that is not among the corpus's places (`corpus/places.toml`, `verso.core.places`). |
| `witness_side` | WSD001, WSD002, WSD003, WSD004, WSD005, WSD006 | AST-based linter (WSD001–WSD006) for the side a wedding's поручитель stood for. |

Any linter: SYN001, SYN002, LNT001 — a file that does not parse (`SyntaxError`, `parse error`), a check that crashed.
