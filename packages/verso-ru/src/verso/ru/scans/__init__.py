"""The scan tools that read a metric book's numbering: a photographed дело's filenames by лист (`folio`), the part's
columns and a record's row (`zoom`), where each record of a leaf begins (`rows`), an album's pages and their images
(`album`) — and the subcommands of `verso scans` they make (`cli`: check, headers, crops, spread, zoom, rows, cards).

Over the core's (`verso.core.scans`: the frame upright, the window, the look, the stanza of `scans.toml`). Nothing
here imports the DSL or the domain, and nothing of them imports this.
"""
