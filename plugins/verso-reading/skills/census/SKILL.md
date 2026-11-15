---
name: census
description: >
  Find a family in a revision list (ревизская сказка) or a confession list (исповедная
  роспись) by reading the scans, then write the households into the DSL. Use when the user
  asks to find someone in РС 1719/1795/1811/1816/1834/1850/1858 or in an ИР of a given year,
  to trace a line one revision further back, to sweep a whole дело for a surname, to pull
  census scans out of Apple Photos / Google Drive, or when scans are photographs of a screen
  and the handwriting will not resolve.
---

`<this skill>` in the commands below is this skill's folder — the one this file is in; scripts are named
from it, so the skill runs wherever it is installed.

Locating one family in a 500-household revision list is a search problem, not a transcription
problem. Transcribing the дело page by page costs hundreds of image reads; the methods below
find the двор in ten to thirty. Read the project's census extraction rules before writing any
DSL — this skill covers finding and verifying, those rules cover the encoding. For a confession
list read the project's confession-list rules as well, and see "Confession lists" below: they are
searched differently, because there is no previous-revision age column to fingerprint with.

Альбомы, архивы и региональные правила — в AGENTS.md проекта: the extraction rules by record kind,
which album holds which дело, where each дело's record (its leaves, its links) is kept.

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

**Use `verso-scans export`, not photoscript.** (`verso-scans` is a command of verso-app, the
Verso review app, not of this library.) The albums are organised per village folder, one album
per дело, named `YYYY (АРХИВ Ф-О-Д)` (e.g. `1811 РС (АРХИВ 1-1-100)`, `1834 РС 8 (АРХИВ 1-1-200)`),
and the tool resolves them in `Photos.sqlite`, copies whatever is already on disk and pays
AppleScript only for the iCloud remainder:

```bash
verso-scans albums --match "1834 РС"      # Z_PK settles a duplicate title
verso-scans export --album "1834 РС 8" --album-pk 1234 --out $SC/rs1834 \
    --village Маниловка                    # ← ALWAYS: the durable stanza
verso-scans check  $SC/rs1834            # is the дело whole?
```

**Always pass `--village`.** Without it the album's stanza (pk, `frames`, note) lands only in
the export directory's own `scans.toml` — a scratch copy that is deleted with the session —
and every window `zoom --remember` saves after that goes there too. One whole review found
seven дворы across five albums this way and kept none of them. If an album was exported
without it, add the stanza afterwards with
`verso.app.scans.layout.remember_album(Path("<village>/scans.toml"), Album(...))` rather than
re-exporting (each `verso-scans` call snapshots Photos.sqlite via SQLite's online backup API
rather than copying the file plus its `-wal`/`-shm` sidecars — the snapshot it produces is
sized to what the database actually holds, not to the WAL, which matters because Photos was
measured not checkpointing at all: a 257 MB `Photos.sqlite` sat beside a 95 GB `-wal`, so the
old file-copy snapshot copied 95 GB on every call and four concurrent runs filled the disk.
The backup itself still walks that WAL to reconstruct the current pages, so it is not free —
measured at ~10 minutes for a ~4.5 GB snapshot on one library — but it is disk-safe: a few
concurrent runs cost a few GB apiece, not tens of GB each). Concurrent runs are safe: each
takes its own snapshot.

Driving Photos frame by frame is the path that fails SILENTLY: `photo.export()` has returned
`[]` with every original of an album already on disk, and a short directory is
indistinguishable from a дело the archive never photographed. Keep the recipe below only for
something `verso-scans` cannot do.

**Tell the album what it is — `scans.toml`.** A ревизская сказка is photographed as a SPREAD
far more often than a metric book is, and the filename usually names one лист only
(`63об.jpg` holding 63об and 64). Declare it once, in the album directory or the village
one, and every recto becomes addressable instead of being reported missing:

```toml
[album."1834 РС 8 (АРХИВ 1-1-200)"]
frames = "spread"      # one file, two leaves — the NAME gives the left one
top = 0.19             # where the ruled household table begins; bottom = … too
```

