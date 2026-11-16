---
name: transcription
description: Transcribe handwritten historical documents (metric books, census records) into a .txt file. Use when the user explicitly wants a transcription artefact — digitising a whole year, a reviewable text a second person can check, or shared source text. Writing the DSL straight from the scan is the project default and needs no transcription; this skill is the legacy transcribe-first route.
compatibility: >
  Needs an agent that can open local image files; the quadrant crops need Python 3.14+ and
  verso-core[scans]>=0.1.41 on PATH.
---

Perform character-by-character transcription of handwritten historical documents, particularly Russian Imperial-era
metric books and census records from the 18th-19th centuries.

> **This is the legacy route.** The default is to write the DSL straight from the scan,
> for every record type (the `verso-reading:dsl-writer` agent of the Claude Code plugin; elsewhere,
> by the project's extraction rules). Transcribe to
> `.txt` first when the text file itself has value: whole-year digitisation feeding several
> extraction passes, an artefact reviewable without re-running vision, or source text shared
> between people. For a targeted lookup in a revision list, use the `census` skill instead
> (`verso-reading:census` in the Claude Code plugin). The reading technique below applies either way.

## IMPORTANT: Transcribe Directly (your own vision, no external API)

Read the images **yourself**, with your own vision, opening each image file as your harness lets
you. Do NOT delegate to an external transcription API.

### Workflow

When the user requests transcription:

1. **Verify requirements** (STOP and request if missing):
   - Image file path(s) provided
   - Regional context file identified — the AGENTS.md проекта names it for each village; read it before
     transcribing

2. **Check scan resolution** (critical):

   ```bash
   python3 -c "import sys; from PIL import Image; print(Image.open(sys.argv[1]).size)" <image>
   ```

   If the scan is low-resolution relative to its content (rule of thumb: a **two-page spread under ~2500px wide**, or
   any scan where the handwriting is only a few pixels tall), the cursive will NOT be legible from the whole-page
   image. Generate upscaled quadrant crops first:

   ```bash
   verso scans quadrants <image> [<image> ...] --out <scratchpad>/crops    # pip install 'verso-core[scans]>=0.1.41'
   ```

   This writes four overlapping crops per image (`N_tl/N_tr/N_bl/N_br` = left/right page × top/bottom, 3x LANCZOS
   upscale + unsharp mask). Upscaling adds no information but makes small glyphs readable to the vision model.

3. **Transcribe (two-pass, per image)**:
   - **Layout pass**: Read the whole page image — table structure, number of records, record numbers, row boundaries.
   - **Text pass**: Read ALL four crops and transcribe cell contents from them (left-page crops = first columns,
     right-page crops = continuation of the same rows).
   - **Validation pass**: Re-read the crops and check the draft against them — pre-reform letter confusions
     (е/ѣ, и/і, ф/ѳ), names, numbers, line/column structure. Only then write the output file.
   - Write the final transcription to `transcriptions/<image_stem>.txt` next to the source image (create the
     subdirectory if the images live elsewhere; follow the existing layout of the year directory).

4. **Parallelize across pages with subagents** (measured on a reading benchmark). Only when the
   `.txt` itself is the product (a reviewable text, a whole year digitised for several readers): when the goal is
   the DSL, writing it straight from the scan made a third fewer errors than a transcription extracted afterwards.
   For multi-page batches, spawn `verso-reading:scan-reader` subagents (Opus at effort high) —
   **about ten records' worth per agent**, never one image each (every agent pays its context before its first
   image, ~17k in a large repository) and not fifty (a big batch flags less, so its errors go silent). For a large
   batch, run them from outside the repository, where an agent starts with no project context at all (the
   AGENTS.md проекта says whether the project has a launcher for that). Write the shared instructions once to a scratchpad file (transcription rules below +
   regional context digest + crop paths), give each agent a short prompt pointing at it, and ask it to read all
   its crops in parallel, in one turn. Launch in waves of 2–4. Require the two-pass protocol and a brief report:
   sheet number, record type (births/marriages/deaths), record number range, months, count of remaining `?` marks.
   If a page comes back with many `?` in name columns, send the agent a follow-up message directing it at the crops
   (or better crops) rather than respawning — its page context is already loaded. Outside the Claude Code plugin
   there is no such agent: give your harness's own subagent the same brief — the crops listed, read-only, «?» for
   what does not read — or read the crops yourself.

5. **After transcription completes**:
   - Verify every expected `.txt` exists and is non-empty; count `?` per file as a quality signal
     (`grep -o '?' file | wc -l`)
   - Present a summary to the user: sheet numbers, record types per page, uncertainty hotspots
   - Suggest next steps (extraction, validation)

**Important notes:**

- Honest uncertainty beats invented text: names that cannot be read from the best available crop stay `?`.
- If scans are inherently too poor even with crops (names still mostly `?`), tell the user and ask for
  higher-resolution scans instead of guessing.
