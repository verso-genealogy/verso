---
name: metric-books
description: >
  Read a year of a metric book (метрическая книга) from a directory of its scans — verify the
  дело is whole, find where части 1/2/3 begin, and cut the pages into the crops that are
  actually legible. Use when sweeping a year for a surname, continuing a year-by-year pass
  through a дело, re-checking one record against its scan, or when a reading disagrees with
  what the corpus already holds. For revision and confession lists use
  `verso-reading:census` instead; for producing a reviewable .txt use `verso-reading:transcription`.
---

A year of a metric book is ~36 листов = ~72 pages. Reading them whole costs several times
what it needs to and gets surnames wrong at an archive's ~950 px per leaf. The four setup steps
below are mechanical and are handled by `verso scans`; everything after them is reading, and no
tool helps with that.

**Кадры дела — каталог.** The input is a directory of the дело's frames, best named by folio:
`<кадр>_<лист>[об]` (`0118_57.jpg`, `0119_57об.jpg`, a spread `0241(131об-132).jpg`). Откуда
кадры — в AGENTS.md проекта: an archive's download, an export of a photo library, a shared folder
— and, with them, the project's regional rules, where the record of each дело's composition (its
first and last лист, its parts) is kept, and the surnames and estates of each village.
`verso scans check DIR` says whether the дело is whole.

`verso scans` needs Pillow: `pip install 'verso-core[scans]>=0.1.40' 'verso-ru>=0.1.40'`. A phone's own
format needs `'verso-core[heic]>=0.1.40'`; with it, `verso scans jpeg DIR` can also turn each HEIC frame into a JPEG in place.

## The four steps

```bash
FR=/path/to/the/frames               # the дело's frames, as the project keeps them
SC=/tmp/mn1887                       # scratchpad, never the project tree nor $FR

# 1. Is the дело whole? --first/--last come from the project's record of the дело.
#    Run it before pulling anything else out of the frames: a SELECTIVE set
#    (80 frames for 288 sides) and a gappy one (27 sides absent) were both found
#    the expensive way, after a hundred crops had already been read.
verso scans check $FR --first 57 --last 92

# 2. Where do части 1/2/3 begin? The running header names the part; a BLANK
#    header strip is a part title page.
verso scans headers $FR --out $SC/headers

# 3. Cut the pages you will actually read — ONE PART AT A TIME, so the crop can
#    drop the columns that carry no names. Folio ranges come from step 2.
verso scans crops $FR --out $SC/c1 --verso-only --part 1 --from 58 --to 74
verso scans crops $FR --out $SC/c2 --verso-only --part 2 --from 75 --to 77
verso scans crops $FR --out $SC/c3 --verso-only --part 3 --from 78 --to 91
```

4. Read `$SC/c1/*.jpg` (then `c2`, `c3`) in order. When a page yields a record worth keeping, pull
its facing recto **row-aligned**:

```bash
verso scans spread $FR --folio 64об --band 0.41 0.63 --out $SC/spread_64об.jpg
```

## Ленты по одной графе — one column across the whole дело

When the question is about ONE column over many frames — a surname in the parents' column, the
«Имена родившихся» of a whole year, household numbers of a revision, the head line of a card —
cut that column from every frame and lay the strips side by side, each labelled with its frame:

```bash
verso scans strips $FR --box X0,Y0,X1,Y1 [--frames FIRST-LAST] [--per 20] [--size 900] --out $SC/strips
```

The box is in fractions of the frame (reading-room scans of one дело drift by a few pixels); a
tall box is laid left to right, a wide one stacked. A strip finds; the frame it names is then read
at full size (two-tier rule below). It needs a steady layout — an archive's own scans; phone
photographs of a book shift and turn, and a fixed box misses. Tested on a 10th-revision дело: see
the `verso-reading:census` skill, «Sweeping a whole дело cheaply». The idea is ex-USSR Kinship
Research's (its field lessons and its scan montage).

## When the frames were never renamed

The four steps above assume the `<кадр>_<лист>.jpg` naming. Whole folders of frames are not
renamed — the years of a parish may sit exactly as the phone wrote them
(`IMG_20000101_120000.jpg`). Every subcommand except `spread` then numbers pages by
**position** and calls them «кадр 12»; `--from`/`--to` select frames, `--frames` forces the
mode, and `check` tells you it can verify nothing:

```bash
verso scans headers $FR --out $SC/headers --rows 6   # → кадр1 … кадр38
verso scans crops   $FR --out $SC/p3 --from 31 --to 38 --part 3
verso scans zoom    $FR --folio 35 --box 0.28 0.55 0.82 0.63 --scale 3.4 --out $SC/z35.jpg
```

Two things this mode cannot do. **It verifies nothing** — a leaf never photographed and a
leaf filed under the wrong year both look like a tidy directory, which is the whole reason the
folio naming exists; rename the frames `<кадр>_<лист>[об]`, read off each page's corner, before
reading a year twice. And **`spread` does not apply**, because «the facing recto» has no meaning
without лист numbers — cut the two halves by hand with `crops --x0/--x1`.

**A number in the filename is read as the лист.** Frames named `000.png … 048.png` are often
FILE numbers, but `verso scans` reads them as листы: `--folio 41` opens `041.png` although the
page says 86. (It cannot be ruled out by shape: `053.jpg` of another дело really is л. 53.)
Rename them `<кадр>_<лист>` (`0041_86.png`, `0042_86об.png`) and `--folio 86` opens the right page.

The frame index counts every image in the directory, so **always `--out` somewhere else**:
writing crops back beside the frames renumbers everything after them. `spread`, `zoom` and
`rows` write into the frames' directory unless `--out` names a file — give it every time.

**A pale hand needs `--enhance`.** Plain autocontrast (the default, `--enhance 1`) left one
book guessable but not readable; `--enhance 1.7` clips the histogram at both ends and
pushes contrast and edges, and the surnames come out plain. Pushing a hand that is already
dark only crushes it, so this is a dial, not a default. Available on `crops`, `spread` and
`zoom`. Once found, set `enhance = 1.7` in the album's stanza of `scans.toml` (below) and
`zoom` takes it without the flag (the output line says «enhance 1.7 из scans.toml»).

## Why each step is shaped this way

**Frames are rotated by EXIF, not by pixels.** A phone records the rotation as a tag and
Pillow does not apply it on open, so a tagged frame would have every fractional window cut
against the wrong axis — a `--part 3` crop slicing across the columns instead of along
them, unreadable with nothing to say why. `verso scans` applies the tag on every open;
if you cut crops with your own Pillow script, call `ImageOps.exif_transpose` first.

