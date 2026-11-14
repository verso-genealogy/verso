"""Records v1: the built DSL records as JSON and back.

`fields` reads the table of every attribute the DSL objects hold — the plugin's vocabulary
since 0.1.0 (`plugins.dsl().vocabulary`; the Russian books' is `verso.ru.records`) —, `ids` names a record
as it is cited, `encode`/`decode` turn the objects into the records-v1 JSON and back,
`graph` compares two object graphs, `schema` builds `records-v1.json`. The codec is
pure — dicts and objects in and out; reading and writing files is `verso.core.pipeline.records`.
"""

SCHEMA_ID = "records-v1"


class FormatError(ValueError):
    """What the records v1 JSON cannot hold."""