- Keep crops in the session scratchpad, not in the repo; only the `.txt` transcriptions are committed
  (scan images in `transcriptions/` are typically gitignored).

### Regional Context Files

Always use the appropriate regional context file when available. Альбомы, архивы и региональные правила — в
AGENTS.md проекта: it names the file for each village.

Distill the relevant parts (parish, estates vocabulary for the year, frequent surnames, clergy roster, neighboring
villages) into the shared instructions you give transcription subagents — full rule files are too long to repeat per
agent. The parish's surnames help a little, as measured (all errors −3.4 per 100 names, silent errors unchanged), and
the model also writes a frequent parish surname over what is written: call the list a reading aid and ask for «?»
where the page does not show the name.

---

## Document Context

### Source Materials

**Historical period**: Russian Empire (Российская империя), 18th-19th centuries

**Script**: Cyrillic with pre-revolutionary orthography (дореформенная орфография)

### Document Types

#### Метрические книги (Metric Books)

Church records of vital events:

- **Рождение** (Births): Parents, child name, godparents, baptism date
- **Брак** (Marriages): Groom, bride, parents, witnesses, wedding date
- **Смерть** (Deaths): Deceased, age, cause of death, burial date

#### Ревизские сказки (Census Records)

Population censuses conducted periodically:

- Household lists with all family members
- Ages, relationships, social estates (сословия)
- References to previous census records
- Tax and military service information

### Regional Context Files

If a regional rules file is provided (the AGENTS.md проекта names it), use it to:

**Disambiguate handwriting**:

- **Географические названия**: Place names (villages, administrative divisions)
- **Типичные имена и фамилии**: Common personal names and surnames in the region
- **Особенности почерка**: Specific scribal handwriting patterns for the document/scribe
- **Административная структура**: Administrative structure (уезд/county, волость/township, губерния/province)

**Apply regional knowledge to**:

- Village and place names that may be difficult to read
- Common surnames that appear frequently in the region
- Typical naming patterns and patronymics
- Local administrative terminology and social estates

## Core Principle: Literal Character-by-Character Transcription

**CRITICAL: STOP AND REQUEST MISSING INPUT**: If the image file has not been provided, DO NOT proceed with
transcription. Stop and request the image from the user.

**CRITICAL**: Transcribe the document exactly as written, character by character. Your goal is to create a perfect
digital copy of the original text to minimize Character Error Rate (CER) and Word Error Rate (WER).

## Forbidden Actions

**DO NOT:**

- ❌ Correct spelling errors
- ❌ Fix typos or scribal mistakes
- ❌ Normalize or modernize the text
- ❌ Adapt old orthography to modern Russian
- ❌ Guess or invent text for illegible sections
- ❌ Reconstruct missing or damaged text

## What to Preserve

Preserve **ALL** original features exactly:

1. **Orthography**: Old spelling, including pre-revolutionary letters (ѣ, ѳ, і, ъ, ѵ)
2. **Case**: Exact capitalization (uppercase/lowercase) as in original
3. **Punctuation**: Original punctuation marks, even if unusual
4. **Errors**: Spelling mistakes, typos, scribal errors - transcribe as-is
5. **Superscript marks**: Titlo marks (˜) and other diacritics (надстрочные знаки)
6. **Spacing**: Word spacing as in original
7. **Symbols**: Crosses (†, ✝), asterisks (\*), or other marks

## Structure Preservation

1. **Line breaks**: One line in document = one line in transcription (strictly maintained)
2. **Paragraphs**: Preserve paragraph divisions
3. **Columns**: Use vertical bar `|` to mark transition between columns
4. **Completeness**: Transcribe everything - headers, footers, page numbers, signatures, monthly/yearly totals
   («Итого въ …»)

## Special Elements

### 1. Marginalia and Insertions

- If text clearly belongs to specific location: insert inline in angle brackets `<текст вставки>`
- If placement unclear: place at end of document with note

### 2. Illegible Text

- Completely illegible word/phrase: `?` (e.g., `? Манилова` for an illegible first name)
- Uncertain character: `Ив?нъ`
- Partial/cut-off text: visible characters + `?` (e.g., `Ва?` for a cut-off patronymic)
- Do NOT guess - mark clearly instead

### 3. Cross-outs and Edits

- Crossed-out text: `~зачеркнуто~`
- Stamps/seals: `[печать: текст печати]`
- Interlinear additions: `^надстрочное: текст^`

### 4. Document Damage

- Physical damage: `[повреждение документа]`
- Stains: `[пятно]`
- Binding damage: `[корешок книги закрывает текст]`
- Indicate approximate extent of missing text
- Do NOT attempt to reconstruct missing text

### 5. Image Quality Issues

- Poor quality sections: `[качество изображения плохое]`
- Specific quality notes: `[текст бледный]`, `[размытие]`, `[затемнение]`
- Archive watermarks: `[водяные знаки архива поверх текста]`

## Output Format

The output `.txt` file must follow this **exact format**:

```
[transcription starts immediately here — no preamble, no markdown fences]
```
