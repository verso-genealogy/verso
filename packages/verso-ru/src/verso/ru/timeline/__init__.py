"""Genealogy timeline exporter — the consolidated domain model rendered as a
self-contained HTML page.

A third publishing target alongside geni and familio, and a read-only one: it
never touches terraform state, it just draws what the records already say. One
horizontal thread per person from birth to death, threads converging at
marriages, children emerging from their parents' shared lane, historical bands
behind.

Layered like `verso.ru.familio` — pure policy (`projection`), pure geometry
(`layout`), pure rendering (`render`), with all I/O confined to
`verso.ru.cli.generate_timeline`.
"""
