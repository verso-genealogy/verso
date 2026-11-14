# intellij-dsllint

IntelliJ Platform plugin (PyCharm, IDEA + Python plugin) that brings the
genealogy DSL linter (`dsllint.py`) inline into JetBrains IDEs. Sibling of
`vscode-dsllint/` — same backend, same UX.

## What it does

- **Linting.** Shells out to `dsllint.py --json <file>` whenever you edit a DSL
  file (`<village>_<type>_<year>.py` for births / marriages / deaths / divorces
  / census / confessions / external_sources / name_lists). Issues from all 25
  linters surface as red/yellow squiggles with the
  message prefixed by the linter name, e.g. `[single_line_calls] redundant ...`.
  Open DSL files are also re-linted automatically when a linter *dependency*
  (`lib/packages/verso-ru/src/verso/ru/domain/statuses.py`) is edited — so a newly-added `Status` constant
  starts being suggested without reopening files or restarting the IDE
  (`DslLintDependencyWatcher`).
- **Quick fixes.** Alt-Enter on an issue:
  - **Replace with `<CONST>`** — swaps a string literal for the canonical status
    constant (`"мещанин"` → `MESHCHANIN`).
  - **Remove redundant `<kwarg>`** — deletes a kwarg already covered by
    `RecordDefaults`, with smart comma handling.
- **Syntax highlighting.** DSL function calls (`person`, `birth`, `marriage`,
  `name_list_records`, `listed_person`, …), `Gender.MALE` / `Gender.FEMALE`, `Month.<NAME>`, and uppercase status
  constants get distinct text-attribute keys so themes can color them
  consistently with `vscode-dsllint`'s TextMate grammar.
- **Commands.** `Tools → DSL Lint → Lint Current DSL File` and
  `Lint All DSL Files`.
- **Settings.** `Settings → Tools → DSL Lint` exposes `Python interpreter`,
  `Lint on open`, and `Lint on save` (mirrors the VS Code config).

## Build & install (local)

```bash
cd lib/ide/intellij-dsllint
make build                  # ./gradlew buildPlugin -> build/distributions/*.zip
make install                # prints ZIP path + install instructions
```

Then in your IDE: `Settings → Plugins → gear → Install Plugin from Disk…` and
pick the built ZIP. Restart the IDE.

For a sandboxed dev run (no install required):

```bash
make runIde                 # ./gradlew runIde
```

## Run tests

```bash
make test
```

The unit-test suite (DSL file detection, kwarg range finder, JSON parser) is a
direct port of the mocha tests in `lib/ide/vscode-dsllint/src/test/`.

## How it wires together

| VS Code piece | IntelliJ counterpart |
|---|---|
| `src/fileDetection.ts` | `DslFileDetector` (same regex) |
| `src/linter.ts` | `lint/DslLintRunner` (`GeneralCommandLine` + 30 s timeout) |
| `src/diagnostics.ts` | `lint/DslLintModels` + `lint/DslLintParser` |
| `src/extension.ts` lint pipeline | `lint/DslLintAnnotator` (`ExternalAnnotator`) |
| `src/quickfix.ts` + `src/quickfixUtils.ts` | `quickfix/*Fix` + `quickfix/KwargRangeFinder` |
| `syntaxes/*.tmLanguage.json` | `highlight/DslSyntaxAnnotator` + `highlight/DslTextAttributes` |
| `dsllint.lint` / `dsllint.lintAll` commands | `actions/LintCurrentFileAction` / `actions/LintAllAction` |
| `dsllint.*` configuration | `settings/DslLintSettings` + `settings/DslLintConfigurable` |

The `dsllint.py` script itself is unchanged — the plugin is just another host
for the same JSON protocol.

## Requirements

- IntelliJ Platform 2025.3+ (build 253+) — compiled against PyCharm 2025.3 and
  checked by the Plugin Verifier up to 2026.3 EAP (`pluginVerifyVersions` in
  `gradle.properties`; `make verify`, or `make verify ide=<path to an installed IDE>`)
- Python plugin (bundled in PyCharm; install in IDEA / GoLand)
- `python3` on PATH (override in settings if needed)
- `dsllint.py` in the project root (auto-discovered by walking parent dirs)
- **For building:** any JDK 21+ on PATH, e.g. the JBR inside an installed IDE
  (`JAVA_HOME=~/Applications/GoLand.app/Contents/jbr/Contents/Home`). The plugin
  targets bytecode 21 via `jvmToolchain(21)`, which Gradle auto-downloads through
  the foojay toolchain resolver. Bytecode 21 is also what keeps 2025.3 (JBR 21)
  loading it; 2026.3 runs on JBR 25 and loads it just the same.