`top`/`bottom` are what make `zoom --row N OF` land on the right двор instead of drifting a
row. And once a household IS found, keep the window — `zoom … --record <№ двора> --box …
--remember` writes it back, and the same двор comes out of `--record` alone next time. A
whole-дело sweep re-reads the same дворы more than once; this is the difference. Remember a
better window later and it REPLACES the earlier one, so a first rough guess costs nothing.
`--record` accepts a revision list's letter-suffixed дворы as-is (`--record 1в`, `--record 2а`)
— households numbered "1", "1а", "1б", "1в" are each their own remembered window.

**Cut windows with `zoom --box`, not with ad-hoc PIL.** A hand-rolled `im.crop(...)` saves
nothing, and eyeballed pixel coordinates on a downscaled render miss the row more often than
not — the same session spent a dozen crops landing above or beside the figure it wanted.
`--box` takes FRACTIONS of the leaf (spread frames: of the whole frame), so the window
survives any render size, and with `--record <№ двора> --part 1 --remember --village X` the
first good one is kept:

```bash
verso-scans zoom $SC/rs1850 --folio 27 --part 1 --record 54 \
    --box 0.12 0.61 0.94 0.84 --scale 1 --tag d54 --remember --village Маниловка \
    --album-title "1850 РС 9 (АРХИВ 1-1-300)"
```

Under frame numbering `--folio 27` is the 27th file (1-based) and the window is stored as
«кадр27». `--scale 1` on a whole-двор window is already ~3400 px wide — enough to read a
figure; go to 3–4 only on a one-column strip. `--out` is a FILE path when given; a directory
fails inside PIL with «unknown file extension». An album photographed sideways (one metric-book
album was lying upside down, in fact) needs `rotate` in its stanza (180 there; one quarter-turn
left the text still running across) — boxes are fractions of the turned frame.
A frame shot differently from the rest takes its own turn, `rotate_frames = { "кадр1" = 90 }`,
which replaces `rotate` for that frame (the `verso-reading:metric-books` skill has the
details). Never «fix» a sideways HEIC by applying pillow-heif's `info["original_orientation"]`:
the decoder has already applied it, and applying it again turns the frame twice.

Comparing digits (is this «3» or «5»?) still wants a strip of one column at 3–4× beside the
same digit elsewhere on the page — cut it with `zoom --box` too, `--tag` keeps the outputs apart.

Two traps that renumber the frames under you:

- **Never write anything into the export directory.** Every image file there is a frame, so
  a `contact.jpg` or a HEIC→jpg conversion saved beside the originals shifts «кадр 6» onto a
  different page (in one album the births spread came up where the burials were). Send crops to
  `--out` elsewhere, and convert HEIC nowhere — `verso-scans` reads it.
- **A number in the filename is read as the лист — until a title says otherwise.** Scans
  named `000.png … 048.png` are often FILE numbers, but the tools read them as листы:
  `--folio 41` opens `041.png`, and the window is stored as «л. 41» although the page says
  86. (It cannot be ruled out by shape: `053.jpg` of another album really is л. 53.)
  **Fix it in Photos, not on disk:** set each frame's «Название» to `<кадр>_<лист>` —
  `0041_86`, `0042_86об`, read off the page's top-right corner — addressing the album by
  its UUID (`ZGENERICALBUM.ZUUID`, see the `photoscript` recipe below), check the titles in a
  fresh `Photos.sqlite` snapshot, and re-export. A title that names a лист beats the
  filename, so the export comes out as `0041_86.png` and `--folio 86` opens the right page;
  `check --album` reads the titles too. A title naming no лист (`0000_обложка`) leaves the
  filename alone. Re-key any window remembered under the old number — it is stored by the
  label, which has changed.
  Timestamp names (`20231115_101530.jpg`) never count as a лист; untitled, `--folio 20` finds
  «no page 20» — pass `--frames` to number by position, or title them the same way.

`photoscript` is the fallback if it is ever needed:

