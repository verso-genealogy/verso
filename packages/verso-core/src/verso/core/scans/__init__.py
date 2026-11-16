"""The images of a scanned book: frames turned upright, a window cut, a faded hand made legible, sheets laid out.

What knows no language of the records and no numbering of a book: `image` opens a frame as the reader sees it
(its EXIF turn, a declared turn, the half of a spread) and writes a phone's HEIC as JPEG; `window` is a crop window
in fractions of the leaf; `level` turns a slanted record level; `look` is how an album's frames are rendered;
`stanza` reads an album's geometry from its `scans.toml` (it writes nothing: the windows are Verso's); `sheets`
lays strips out on one image. `verso scans` (`cli`) runs them; a plugin adds the subcommands that know its books'
numbering (`Plugin.scans`).

Pillow is the extra `[scans]` (`pip install 'verso-core[scans]'`), pillow-heif `[heic]`; each module imports them
where it uses them, so the pure arithmetic runs without either.
"""
