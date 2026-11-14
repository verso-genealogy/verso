"""Writing the transliteration's rules — what `verso translit add|remove` and the App's Dictionary do.

A rule is written into the layer `[names] writable` names (`verso.ru.naming.translit_layers`) after the layers' linter
reads it over the rules under it (`verso.ru.linters.checks.translit`): a hard finding refuses it and nothing is written.
One more refusal is the workspace's own: a rule of the profile that spells its **addresses** (`[translit] address`)
moves every res_name the word stands in, and a res_name is a Terraform address — so a rule of that profile is refused
while a generated tree of the workspace (`<village>/terraform/geni/*.tf`) holds a resource whose label carries the
word's spelling as it is now, and the refusal names the profile of display instead. A workspace with no tree — a new
one, a server's project — refuses nothing on that count.
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from verso.core import workspace
from verso.ru.linters.checks.translit import lint_rules
from verso.ru.messages import t
from verso.ru.naming import translit_layers
from verso.ru.naming.translit_layers import TranslitRule
from verso.ru.naming.transliteration import PROFILES, Role, generate_res_name, profile_of

ROLES: tuple[Role, ...] = ("address", "display")
_LABEL = re.compile(r'^resource "geni_\w+" "([^"]+)"', re.MULTILINE)


class RuleRefused(ValueError):
    """A rule not written: `code` and `params` say why (a linter's code, or `minted` / `no_rule`), the message in the
    interface's language."""

    def __init__(self, code: str, params: Mapping[str, object], message: str) -> None:
        super().__init__(message)
        self.code, self.params = code, dict(params)


@dataclass(frozen=True)
class RuleView:
    """A rule as the sum of the layers holds it: which layer gave it, whether it is that layer is writable, what the profile
    gives without it and whether it is redundant (it gives the same)."""
    profile: str
    word: str
    latin: str
    layer: str
    writable: bool
    profile_gives: str
    redundant: bool


@dataclass(frozen=True)
class Explanation:
    """One role's answer for a word: its profile, what the profile gives, the rule that spells it otherwise, the result."""
    role: Role
    profile: str
    profile_gives: str
    rule: RuleView | None
    result: str


def _view(ws: workspace.Workspace, rule: TranslitRule) -> RuleView:
    held = translit_layers.explain(ws, rule.profile, rule.word)
    layer = next((name for name, row in reversed(held) if row.latin is not None), held[-1][0] if held else "")
    writable = any(source.writable and source.name == layer for source in translit_layers.sources(ws))
    profile = PROFILES.get(rule.profile)
    gives = profile(rule.word) if profile is not None else ""
    return RuleView(rule.profile, rule.word, rule.latin or "", layer, writable, gives, gives == rule.latin)


def rules(ws: workspace.Workspace, profile: str | None = None) -> list[RuleView]:
    """Every rule of the sum, sorted by (profile, word); of one profile with `profile`."""
    return [_view(ws, rule) for key, rule in sorted(translit_layers.rules(ws).items())
            if profile is None or key[0] == profile]


def explain(ws: workspace.Workspace, word: str) -> list[Explanation]:
    """What each role does with `word`: its profile, what the profile gives, the rule of that profile if any, the result."""
    summed = translit_layers.rules(ws)
    out: list[Explanation] = []
    for role in ROLES:
        profile = profile_of(role)
        gives = profile(word)
        rule = summed.get((profile.name, word))
        view = _view(ws, rule) if rule is not None else None
        out.append(Explanation(role, profile.name, gives, view, view.latin if view is not None else gives))
    return out


def tree_labels(ws: workspace.Workspace) -> list[str]:
    """The labels of every resource of the workspace's generated trees (`<village>/terraform/geni/*.tf`), in order."""
    out: list[str] = []
    for village in ws.villages:
        tree = ws.root / village / "terraform" / "geni"
        if tree.is_dir():
            for tf in sorted(tree.glob("*.tf")):
                out.extend(_LABEL.findall(tf.read_text(encoding="utf-8")))
    return out


def minted_labels(ws: workspace.Workspace, profile: str, word: str, after: str | None = None) -> list[str]:
    """The resource labels a rule of `profile` for `word` would rename: none unless `profile` spells the workspace's
    addresses, nor when `after` — the word's Latin once the edit is made — gives the address it has now (a redundant rule
    added or taken away renames nothing); else each label of its trees holding the word's spelling as it is now as one of
    its `_`-parts."""
    if profile != profile_of("address").name:
        return []
    token = generate_res_name(word)
    if not token or (after is not None and generate_res_name(after) == token):
        return []
    return [label for label in tree_labels(ws) if token in label.split("_")]


def _refuse_minted(ws: workspace.Workspace, profile: str, word: str, after: str) -> None:
    minted = minted_labels(ws, profile, word, after)
    if minted:
        display = profile_of("display").name
        params = {"word": word, "count": len(minted), "example": minted[0], "display": display}
        text = t("translit_edit.minted", **params) if display != profile else t("translit_edit.minted_same", **params)
        raise RuleRefused("minted", params, str(text))


def _profile(profile: str | None) -> str:
    return profile or profile_of("display").name


def add_rule(ws: workspace.Workspace, word: str, latin: str, *, profile: str | None = None,
             dry_run: bool = False) -> RuleView:
    """Write the rule (profile, word) → latin into the writable layer — the profile of display by default — replacing its
    row of that key; refused (`RuleRefused`) on a hard finding of the layers' linter or a minted address."""
    profile = _profile(profile)
    source = translit_layers.writable(ws)
    rule = TranslitRule(profile, word, latin)
    below = _below(ws, source.name)
    for found in lint_rules([(0, rule)], below=below):
        if found.issue.level == "error":
            raise RuleRefused(found.issue.code, found.issue.params, str(found.issue.message))
    _refuse_minted(ws, profile, word, latin)
    if not dry_run:
        source.put(rule)
    return RuleView(profile, word, latin, source.name, True, PROFILES[profile](word), PROFILES[profile](word) == latin)


def remove_rule(ws: workspace.Workspace, word: str, *, profile: str | None = None, dry_run: bool = False) -> RuleView:
    """Take the rule (profile, word) away: the writable layer's row goes; a rule only a layer under it holds is taken away by
    a `-` row. Refused when no layer holds the rule, or when its profile spells minted addresses."""
    profile = _profile(profile)
    source = translit_layers.writable(ws)
    own = source.load().get((profile, word))
    below = _below(ws, source.name).get((profile, word))
    if (own is None or own.latin is None) and below is None:
        params = {"word": word, "profile": profile}
        raise RuleRefused("no_rule", params, str(t("translit_edit.no_rule", **params)))
    _refuse_minted(ws, profile, word, PROFILES[profile](word) if profile in PROFILES else "")
    gone = own if own is not None and own.latin is not None else below
    assert gone is not None and gone.latin is not None
    if not dry_run:
        if below is not None:
            source.put(TranslitRule(profile, word, None))
        else:
            source.remove((profile, word))
    gives = PROFILES[profile](word) if profile in PROFILES else ""
    return RuleView(profile, word, gone.latin, source.name, True, gives, gives == gone.latin)


def _below(ws: workspace.Workspace, layer: str) -> dict[translit_layers.Key, TranslitRule]:
    """The rules of the layers under `layer`, summed."""
    out: dict[translit_layers.Key, TranslitRule] = {}
    for source in translit_layers.sources(ws):
        if source.name == layer:
            break
        for key, rule in source.load().items():
            if rule.latin is None:
                out.pop(key, None)
            else:
                out[key] = rule
    return out


def migrate(ws: workspace.Workspace) -> tuple[Path, int]:
    """Move the corpus's `transliteration.toml` into the writable layer: each `[names]` entry a row of `ru-v1` (source
    `editor`), the file left for its owner to remove. The file and how many rows were written; nothing is written twice."""
    from verso.ru.naming.transliteration import RU_V1, TRANSLITERATION_FILE, _read_spellings  # pyright: ignore[reportPrivateUsage]
    if ws.translit is None:
        raise RuleRefused("schema", {}, str(t("translit_edit.needs_schema_7", config=ws.root / workspace.CONFIG)))
    if ws.corpus_dir is None or not (ws.corpus_dir / TRANSLITERATION_FILE).is_file():
        raise RuleRefused("no_file", {}, str(t("translit_edit.no_old_file", config=ws.root / workspace.CONFIG)))
    path = ws.corpus_dir / TRANSLITERATION_FILE
    source = translit_layers.writable(ws)
    held = source.load()
    written = 0
    for word, latin in _read_spellings(path).items():
        if (RU_V1.name, word) not in held:
            source.put(TranslitRule(RU_V1.name, word, latin))
            written += 1
    return path, written

