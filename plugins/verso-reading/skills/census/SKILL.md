---
name: census
description: >
  Find a family in a revision list (ревизская сказка) or a confession list (исповедная
  роспись) by reading the scans, then write the households into the DSL. Use when the user
  asks to find someone in РС 1719/1795/1811/1816/1834/1850/1858 or in an ИР of a given year,
  to trace a line one revision further back, to sweep a whole дело for a surname, to cut a
  directory of a дело's frames into what reads, or when scans are photographs of a screen
  and the handwriting will not resolve.
compatibility: >
  Needs Python 3.14+ and the verso library on PATH — pip install 'verso-core[scans]>=0.1.43'
  'verso-ru>=0.1.43' (verso-core[heic] for a phone's own format) — and an agent that can open
  local image files.
---

Locating one family in a 500-household revision list is a search problem, not a transcription
problem. Transcribing the дело page by page costs hundreds of image reads; the methods below
find the двор in ten to thirty. Read the project's census extraction rules before writing any
DSL — this skill covers finding and verifying, those rules cover the encoding. For a confession
list read the project's confession-list rules as well, and see "Confession lists" below: they are
searched differently, because there is no previous-revision age column to fingerprint with.

**What this costs.** This text — about 22 thousand characters — is read once, when the skill is
used. The sweeps below read strips and fingerprints, not whole pages; subagents are optional, and one pays
its own context before its first page.

Альбомы, архивы и региональные правила — в AGENTS.md проекта: the extraction rules by record kind,
where each дело's frames and its record (its leaves, its links) are kept.

The other skills named here are named bare (`metric-books`); in the Claude Code plugin they are
`verso-reading:metric-books` and so on.

## The method: work backwards one revision at a time

Never start from the earliest source. Start from the revision where you already know the
family and step back, because each revision states the ages from the previous one and that
gives you an exact fingerprint to search for.

1. Take the household you know (say РС‑8 1834, семья 257).
2. Read every member's `previous_age` — that is their age at the **prior** revision.
3. Convert to the revision you are searching. The gaps are fixed:

   | revision | prior | gap |
   |---|---|---|
   | 1745 | 1719 | 26 |
   | 1762 | 1745 | 17 |
   | 1795 | 1782 | 13 |
   | 1811 | 1795 | 16 |
   | 1816 | 1811 | 5 |
   | 1834 | 1816 | 18 |
   | 1850 | 1834 | 16 |
   | 1858 | 1850 | 8 |

   (Authoritative table: `verso.ru.census_revisions`.)
4. You now have a **household fingerprint**: a head of a given age plus a specific set of sons
   with specific ages. That shape is what you search for, not the name.

The fingerprint is what makes the search cheap and the identification safe. A name alone
proves nothing in a village where forty men are called Иван Ивановъ; five ages agreeing to
within a year proves everything.

## Age arithmetic is your error detector, not just your search key

Both age columns for one person must differ by exactly the revision gap. Any pair that does
not is **a misreading, not a source inconsistency** — the scribes were reliable about this
because the numbers were copied forward, not recomputed.

This is the single most useful check in the whole workflow. Real examples from one session:

- An agent reported «Аѳанасій 13 → 25» and «Лука 9 → 15» for an 1811 двор. Gap is 16, so
  both are wrong; the correct readings were 29 and 25.
- Two readers (me included) read «Прохоръ 19» where the 1834 list implied 11. At maximum zoom
  the digit was **12** — a «2» whose bottom tail is flat, not a «9» with a closed bowl.
- Conversely a pair that *does* fit is strong evidence you read it right, even on bad ink.

So: compute the expected partner of every number you read. When it disagrees, re-crop before
believing either figure.

## Getting the scans

**Кадры дела — каталог.** The input is a directory of the дело's frames, best named by folio
(`<кадр>_<лист>[об]`: `0118_57.jpg`, `0119_57об.jpg`). Откуда кадры — в AGENTS.md проекта: an
archive's download, an export of a photo library, a shared folder. `verso scans check DIR` says
whether the дело is whole; `verso scans` needs `pip install 'verso-core[scans]>=0.1.43' 'verso-ru>=0.1.43'`.

```bash
FR=/path/to/the/frames/rs1834          # the дело's frames, as the project keeps them
SC=/tmp/rs1834                         # scratchpad, never the project tree nor $FR
verso scans check $FR                  # is the дело whole?
```

**Tell the album what it is — `scans.toml`.** A ревизская сказка is photographed as a SPREAD
far more often than a metric book is, and the filename usually names one лист only
(`63об.jpg` holding 63об and 64). Declare it once in the frames' directory — `check`, `headers`,
`crops`, `spread`, `zoom` and `rows` read it there, and `zoom`/`rows` also read the file `--layout`
or `--village` names — and every recto becomes addressable instead of being reported missing:
`check` counts both leaves of a frame, and a window's fractions are of the leaf, cut from its half.

```toml
[album."1834 РС 8 (АРХИВ 1-1-200)"]
frames = "spread"      # one file, two leaves — the NAME gives the left one
top = 0.19             # where the ruled household table begins; bottom = … too
```

`top`/`bottom` are what make `zoom --row N OF` land on the right двор instead of drifting a
row. Once a household IS found, keep its window: a whole-дело sweep re-reads the same дворы more
than once, and that is the difference. `verso scans` never writes `scans.toml`; if the project has
a tool that remembers windows, the AGENTS.md проекта names it — otherwise note the `--box` beside
the двор in the project's notes on the дело.

**Cut windows with `zoom --box`, not with ad-hoc PIL.** A hand-rolled `im.crop(...)` is thrown
away, and eyeballed pixel coordinates on a downscaled render miss the row more often than
not — one session spent a dozen crops landing above or beside the figure it wanted.
`--box` takes FRACTIONS of the leaf — under `frames = "spread"` the half of the frame the leaf lies
on; for a spread not declared in `scans.toml`, or under `--frames`, the whole frame — so the window
survives any render size:

```bash
verso scans zoom $FR --folio 27 --part 1 --box 0.12 0.61 0.94 0.84 --scale 1 \
    --album-title "1834 РС 8" --out $SC/rs1834_d54.jpg
```

Under frame numbering `--folio 27` is the 27th file (1-based), labelled «кадр27». `--scale 1` on a
whole-двор window is already ~3400 px wide — enough to read a figure; go to 3–4 only on a
one-column strip. `--out` is a FILE path; a directory fails inside PIL with «unknown file
extension». An album photographed sideways (one metric-book album was lying upside down, in
fact) needs `rotate` in its stanza (180 there; one quarter-turn left the text still running
across) — boxes are fractions of the turned frame. A frame shot differently from the rest takes
its own turn, `rotate_frames = { "кадр1" = 90 }`, which replaces `rotate` for that frame (the
`metric-books` skill has the details). Phone photos of an open ledger often have
the spread sideways in a portrait frame, and the phone's orientation tag is a guess that over a
flat book is often wrong: try the turn, check which way up the text lands before deciding which
half is the male page, then declare it so the next reader need not. Never «fix» a sideways frame
by applying pillow-heif's `info["original_orientation"]`: the decoder has already applied it, and
applying it again turns the frame twice.

A ledger photographed a little crooked — its lines falling a degree or two, so a window around one
двор takes in the next one's rows — takes `zoom --angle auto` (or `--angle DEG`, counter-clockwise,
within ±45): the window, named on the frame as it lies, is cut from the frame turned level, and the
line `zoom` writes says the turn. `rotate` is for quarter turns only; the `metric-books` skill has
the details, `rows --angle` among them.

