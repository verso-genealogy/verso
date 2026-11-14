# Contributing

```sh
pip install -e "packages/verso-core[schema]" -e "packages/verso-ru[xlsx,dsl-tools]"
python -m pytest tests                       # the library's tests
python -m pytest -p tests.core.block tests/core   # the core alone, with verso.ru blocked
ruff check . && pyright
python -m tools.reference --check            # the reference is current
```

- **A test with every change.** A behaviour change comes with the test that fails without it; a
  fix, with the test that reproduces the bug. The tests read only their fixtures — the synthetic
  corpus in `tests/fixtures/` — never a real one.
- **The DSL's facade, the records JSON, the commands, the workspace's keys, the linters' codes**
  are public ([compatibility](docs/compatibility.md)): changing one is a release note, and removing
  one goes through a deprecation.
- **Outputs that are addresses** — res_names, record ids — stay byte-stable; a change to how they
  are spelled is a new profile or a new rule, never an edit.
- **Messages** to the user — linter findings, errors — follow [the i18n rules](docs/i18n.md): English
  is the source (`locales/en.toml`), Russian a translation (`ru.toml`); content — the records' own
  words — is never translated. Code, comments and docs are in English.
- **How a change is checked.** `make premerge` runs every check. Byte-neutrality on a real corpus is
  checked by the maintainer at release. A PR that moves what a corpus produces (Terraform, CSV,
  records JSON, the ratchets' fingerprints) says so in its description.
