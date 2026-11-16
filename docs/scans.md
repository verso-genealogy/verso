# The scan tools

**English** · [Русский](scans.ru.md)

`verso scans` works on the frames of a scanned book already on disk — a directory of an album's images, as an
archive's reading room or a phone gave them. It verifies the album is whole, finds where the book's parts begin,
cuts the pages into crops that read, lines a spread's two pages up row for row, zooms one record, and finds where
each record of a leaf begins. It fetches nothing and writes no window into `scans.toml`: getting the frames onto disk
(a photo library, a cloud folder) and remembering windows are the review page's (Verso).

## Install

The tools need Pillow, the extra `scans` of verso-core; a phone's HEIC frames need pillow-heif as well, the extra
`heic`. Without them the pure parts (filenames, continuity, the windows' arithmetic) still import and run.

```bash
pip install 'verso-core[scans]'    # JPEG, PNG, TIFF
pip install 'verso-core[heic]'     # and HEIC
```

## Subcommands

`verso scans --help` lists them: the core's first, then each installed plugin's (`Plugin.scans`, [plugins](plugins.md)).
`DIR` is a directory of frames. Every window is given in fractions of the frame or the leaf (0..1), never in pixels:
the frames of one дело drift by a few pixels in size.

| Subcommand | Package | Writes | Exit |
|---|---|---|---|
| `strips ALBUM --box X0,Y0,X1,Y1 --out DIR [--frames FIRST-LAST] [--per 20] [--size 900]` | core | `strips_<first>-<last>.jpg`, each path printed | 0; 2 when there is no album or no frame |
| `quadrants IMAGE… --out DIR` | core | `<stem>_{tl,tr,bl,br}.png`, upscaled 3× | 0 |
| `descreen IMAGE [l,t,r,b\|-] [SCALE] [MODE] [ROT]` | core | `<dir of IMAGE>/crops/<stem>_<box>_<scale>_<mode>_<rot>.png`, its path and size printed | 0 |
| `jpeg DIR` | core | each HEIC of DIR as a JPEG of the same name, quality 92, turned upright; the HEIC removed | 1 when a frame was not written |
| `check DIR [--first N] [--last N]` | ru | a report: the leaves the album covers, a side absent or doubled, a leaf outside the inventory's range | 1 on any defect |
| `headers DIR --out OUT [--strip 0.17] [--rows 8] [--frames]` | ru | `headers_NN.jpg`, contact sheets of the running headers | 0 |
| `crops DIR --out OUT [--verso-only] [--part 1\|2\|3] [--from N] [--to N] [--with-count] [--x0] [--x1] [--scale] [--top 0.07] [--grey] [--enhance N] [--frames]` | ru | `<frame:04d>_<leaf>_{a,b}.jpg`, half-page crops | 0 |
| `spread DIR --folio 120об [--band 0.07 0.56] [--scale 2.6] [--enhance N] [--out F]` | ru | `spread_<leaf>_<y0>-<y1>.jpg` in DIR: an об page's band over the facing recto's | 1 when the album has no leaf numbers, or no such page |
| `zoom DIR --folio F [--part] [--col] [--row N OF] [--box X0 Y0 X1 Y1] [--scale 6] [--top 0.17] [--pad 0.02] [--colour] [--enhance N] [--frames] [--tag a] [--out F] [--layout F] [--village DIR] [--album-title T]` | ru | `zoom_<leaf>_<tag>.jpg` in DIR: one record, grey and autocontrasted | 1 when there is no such page or the window does not read |
| `rows DIR --part N --folio F… [--x0] [--x1] [--count X0 X1] [--top] [--bottom] [--layout] [--village] [--album-title] [--out] [--frames]` | ru | `rows_<first>[-<last>]_<part>.jpg` in DIR: each leaf's marks and cuts drawn; the marks printed | 1 on a leaf that does not read, or no such page |
| `cards ALBUM OUT [--header B] [--table B] [--number B] [--leaf B] [--zoom IDX:x0:y0:x1:y1]` | ru | `NN.jpg`, `numbers.jpg`, `leaves.jpg` (or `zoom_NN.jpg`) of the 1917 farm-census cards | 1 when ALBUM holds no image |

An argument argparse cannot read exits 2, as every command of `verso` does.

A frame of verso-ru's albums is named `<frame>_<leaf>.jpg` — `0118_57.jpg`, `0119_57об.jpg`, a spread
`0241(131об-132).jpg` — and its pages are read by leaf. An album that still carries a phone's names (`IMG_0001.jpg`)
is read by position instead («кадр 12»), which verifies nothing; `--frames` asks for that numbering outright.

## What is read from `scans.toml`

The album's stanza, `[album."<title>"]`, is read and never written:

| Key | What it does |
|---|---|
| `frames` | `"spread"`: a frame named by one leaf holds the facing side too — a frame standing up stays one page (`check`, `headers`, `crops`, `spread`, `zoom`, `rows`) |
| `top`, `bottom` | where the writing begins and ends, as fractions of the leaf (`zoom`, `rows`) |
| `rotate`, `rotate_frames` | the turn on top of the frame's own EXIF tag, for the album and per page |
| `enhance` | the push a faded hand needs (`zoom`, when no `--enhance` is given) |
| `village` | in an album's own copy, the directory whose `scans.toml` is the durable one: `enhance` is asked there too |

Every other key — the windows (`[[album."…".box]]`), the columns, the look's other keys, the source — is passed over.
`check`, `headers`, `crops` and `spread` read the album directory's own `scans.toml`, and its only album: they take
no flag that names another file or a title. `zoom` and `rows` read the one `--layout` names, else the album's own,
else `--village`'s; the title is `--album-title` (exact, or the one album whose title contains it), else the file's
only album. Under `frames = "spread"` a window's fractions are of the leaf — the half of the frame it lies on — in
every subcommand; `--frames` reads frames by position and leaves them whole. `check` expects such an album's sides
from its first to its last: the recto before the first spread's left leaf and the verso after the last spread's
right leaf are the neighbouring albums'. A `scans.toml` that does not read as TOML is refused in a line, exit 2.

The windows are the review page's: Verso writes them, and `verso-scans` (the App's) remembers one with
`zoom --record --remember` or a leaf's at once with `windows`. `verso scans rows` finds the marks and draws them; it
writes nothing.