```python
import photoscript
p = photoscript.PhotosLibrary(); p.activate()
folder = [f for f in p.folders() if f.name == "Маниловка"][0]
alb = [a for a in folder.albums if a.name == "1834 РС 8 (АРХИВ 1-1-200)"][0]
for ph in alb.photos():
    ph.export(dest, original=True, overwrite=False, timeout=180)

# Titling: address the album by UUID (select ZUUID from ZGENERICALBUM where Z_PK=…),
# not by name — the folder walk has failed with «Invalid index».
alb = photoscript.Album("<ZUUID of the album>")
for ph in alb.photos():
    ph.title = titles[ph.filename]          # {"041.png": "0041_86", …}
```

- `.folders()` / `.albums()` are METHODS on `PhotosLibrary`; on a `Folder`, `.albums` is a
  PROPERTY (no parens).
- **Do not read the originals straight off disk.** Roughly half are iCloud-optimised: only a
  1536×2048 derivative exists locally under `resources/derivatives/`, and the full 4096×3072
  original arrives only when `export()` pulls it down. Exporting runs at ~35 photos/minute, so
  a 250-photo дело takes about seven minutes — start it in the background.
- Phone photos of an open ledger are often **rotated**: the spread sits sideways in a portrait
  frame. The phone's orientation tag is a guess, and flat over a book it is often wrong, so
  `ImageOps.exif_transpose()` (which applies it) is not enough; try `.rotate(90, expand=True)`
  and check which way up the text lands before deciding which half is the male page — then
  declare the turn in `scans.toml` (`rotate` / `rotate_frames`) so the next reader need not.

**Google Drive** holds the same scans for some дела (the project's record of the дело has the
folder links). They are publicly fetchable without auth:

```bash
curl -sL "https://drive.usercontent.google.com/download?id=<FILE_ID>&export=download&confirm=t" -o 000.png
```

Enumerate the folder with `gdown --folder --json <folder-url>` (install into the venv) — the
plain `gdown --folder` download rate-limits after ~40 files, so take the JSON id list and curl
the rest yourself. `uc?export=download` works for small files but returns a confirm page for
large ones; the `usercontent` host with `confirm=t` does not.

⚠ **A reading is not a finding until the person who knows the hand agrees.** Ages and names
in a revision tale decide who is whose child, and a single misread letter propagates into the
DSL, the fold and the tree. Cut the window, show it, and ask — twice in one session a
confident reading at 9–12× turned out to be another surname of the same shape, and each
retraction cost more than the crop did.

## Sweeping a whole дело cheaply

A 500-household дело is ~100 page images. Reading each in full costs ~2000 tokens; reading
just the left margin costs a quarter of that, and the margin is where the household number and
the head's name live.

```python
# 4 pages side by side, left 37% of each — head names and numbers, nothing else
W, H = 420, 1700
def strip(n):
    im = Image.open(f"rs1811/{n:03d}.png").convert("L")
    w, h = im.size
    c = ImageOps.autocontrast(im.crop((0, 0, int(w * 0.37), h)), cutoff=1)
    return c.resize((W, H), Image.LANCZOS)
```

Twenty-seven montages cover a hundred pages. Use this to build the household-number → page
index first; then jump straight to the band your fingerprint predicts.

**Cheaper still for the index alone — a strip of the «№ семьи» column, 27 frames to a sheet**
(`<this skill>/../metric-books/scripts/scan_strips.py`, the «лента по одной графе» of
ex-USSR Kinship Research). Tested on a 10th-revision дело (reading-room spreads 1500×~1180):
100 frames → **4 sheets** in a second, and they gave every anchor of a hand-made index that had
taken 35 three-scan montages.

```bash
python3 "<this skill>/../metric-books/scripts/scan_strips.py" "$ALBUM" \
    --box 0.065,0.26,0.145,0.93 --frames 0310-0409 --per 27 --size 800 --out $SC/strips
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
  3× before, readable at 2× after. Packaged as
  `<this skill>/scripts/descreen_crop.py` (Python and Pillow):

  ```bash
  python3 "<this skill>/scripts/descreen_crop.py" \
      page.png 0.19,0.22,0.66,0.60 1.5            # band of rows, 1.5x, de-screened
  python3 "<this skill>/scripts/descreen_crop.py" \
      photo.jpg - 0.4 raw 90                       # whole page, rotated, no filter
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
whether the project has a launcher for that).

## Cross-checking against the parish registers

`village.db` is the other half of the search. Before opening a scan:

```bash
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