Comparing digits (is this «3» or «5»?) still wants a strip of one column at 3–4× beside the
same digit elsewhere on the page — cut it with `zoom --box` too, each to its own `--out`.

Two traps that renumber the frames under you:

- **Never write anything into the frames' directory.** Every image file there is a frame, so
  a `contact.jpg` saved beside the originals shifts «кадр 6» onto a different page (in one
  album the births spread came up where the burials were). Send crops to `--out` elsewhere.
  A phone's own format is read as it is with `verso-core[heic]>=0.1.43`, and converting it is done in
  place: `verso scans jpeg DIR` replaces each HEIC with a JPEG of the same name, keeping the count.
- **A number in the filename is read as the лист.** Scans named `000.png … 048.png` are often
  FILE numbers, but the tools read them as листы: `--folio 41` opens `041.png` although the page
  says 86. (It cannot be ruled out by shape: `053.jpg` of another дело really is л. 53.)
  Rename each frame `<кадр>_<лист>` — `0041_86.png`, `0042_86об.png`, read off the page's
  top-right corner — and `--folio 86` opens the right page; where the project keeps its frames
  (the AGENTS.md проекта) says how to rename them there. A name naming no лист
  (`0000_обложка`) is a frame and no page. Re-key any window noted under the old number.
  Timestamp names (`20000101_120000.jpg`) never count as a лист; `--folio 20` then finds
  «no page 20» — pass `--frames` to number by position, or rename them the same way.

