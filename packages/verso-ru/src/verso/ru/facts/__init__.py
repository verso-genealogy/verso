"""Source-neutral assertions extracted from the records, and rules over them.

The layer exists because knowledge of «who is in this record and in what role»
was written out independently in seven places, with four disagreeing role
vocabularies and five separate parsers recovering from a `res_name` string what
the translator had encoded into it. Here a record's shape is confined to one
extractor, and a rule joins predicates without knowing what kind of document
produced them.

Layered like `verso.ru.familio` and `verso.ru.timeline`, and — unlike them — checked:

    model       the vocabulary: Persona, Citation, Basis, the predicates.
                Stdlib only. GENTECH/GEDCOM X names, because the domain solved
                this twice and its words are better than ours would be.
    identity    what counts as one person. A parameter, not a policy baked into
                a rule: the repo currently holds three incompatible answers.
    extract/    DSL records → assertions. The ONLY layer that may import
                `verso.ru.dsl.records`, and one module per record kind.
    rules/      the questions. Import model + identity and nothing else; they
                take their predicates as TYPE PARAMETERS and may not name one.
    checks/     the policy of each question: which predicates it compares and
                the measured tolerances. May name predicates; no I/O.
    projection  bridges to `verso.core.targets.geni`: dates, and the identity bridge
                from an appearance to the canonical profile it was folded
                into (`consolidated_identity`). Pure.

All I/O — reading DSL files, writing reports — lives in `verso.ru.cli.facts`.
`tests/test_facts_layering.py` enforces every line of the above.
"""