**The tag is the phone's guess, and over a book lying flat it guesses wrong.** On one set of
phone albums it was wrong on most spreads and right on the odd single page. So a frame that
still lies sideways is DECLARED in `scans.toml` — `rotate` for the album, `rotate_frames` for a
frame shot differently (below). Upright is what the phone's own viewer shows: compare with it.
A phone's own format is decoded already turned, and pillow-heif keeps the old tag in
`info["original_orientation"]` only as a record of what was applied: applying it again turns
every frame twice (it would have put four years of one village's albums upside down).

**`check` before reading, always.** Two failures are invisible to a reader and expensive:
a page never photographed (the godparents of a whole spread simply absent), and a leaf
filed under the *wrong year* — one album held a лист belonging to another year, found
only after the year had been read once. Passing `--first/--last` from the project's record of
the дело catches the second; without them the check still catches gaps and doubles.
A gap in FRAME numbering is not a defect (the cover is frame 1 and the first leaf may be
frame 190); a missing folio SIDE is.

**A дело with gaps is completed, not read around.** When the дело is online whole (an
archive's reading room, an aggregator — the project's record of the дело has the link),
compare the frames with the case before reading: one set held 64 of the case's 92
scans, its filenames were shifted against the scan numbers (`317.jpeg` was scan 315), and the
missing 28 included a birth, two weddings and a burial of the family being swept. Find the
missing scans by matching each frame against the case's previews, download the originals and
add them to the frames without deleting anything (the AGENTS.md проекта names the
project's tools for its archives). An aggregator's OCR text is also the fastest way to LOCATE a
family in a whole case — search the surnames, then read every hit on the scan.

**Verso only.** The spread is `об` (left) + the next leaf's recto (right). The `об` page
carries the numbers, dates and the names of child + parents (ч. 1), the couple (ч. 2) or
the deceased (ч. 3). The recto carries godparents / sureties — and in ч. 3 it carries
«Отъ чего умеръ», «Кто исповѣдывалъ», «Кто совершалъ погребеніе» and **no names at all**,
so reading rectos in ч. 3 doubles the cost for nothing.

**Half pages, and only the columns with names in them.** A whole page at a readable scale
exceeds what the viewer shows and gets downscaled again; halves do not, and the two halves
overlap slightly so a record straddling the cut is whole in one of them. `--part` then drops
the счётъ and мѣсяцъ columns — **the same output size, a third bigger glyphs**, because those
columns carry no names. ч. 1 keeps «Имена родившихся» beside the parents, ч. 3 keeps the age
column (a burial is unusable without it), ч. 2 spans nearly the whole leaf.

**Checking a DSL номер against the book needs `--with-count`.** The счётъ column the presets
drop is the only thing that says WHICH record a row is, so verifying an attribution — as
opposed to reading a record already located — has to put the left edge back at 0. And read
the column HEADER before the numbers: ч. 1 runs **two series side by side** («Счетъ
родившихся: Мужескаго пола | Женскаго пола»), so «№ 15» legitimately appears twice in a
year, and the DSL's `(number, Gender)` pair is what disambiguates them. Taking the female
series for the male one is how a correct attribution got reported as an error.

**Reading is two-tier, and the second tier is not optional.** The part crop is enough to
LOCATE a record and not always enough to READ a name: on a 1.8× full-width sweep of 1887
«дочь **Платонида**» read as «дочь Пелагія», and the phantom contradiction with a birth three
weeks earlier cost more than the crops did. So: sweep to find, then **re-crop at 4–5× every
name that will enter the DSL** — not only the ones that change a conclusion.

**Handing the sweep to subagents** (measured on a reading benchmark): Opus at effort high, about
ten records per agent, the lean `verso-reading:scan-reader` for a sweep that only reports, and
`verso-reading:dsl-writer` straight from the scan for the DSL. For a long sweep, run
the readers from outside the repository, so that each starts with no project context (the
AGENTS.md проекта says whether the project has a launcher for that).

**When the ink fits two names, ask the святцы.** A child was named for a saint kept near
the birth or the christening (in one corpus 78 % of the births have one within ±7 days of the
christening, against 24 % for a random day).
`verso svyatcy near 1887-04-06 --gender F --like Пелагия` lists the names the Church kept around
that Julian day, most like your reading first — Платонида is kept on 6 April and nowhere else. It narrows the reading, it does not
make it: the re-crop still decides, and a name the святцы do not support is a reason to
look again, not to change what the ink says.

**`spread`, not two separate crops.** Aligning the recto band by eye is the most repeated
error of a reading session — crop 3% too low and you attribute another family's godparents.
`spread` takes the same y-band from both halves and stacks them: the row at a given height
on top is the same record as the row at that height below.

## `scans.toml` — what the album knows about itself

Finding one record on one лист costs several zooms of guesswork. What the album knows about
its own geometry is declared once in `scans.toml`, in the frames' directory (so the directory is
self-describing); `zoom` and `rows` also take `--layout FILE` or `--village DIR`, where a project
keeps the durable copy:

```toml
[album."Маниловка 1902"]
frames = "spread"       # the file is a spread though the NAME gives one лист
top = 0.19              # where the writing area begins; bottom = … as well
rotate_frames = { "кадр7" = 270 }
enhance = 1.7
```

- **`frames = "spread"`** is what makes the right-hand leaf exist at all. Some
  albums name a frame by its LEFT leaf (`47об.jpg` holds 47об and
  48), so without it every recto is reported missing and none can be addressed.
  These albums MIX — the opening leaves are single frames — and a page whose
  facing side has a file of its own is left alone, so the declaration is safe.
  So is a frame whose image STANDS (taller than wide, after its orientation tag
  and the album's `rotate`): a spread lies on its side, and some archives' albums
  shoot a blank or summary leaf alone among spreads — split, its «об» would be
  the right half of its own recto (`standing_frames`).
- **`top`/`bottom`** are what make `zoom --row N OF` land: the writing area starts at
  a different height in every дело, and a page whose last third is signatures
  divides into rows that are all too tall.
- **`rotate`** turns every frame that many degrees counter-clockwise on top of
  what the file declares; **`rotate_frames = { "кадр1" = 0, "кадр7" = 270 }`**
  gives a frame shot differently its own turn, keyed by the label `--folio`
  names (`кадр7`, `64об`). An entry REPLACES `rotate` rather than adding to it,
  so `0` declares the one frame the phone got right. Every command (`headers`,
  `crops`, `spread`, `zoom`) reads both, and every window is in fractions of
  the TURNED frame — so changing a declaration moves every window on its frames,
  and they must be turned with it.
- **`enhance`** is the push a faded hand needs; `zoom` takes it when no `--enhance` is given.
- **`village`**, in the frames' own copy, names the directory whose `scans.toml` is the durable
  one: `enhance` is asked there too. `--layout`, `--village` and `--album-title` override.

`verso scans` reads `scans.toml` and never writes it. A record's window, once found, is worth
keeping — a whole-дело sweep comes back to the same records. If the project has a tool that
remembers windows, it is named in the AGENTS.md проекта; without one, write the `--box` you
settled on into the project's notes on the дело.

```bash
verso scans rows $FR --part 1 --folio 47об 48об --out $SC/rows_47об.jpg   # where each record begins
verso scans zoom $FR --folio 47об --part 1 --row 3 8 --out $SC/z47об_3.jpg   # the 3rd of the page's 8
verso scans zoom $FR --folio 47об --box 0.18 0.44 0.60 0.97 --scale 9 --out $SC/z47об_3.jpg
```

⚠ **A reading of mine is not a finding.** Twice in one session a model read this kind
of hand wrong at 9–12× — one surname for another of the same shape, twice — and built a
conclusion on it, and each time the retraction cost more than the crop did. Cut the window,
show it, and let the person who knows the hand read it.

## Reading rules that are not about images

- **Read the year on the surnames the project's notes for the village name, AND on bare
  patronymics.** A род with street surnames is often written with no surname at all
  («Евлампій Агѣевъ безъ фамиліи»), and a surname written once in the plural covers every
  name in the list («Ѳирсъ Евлампіевъ и Мина Ѳирсовъ Маниловы»).
- **A part boundary tears a spread.** Sureties of the last marriages of ч. 2 would stand on
  the first leaf of ч. 3, where the printed title is — so they do not exist. Say so in the
  DSL rather than leaving it looking like an oversight.
- **An age in ч. 3 is a per-дело convention, and it can change between years of one дело.**
  One дело means years by a bare number in its later years — and months by one in an earlier year. Never carry
  the rule across a year without a check.
- **Cross-check the year against itself and against what is already read.** A child born and
  buried inside one book proves the age convention; an age in a later year points at a birth
  to look for. `verso death-age --village X` does this over the whole corpus after the year is
  written.
- **Verify every reading that changes a conclusion** by re-cropping at 4–16× before writing
  it. A single letter decided between two surnames for two years of records.

## After the reading

1. Write the DSL under `<village>/YYYY/` by the project's extraction rules (the AGENTS.md проекта
   names them per record kind).
2. `verso dsllint <village>/YYYY/*.py` — every DSL check in one run, and the file loads.
3. The project's own post-reading checks and generators (the AGENTS.md проекта lists them). Of the
   library's, `verso death-age` and `verso sibling-spacing` (validates every birth year you derived
   from a burial age) are the ones a newly read year most often trips; reading backwards, a new year
   almost always falsifies some primacy claim of the years already written.
4. Record the year's composition (part boundaries, inserted leaves, frame range) where the
   project keeps the record of the дело — the next year's `check --first/--last` depends on it.

## Limits

`verso scans` fetches nothing: it works on frames already on disk, and getting them there is the
project's (the AGENTS.md проекта). It needs Pillow only — `verso-core[scans]>=0.1.40`, and
`verso-core[heic]>=0.1.40` for a phone's own format; without them the pure parts (filenames, continuity,
the windows' arithmetic) still run.