⚠ **A reading is not a finding until the person who knows the hand agrees.** Ages and names
in a revision tale decide who is whose child, and a single misread letter propagates into the
DSL, the fold and the tree. Cut the window, show it, and ask — twice in one session a
confident reading at 9–12× turned out to be another surname of the same shape, and each
retraction cost more than the crop did.

## Sweeping a whole дело cheaply

A 500-household дело is ~100 page images. Reading each in full costs ~2000 tokens; reading
just the left margin costs a quarter of that, and the margin is where the household number and
the head's name live.

```bash
# 4 pages side by side, left 37% of each — head names and numbers, nothing else
verso scans strips $FR --box 0,0,0.37,1 --per 4 --size 1700 --out $SC/margins
```

Twenty-seven sheets cover a hundred pages. Use this to build the household-number → page
index first; then jump straight to the band your fingerprint predicts.

**Cheaper still for the index alone — a strip of the «№ семьи» column, 27 frames to a sheet**
(`verso scans strips`, the «лента по одной графе» of ex-USSR Kinship Research). Tested on a
10th-revision дело (reading-room spreads 1500×~1180): 100 frames → **4 sheets** in a second, and
they gave every anchor of a hand-made index that had taken 35 three-scan montages.

```bash
verso scans strips $FR --box 0.065,0.26,0.145,0.93 --frames 0310-0409 --per 27 --size 800 --out $SC/strips
```

The box is in fractions of the frame (a 9th/10th-revision spread: both number columns sit at
x 0.065–0.145, the table from y 0.26). Numbers only — the head's name still needs the 37 % strip
above or the frame itself. Archive scans only: phone photographs of a book drift from frame to
frame and a fixed box misses.

**Predicting the band.** Household order is broadly preserved across revisions. Sample two
pages, note their household numbers, and interpolate — 4–5 households per page is typical. A
family at семья 412 in 1834 will not be at двор 5 in 1811.

**The margin strip has one blind spot**: it shows the given name but often clips the
patronymic, and it cannot show a man listed as a son inside someone else's двор. If a margin
sweep comes back empty, that is not proof of absence — widen the crop or sweep by given name
instead. A given name reads far more reliably than a patronymic in this hand, and a
name-only negative is worth much more than a patronymic-based one.

## Confession lists (исповедные росписи)

An ИР is searched the same way — build a двор → page index, interpolate, jump — but the
fingerprint is weaker and the page reads differently.

**Locating the двор.** The number stands in the leftmost column **against the first line of
its household**. The two «Число людей» columns beside it carry *running totals of people*;
a «100» there is not двор 100, and mistaking one for the other throws the whole index off.
Expect ~3–5 дворы per page (a peasant household with married sons fills half a page), so
sampling two pages and interpolating lands within a page or two of the target.

**Reading the page.** Three rules, and the third is the one that ruins transcriptions:

- The **age column decides the sex** — «Мужеска пола» / «Женска пола». When your reading of a
  name disagrees with the column, the column wins.
- **Exactly one age per person.**
- **A name may wrap onto a second line** («Иванова жена Пелагея / Петрова» is one woman),
  and the wrapped line carries no age of its own. So **count the ages and count the people
  before writing anything down** — if they differ, you have taken a wrap for a person and
  every age below that point is off by one row.

**What you lose, and what you gain.** There is no previous-revision column, so the age-gap
arithmetic that makes a revision search self-checking does not exist, and ИР ages drift by
years between rolls — identification has to come from the household's *shape* (head + wife +
sons in birth order + сноха), cross-checked against the metric books. What you gain is a
yearly snapshot with the women and the girls in it, dating a household to a single year
instead of a revision interval.

## When the scans are photographs of a screen

Some дела reach us as phone photos of a monitor showing a PDF viewer. Two consequences:

- **Orientation varies shot to shot** and the two halves of a spread can differ. Decide it
  per photo: in this form the printed column headers run *perpendicular* to the handwriting,
  so if the printed «…дворовъ» header reads horizontally, the names do not — rotate 90° and check
  again. Straighten the page before cropping; do not fight it band by band.
- **Moiré is the real blocker.** The screen's pixel grid beats against the camera sensor and
  produces fine vertical stripes that survive contrast stretching and get *worse* under
  upscaling — at 5× the letters dissolve into the stripes. A plain median filter does not
  remove them because they are directional.

  **A one-dimensional box blur across the stripes, applied BEFORE upscaling, does.** In PIL a
  5×5 kernel with only the middle row filled is a horizontal 5×1 box:

  ```python
  im = im.filter(ImageFilter.Kernel((5, 5), [0]*10 + [1]*5 + [0]*10, 5))
  im = im.resize((im.width * 2, im.height * 2), Image.LANCZOS)
  im = im.filter(ImageFilter.UnsharpMask(radius=4, percent=160, threshold=2))
  im = ImageOps.autocontrast(im, cutoff=0.5)
  ```

  (Transpose the kernel if the stripes run horizontally.) It costs a little horizontal
  sharpness and buys back the whole word. Measured on one дело of such photos: unreadable at
  3× before, readable at 2× after. `verso scans descreen` does exactly this, writing into
  `crops/` beside the scan:

  ```bash
  verso scans descreen page.png 0.19,0.22,0.66,0.60 1.5     # band of rows, 1.5x, de-screened
  verso scans descreen photo.jpg - 0.4 raw 90               # whole page, rotated, no filter
  ```

- **The useful zoom is lower than you think.** ~1.5–2× over a band of 6–10 rows beats 4–5×
  over one word: the underlying scan has no more detail to give, and the wider band gives you
  the neighbouring rows to align against. Go to 3–4× only for a single contested letter, and
  believe the result less than you would on a real scan.
- **Check for a duplicate frame.** These albums often contain two shots of the same spread
  taken seconds apart; the second is sometimes sharper or free of the viewer's UI overlay.
  Sort the album by timestamp and compare before concluding a word is illegible.
- **Say so in the output.** Screen photos cap what can honestly be read. Keep the file
  `reviewed=False`, put every contested reading in `comment=`, and tell the user which lines
  need a better scan rather than quietly picking the likelier of two readings.

## Delegating to subagents

Only with the user's explicit go-ahead. Fan-out works well for the sweep and badly for the
verdict. Measured over one session of four agents on about a hundred pages:

- **Good at**: covering ground, building the page → household index, spotting a marginal
  remark you skipped (they found «умеръ въ 1807 году» in a column I had cropped away), and
  reporting honest negatives.
- **Bad at**: patronymics. Three wrong readings that survived their own zoom checks —
  «Мартыновъ» for Маркеловъ, «Никифоровъ» for Нефедовъ, «Степанъ» for Семенъ. One also declared a
  range clean that contained the target двор.

So: **re-read every line yourself before it goes into the DSL.** Take their ages and remarks
as leads, never as data. When two readings conflict, the age arithmetic usually decides it
without a third opinion; when it cannot, crop that one word at 8× and look.

Give each agent a fingerprint (names *and* ages), the page range, the full-resolution path for
their own crops, and an explicit instruction to flag uncertainty rather than smooth it. Model,
effort and how much to give one agent were measured on a reading benchmark: Opus at effort high,
about ten records' worth per agent (each pays its context before its first page; a much bigger
range flags less and leaves more silent errors), parallel reads, and the lean
`verso-reading:scan-reader` for a sweep that only reports — for a long sweep, one brief per agent,
run from outside the repository so each starts with no project context (the AGENTS.md проекта says
whether the project has a launcher for that). Outside the Claude Code plugin there is no such
agent: give your harness's own subagent the same brief — the crops listed, read-only, «?» for what
does not read — or read the pages yourself.

## Cross-checking against the parish registers

`village.db` is the other half of the search — `verso all-persons <village>` builds it from the
village's DSL, and rebuilds it after a year is written. Before opening a scan:

```bash
verso all-persons Маниловка
verso find-person Маниловка "Федот Зотов"
sqlite3 -column -header Маниловка/village.db "SELECT year,record_type,record_num,role,name_orig,patr_orig \
  FROM persons WHERE patr_orig LIKE 'Зотов%' AND year<=1800 ORDER BY year;"
```