## In Python

The modules' `__all__` is public ([compatibility](compatibility.md)):

| Module | What it gives |
|---|---|
| `verso.core.scans.image` | `open_upright`, `turn_upright`, `cut_half`, `upright_size`, `turned_frame_size`, `image_names`, `heic_to_jpeg`, `convert_heic_frames`, `heic_clashes`, `pil`; `IMAGE_SUFFIXES`, `HEIC_SUFFIXES` |
| `verso.core.scans.window` | `Box`, a window in fractions; `FULL_WIDTH` |
| `verso.core.scans.level` | `turn`, `turned_size`, `level_crop`, `line_angle` |
| `verso.core.scans.look` | `Look`, `legible`, `coloured_ink`; `PLAIN`, `INKS`, `MAX_ENHANCE` |
| `verso.core.scans.stanza` | `Stanza`, `StanzaError`, `for_album`, `rotation`, `enhance_for` |
| `verso.core.scans.sheets` | `contact_sheet`, `strips_sheet`, `fit_width` |
| `verso.ru.scans.folio` | `Page`, `parse_album`, `parse_frame`, `frame_pages`, `check_album`, `format_report`, `expand_spreads`, `renumber_scans`; `FRAME_PREFIX`, `VERSO_SUFFIX` |
| `verso.ru.scans.zoom` | `COLUMNS`, `DEFAULT_TOP`, `column_window`, `row_band`, `resolve` |
| `verso.ru.scans.rows` | `detect`, `count_window`, `ruler`, `sheet`, `parse_keys`, `pair`, `cuts_from` |
| `verso.ru.scans.album` | `load_pages`, `open_page`, `page_size`, `find`, `page_named`, `where`, `titled`, `note_frame_mode`, `album_of`, `spread_frames` |
| a subcommand's module, `verso.core.scans.cli.<sub>`, `verso.ru.scans.cli.<sub>` | `HELP`, `add_arguments`, `run` (`Plugin.scans`); `verso.ru.scans.cli.rows` also `leaf`, `report`; `verso.ru.scans.cli.zoom` also `locate`, `cut`, `Target` — the page found, then a window cut from it, which a caller may hand its own window and turn |
| `verso.ru.scans.cli` | `add_frames_flag`, `add_enhance_flag` |
| `verso.core.scans.cli` | `main`, `verso scans` itself |

Nothing else of these modules is public — a value of a type they do not list (`Stanzas`, `Rows`) is read by its
attributes, not imported.
