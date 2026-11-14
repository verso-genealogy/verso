"""Loading a village and translating it: what every reader of the corpus starts from.

Moved out of the CLI before 0.1.0, which had done it for everyone — the consolidation checks and
Verso among them. Each module rests only on those before it:

* `load` — a DSL file as a module, a village's record sets in the translator's order,
  the review ratchet's admission;
* `config` — a village's `generate_config_names.py` as a module, its `Consolidation` and
  the state-continuity blocks it generates;
* `translate` — a village's record sets fed to a `TerraformGenerator`;
* `facts` — one translation's assertions and the bridge from each to its canonical.

No argument parsing and nothing on stdout; a file that does not import is a warning on
stderr, as `discover_records` prints it.
"""
