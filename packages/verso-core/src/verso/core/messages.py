"""verso.core's messages: `t("key", name=value)` is a message of the core's catalogs
(`verso/core/locales/<lang>.toml`), rendered in the language of the moment it is read
(`verso.core.i18n`). Where the language comes from — the workspace's `[i18n] locale` and `packs` —
`verso.core.workspace` tells the mechanism when it is imported; before that, and without a
workspace, it is `VERSO_LANG`, else English.
"""
from __future__ import annotations

from verso.core.i18n import Message

PACKAGE = "verso.core"


def t(key: str, /, **params: object) -> Message:
    return Message(PACKAGE, key, params)