Two things this buys you:

- **A death date tells you whether to look at all.** A father who died before the prior
  revision is simply absent from the list — his sons open the двор under a bracketed
  «<Отчество>вы дети» heading with no head line. Searching for him wastes a whole sweep.
- **It confirms the identification independently.** A revision-list двор whose head died in
  1808 and a burial record of the same name dated 03.02.1808 are the same man; that pairing is
  worth more than any single reading.

Watch the orthography: the registers spell the same patronymic «Евдокимовъ» and «Авдокимовъ», and
the modern canonicalisation in `village.db` maps «Ѳоминъ» to «Фомич». Query the
`*_orig` columns with `LIKE` prefixes, not the modern forms.

## Writing the result

Encode per the project's census extraction rules — role in the source's own word, `ref_member`
for a non-head parent, pre-reform orthography, no `comment=` on `household()`. For a confession
list use `census_records(**CONFESSION_LIST)` and the project's confession-list rules: same
roles and `ref_member`, but always pass the двор number and never `previous_age`.

Two rules specific to scan work:

- **Mark the file `reviewed=False`** while any reading is open. `census_records(reviewed=False)`
  sets it for the whole file, `household(reviewed=…)` overrides per двор. An unreviewed
  household emits no profiles, document or union, so a half-read двор cannot reach Geni.
- **Never fill a gap from arithmetic.** If a figure is illegible, omit the age and say why in
  `comment=`. Back-computing it from the next revision turns a transcription into an
  assertion, and the next reader cannot tell which is which.

Record contested readings in `comment=` rather than picking silently — «имя при повторном
чтении разобрано как Матвей», «цифра возраста в скане не читается».

Then `verso dsllint <file>` — no finding of level error (it reads the text and imports nothing) — and
`verso export-csv --village <village> --year YYYY`, which must exit 0: it builds the file, and a file that
does not import is skipped by every check after it with a warning and an «OK». The roll's own linters
(CAI, CPL) are in `dsllint`. A roll's ages are checked against the metric books by
`verso facts --village <village> --check birth-claims` — once the corpus has joined each person's records,
and on reviewed households only.

## Releasing a roll: fold it before any plan

Dropping `reviewed=False` mints a NEW profile for every member. Before the next plan of the
tree, map each member to a canonical by place in the двор, kin and age, against the
neighbouring rolls and the metric books. Do it member by member, writing each age
pair into the config comment.

A roll is often the bridge no channel had. One confession list's двор tied together a
birth, two weddings and a later revision's двор into one household. Most of those records
were already on Geni, so the fold needs Geni merges first: the project's consolidation guide
(the AGENTS.md проекта names it) has the recipe for folding records already on Geni.

When two rolls disagree on a name for the same slot (wife «Ѳеодосья» in one, «Евдокія» in the
next), re-read the scan before choosing between «two wives» and «one woman». In the case this
comes from, the later reading turned out to be wrong.

## Worked example

Маниловка РС‑6 1811 (АРХИВ 1-1-100, лл. 88–131, 87 scans, 402 households). Target: the
Маниловы, known from РС‑8 1834 as семьи 412, 413, 417, 420, 431, 436.

1. 1816 ages from the 1834 file → minus 5 → 1811 ages. Лаврентій Никоновъ 41, Кондратъ 34,
   Онисимъ Ѳилиповъ 52, Прохоръ Онисимовъ 29, Евсѣй 22.
2. `village.db`: «Никонъ Ѳилиповъ» died 1789 — before the 1795 revision, so he will not be
   in the list. Expect his sons to open a двор as «Никоновы дети».
3. 1834 семья 412 ÷ 448 households ≈ the tail of the дело → search pages 074–086 first.
4. Margin montages over the tail → двор 361 «Лаврентій ⎫ Никоновы дети / Кондратъ ⎬», 26 → 42 and
   18 → 34. Seven age points agree within a year. Двор 362 next door is Онисимъ Ѳилиповъ 37 → 53.
5. Двор 384 gives the root: Ѳилипъ Савельевъ, 64 at the 1795 revision, born about 1731.
6. Five of the six 1834 households resolve onto three дворы of 1811.

Total cost: about twenty-five image reads, of which a dozen were single-word crops settling
disputed letters.
