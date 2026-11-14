# Verso DSL Linter

VS Code extension that provides inline linting, quick fixes, and syntax highlighting for genealogy DSL Python files (birth/marriage/death records).

## Features

### Linting

Runs 25 Python AST-based linters on DSL files — births, marriages, deaths, divorces,
census/confessions, external sources and name lists (`*_births_*.py`, `*_census_*.py`,
`*_name_lists_*.py`, …). Highlights of the set:

- **single_line_calls** — `person()` calls must be on a single line; string literals should use status constants; redundant defaults detection
- **genders** — validates gender-role constraints (father=MALE, mother=FEMALE, groom=MALE, bride=FEMALE, etc.)
- **names** — validates first names and patronymics against known Russian historical names; checks gender-status consistency

Diagnostics appear inline on save and on open, prefixed with the linter name (e.g. `[single_line_calls] use constant MESHCHANIN...`).

### Quick Fixes

Two error types support auto-fix via the lightbulb menu (Ctrl+.):

| Error | Quick Fix |
|-------|-----------|
| `use constant MESHCHANIN instead of string literal status="мещанин"` | Replace `"мещанин"` with `MESHCHANIN` |
| `redundant residence="Заманиловка" (already in RecordDefaults)` | Remove the redundant kwarg |

### Syntax Highlighting

TextMate injection grammar adds highlighting on top of standard Python for:

- DSL functions: `person`, `birth`, `death`, `marriage`, `page`, `book`, `birth_month`,
  `birth_records`, `name_list_records`, `listed_person`, etc.
- Enums: `Gender.MALE`, `Gender.FEMALE`, `Month.JANUARY`, etc.
- Status constants: `ECON_PEASANT_MALE`, `MESHCHANIN`, etc.

## Installation

```bash
cd lib/ide/vscode-dsllint
make link
# Restart VS Code
```

## Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| `dsllint.pythonPath` | `python3` | Path to Python interpreter |
| `dsllint.lintOnSave` | `true` | Lint automatically on file save |
| `dsllint.lintOnOpen` | `true` | Lint automatically when opening a file |

## Commands

- **DSL Lint: Run Linter on Current File** — manually lint the active file
- **DSL Lint: Run Linter on All DSL Files in Workspace** — lint all DSL files

## Architecture

The extension spawns `dsllint.py` (project root) which runs all three Python linters in a single process and outputs unified JSON to stdout. The TypeScript extension parses this JSON and maps issues to VS Code diagnostics.

```
dsllint.py --json <file.py>
  └── check_single_line_calls.Checker (with fix metadata)
  └── check_genders.check_file()
  └── check_names.check_file()
```

## Development

```bash
cd lib/ide/vscode-dsllint
make install    # npm install
make compile    # tsc
make test       # mocha tests
make link       # symlink to ~/.vscode/extensions/
```

Python wrapper tests:
```bash
python3 test_dsllint.py
```
