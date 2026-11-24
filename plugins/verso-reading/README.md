# verso-reading — a Claude Code plugin

Skills and agents for reading handwritten Russian archival scans — metric books (метрические
книги), revision lists (ревизские сказки), confession lists (исповедные росписи), the 1917
farm-census cards — and writing what they say into the Verso DSL (`verso.ru.dsl`).

| Skill | What for |
|---|---|
| `verso-reading:metric-books` | a year of a metric book from a directory of its frames: check it is whole, find the parts, cut legible crops, read in two tiers |
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
the clergy), where the frames of each дело come from and where the record of each дело's
composition is kept, and the tools it has for its archives. The skills and agents read those from
there.

A project starting out has none of that yet. The toy example of the verso repository carries a sample of the
project's AGENTS.md (`examples/toy/AGENTS.md`, an invented village): its rules, its statuses and places, the
checks to ask after a year. A project with no extraction rules of its own writes by the library's rules of a
record — the guide of that name in the verso repository — and `dsl-writer` falls back on them, saying so.

The skills read a directory of a дело's frames, best named by folio (`<кадр>_<лист>[об]`), with
the library's `verso scans` and the other `verso …` commands. They need the library with Pillow:

```bash
pip install 'verso-core[scans]>=0.1.43' 'verso-ru>=0.1.43'
```

## What it costs

- **Always in context**: the descriptions of the five skills and two agents — about 4 thousand characters
  together. Nothing else of the plugin is read until a skill is used.
- **A skill, when used**: its text, once — `metric-books` about 26 thousand characters and `census` about 23 (each
  says its own size), the others 8–11 thousand. `dsl-writer`'s prompt is about 14 thousand, and it reads the
  project's rules itself; `scan-reader`'s about 2.
- **The two tiers of reading are two scales of crop**, not two passes of readers: a part crop finds a record, a
  4–5× cut reads each name that enters the DSL. Subagents are optional — a year can be read in the session itself.
  A subagent pays its own context before its first page: give one about ten records, not one or fifty.
- **Which model reads these hands how well, and at what price per record**, is measured in
  [an article](https://verso-genealogy.github.io/articles/en/models/).

A token is a few characters, fewer for Cyrillic: count with the model's tokenizer before budgeting by these.

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

An agent with `memory: project` keeps its memory in the project's agent-memory directory under its
plugin-scoped name, `verso-reading-<agent>` (Claude Code 2.1.311 made `verso-reading-dsl-writer`).

## Outside Claude Code

Other agents that read the Agent Skills format (Codex, Gemini CLI, GitHub Copilot, Cursor and others) take the skills — not
the agents, which are Claude Code's — through [skills.sh](https://skills.sh): `skills.sh.json` at the repository's
root points it at this plugin's `skills/`.

```bash
npx skills add verso-genealogy/verso@vX.Y.Z --skill metric-books -a codex
```

What changes there:

- **The skills go by their bare names** — `metric-books`, `census`, `transcription`, `names` — not by
  `verso-reading:<skill>`; each skill says so where it points at another. A skill installed alone
  works alone: the pointers are to other skills' advice, not to their files.
- **There are no agents.** Where a skill hands the reading to `verso-reading:scan-reader` or
  `verso-reading:dsl-writer`, it says what to give your harness's own subagent instead — the same
  brief: the crops listed, read-only, «?» for what does not read — or to read the crops yourself.
- **The library has to be there**: Python 3.14 or later and the `verso` command on PATH, from the
  `pip install` line above. Each skill's `compatibility` says what it needs.
- **The project's AGENTS.md is the skills' map**, and not every harness reads the project's AGENTS.md
  on its own: Claude Code reads `CLAUDE.md` instead when the directory or one above it holds one,
  and Gemini CLI reads `GEMINI.md`. Where it is not loaded, have the agent open the project's AGENTS.md
  before a skill's first step (or import it from the file the harness reads).
- **A bare name can meet a project's own skill** of the same name — a project may keep its own
  `names` or `census`, and a harness then shows both, or keeps whichever it finds first. Install
  ours under a directory of another name — copy `plugins/verso-reading/skills/census/` to
  `.agents/skills/verso-census/` and set `name: verso-census` in its frontmatter (the standard wants
  the two to agree) — or leave out the one the project already has.
