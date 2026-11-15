# verso-reading — a Claude Code plugin

Skills and agents for reading handwritten Russian archival scans — metric books (метрические
книги), revision lists (ревизские сказки), confession lists (исповедные росписи), the 1917
farm-census cards — and writing what they say into the Verso DSL (`verso.ru.dsl`).

| Skill | What for |
|---|---|
| `verso-reading:metric-books` | a year of a metric book: export the album, check it is whole, find the parts, cut legible crops, read in two tiers |
| `verso-reading:census` | find a family in a revision or confession list by its age fingerprint, then write the households |
| `verso-reading:agri-census-1917` | the 1917 household cards: the bottom-up table, the relationship codes, the DSL shape |
| `verso-reading:transcription` | the legacy transcribe-first route: a reviewable `.txt` of a page |
| `verso-reading:names` | the names lexicon: the base, a corpus's layers, the lint findings on names |

| Agent | What for |
|---|---|
| `verso-reading:dsl-writer` | a page scan (or a validated transcription) → a DSL file |
| `verso-reading:scan-reader` | a lean reader: reads the crops a brief names and writes what it asks — a sweep's findings, a list of readings, a `.txt` for a person to check |

## What the plugin leaves to the project

Nothing here knows a corpus. Альбомы, архивы и региональные правила — в AGENTS.md проекта: the
project that uses the plugin says, in the project's AGENTS.md, where its extraction rules are (the
general set and one per record kind), its regional notes per village (surnames, estates, places,
the clergy), which Photos album holds which дело, where the record of each дело's composition is
kept, and the tools it has for its archives. The skills and agents read those from there.

Scripts, each in its skill's `scripts/` (`skills/*/scripts/`), need only Python and Pillow. `verso-scans`, which the scan skills call,
is a command of verso-app (the Verso review app); the `verso …` commands are this library's.

## Installing

The repository is a Claude Code marketplace named `verso` (`.claude-plugin/marketplace.json` at
its root) with this one plugin:

```text
/plugin marketplace add verso-genealogy/verso
/plugin install verso-reading@verso
```

A project that pins the library to a tag can name the same tag for the marketplace, so the skills
match the library it runs — in its project settings of Claude Code:

```json
{
  "extraKnownMarketplaces": {
    "verso": {"source": {"source": "github", "repo": "verso-genealogy/verso", "ref": "vX.Y.Z"}}
  },
  "enabledPlugins": {"verso-reading@verso": true}
}
```

The plugin carries no `version`: Claude Code versions it by the commit it was installed from, so
moving the tag moves the plugin.

Other agents that read the Agent Skills format (Codex, Gemini CLI, GitHub Copilot, Cursor and others) take the skills — not
the agents, which are Claude Code's — through [skills.sh](https://skills.sh): `skills.sh.json` at the repository's
root points it at this plugin's `skills/`.

```bash
npx skills add verso-genealogy/verso@vX.Y.Z --skill metric-books -a codex
```

An agent with `memory: project` keeps its memory in the project's agent-memory directory under its
plugin-scoped name (`verso-reading-<agent>`).
