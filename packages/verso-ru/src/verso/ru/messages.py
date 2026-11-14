"""verso.ru's messages: `t("key", name=value)` is a message of the plugin's catalogs
(`verso/ru/locales/<lang>.toml`), in the workspace's language (`verso.core.messages`)."""
from __future__ import annotations

import verso.core.workspace  # noqa: F401 — the workspace says the language (verso.core.i18n.configure)
from verso.core.i18n import Message

PACKAGE = "verso.ru"


def t(key: str, /, **params: object) -> Message:
    return Message(PACKAGE, key, params)


def form(kind: str, id_: str, case: str = "nom") -> Message:
    """A word's form from the catalog's table `forms.<kind>.<id>`: `form("role", "husband",
    "gen")` is «мужа» in Russian. A case the language does not keep falls back to its `nom`."""
    return Message(PACKAGE, f"forms.{kind}.{id_}.{case}", {})
