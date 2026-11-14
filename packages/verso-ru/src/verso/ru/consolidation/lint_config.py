#!/usr/bin/env python3
"""Static linter for a village's generate_config_names.py.

Catches silent-failure patterns in the `profiles_to_consolidate` and
`unions_to_consolidate` dict literals — duplicate keys, invalid schema
keys, invalid `GeniProfile(...)` kwargs, and missing/malformed fields — and in
the `profiles_to_consolidate.update({...})` blocks, read together with the
literal (see `UPDATE_BLOCK_EXEMPT` for the two style rules they are spared).

The file is parsed with `ast`, never imported: importing it executes
~25k lines of dict construction and would mask the exact bugs this
linter targets (Python silently overwrites duplicate dict keys at
literal-eval time).

Exit status: 1 if any error-severity finding is reported, else 0.
"""

from __future__ import annotations

import ast
import json
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from collections.abc import Iterable, Iterator

PROFILES_VAR = "profiles_to_consolidate"
UNIONS_VAR = "unions_to_consolidate"

PROFILE_SCHEMA_KEYS = {
    "profile_names",
    "additional_info",
    "override",
    "preference",
    "ignore",
    "lifecycle_ignore_changes",
    "generate_moved_block",
    "keeper",
    "adopt_external",
}

UNION_SCHEMA_KEYS = {
    "union_names",
    "undocumented_children",
    "undocumented_partner",
    "exclude_children",
    "override",
}

# Mirror of geni_profile.GeniProfile.__init__ signature. Kept in sync
# manually; CCN006 fails closed (unknown kwarg) so drift here surfaces
# as a false positive rather than silently allowing real bugs.
GENI_PROFILE_FIELDS = {
    "res_name", "gender", "first_name", "middle_name", "last_name",
    "birth_last_name", "nicknames", "title", "alive", "public",
    "birth", "baptism", "death", "burial", "cause_of_death",
    "current_residence", "occupation", "projects", "about",
    "source_date", "source", "sources",
}

# kwarg → suggested replacement for common typos.
GENI_PROFILE_KWARG_FIXES = {
    "maiden_name": "birth_last_name",
    "maidenname": "birth_last_name",
    "birthname": "birth_last_name",
    "first": "first_name",
    "last": "last_name",
    "middle": "middle_name",
}


@dataclass(frozen=True)
class Finding:
    code: str
    severity: str  # "error" | "warning"
    path: str
    line: int
    col: int
    message: str

    def format_text(self) -> str:
        return f"{self.path}:{self.line}:{self.col}: {self.severity} {self.code} {self.message}"


def _const_str(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _find_assign(tree: ast.Module, var_name: str) -> ast.Dict | None:
    """The top-level `<var_name> = {...}` dict, annotated or not.

    `ast.AnnAssign` counts: a config may spell the dict with a type annotation
    (`unions_to_consolidate: dict[str, object] = {`, as Маниловка does), and
    matching only `ast.Assign` made those configs invisible. The unions branch
    skips silently when this returns None, so the whole village went unchecked
    with nothing going red.
    """
    for node in tree.body:
        if isinstance(node, ast.Assign):
            if (
                len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == var_name
                and isinstance(node.value, ast.Dict)
            ):
                return node.value
        elif isinstance(node, ast.AnnAssign):
            if (
                isinstance(node.target, ast.Name)
                and node.target.id == var_name
                and isinstance(node.value, ast.Dict)
            ):
                return node.value
    return None


def _iter_geni_profile_calls(node: ast.AST) -> Iterator[ast.Call]:
    """Yield every `GeniProfile(...)` call anywhere under `node`."""
    for descendant in ast.walk(node):
        if (
            isinstance(descendant, ast.Call)
            and isinstance(descendant.func, ast.Name)
            and descendant.func.id == "GeniProfile"
        ):
            yield descendant


def _check_names_not_canonical(
    *,
    path: str,
    cluster_key: str,
    value_node: ast.Dict,
    names_field: str,
    canonical_keys: set[str],
) -> Iterator[Finding]:
    """CCN008: no names-list element may be a canonical consolidation key.

    An element that matches a canonical key of a *different* cluster is a
    double-consolidation — that stub would be folded in two places at once.

    A cluster's *own* key is exempt in exactly one case: a **single-element**
    list (`{"X": {"profile_names": ["X"]}}`). That is a passthrough — one raw
    stub declared canonical with no merge — so a CSV-only village (e.g.
    Заманиловка) may keep the raw stub as the key. But once a cluster **merges
    2+ stubs**, its key must be a *new synthetic canonical name*, never one of
    the raw stubs being merged; a self-key inside a multi-element list is flagged.
    """
    names_node: ast.AST | None = None
    for k, v in zip(value_node.keys, value_node.values, strict=False):
        if _const_str(k) == names_field:
            names_node = v
            break

    if names_node is None or not isinstance(names_node, ast.List):
        return

    is_passthrough = len(names_node.elts) == 1

    for elt in names_node.elts:
        name = _const_str(elt)
        if name is None:
            continue
        if name not in canonical_keys:
            continue
        if name == cluster_key:
            if is_passthrough:
                continue
            message = (
                f"cluster {cluster_key!r}: merges {len(names_node.elts)} stubs, so its "
                "canonical key must be a new synthetic name, not its own raw stub "
                f"{name!r}"
            )
        else:
            message = (
                f"cluster {cluster_key!r}: {names_field!r} entry {name!r} refers to "
                "another cluster's canonical key — a stub cannot be consolidated twice"
            )
        yield Finding(
            code="CCN008",
            severity="error",
            path=path,
            line=elt.lineno,
            col=elt.col_offset,
            message=message,
        )


def _is_truthy_const(node: ast.AST | None) -> bool:
    """Mirror the generator's `entry.get(...)` truthiness on a literal."""
    return isinstance(node, ast.Constant) and bool(node.value)


def _check_keeper(
    *,
    path: str,
    cluster_key: str,
    value_node: ast.Dict,
) -> Iterator[Finding]:
    """CCN012/CCN013: the `keeper` pin must be read, and must name a record.

    `keeper` has exactly one read site — `build_moved_consolidated_profiles`
    (`verso/ru/cli/generate_tf.py`) — reached only for an entry that carries
    `generate_moved_block: True`, declares a non-empty `profile_names`, and is
    not `adopt_external` (which takes the removed-only branch before the keeper
    is consulted). Anywhere else the pin is dead text.

    * **CCN012** — the pin is never read. Not cosmetic: the whole point of a
      keeper is to say which record's Geni id survives onto the canonical, and
      an unread pin means the generator silently falls back to
      `profile_names[0]`. A canonical key (`canonical_a`) carried a
      six-line comment justifying its keeper and never had the flag.
    * **CCN013** — the pin is read but names no declared record, so the
      generated `moved` points from an address this cluster does not manage and
      *every* declared record gets `removed{destroy=false}`: nothing carries the
      surviving id onto the canonical. A canonical (`canonical_b`) pinned one
      spelling of a given name while every stub reads another.

    The two are mutually exclusive by design — an unread dangling pin is one
    problem with one fix (delete the key, or add the flag and *then* answer
    CCN013), not two findings.
    """
    fields: dict[str, ast.expr] = {}
    for k, v in zip(value_node.keys, value_node.values, strict=False):
        name = _const_str(k)
        if name is not None:
            fields[name] = v

    keeper_node = fields.get("keeper")
    if keeper_node is None:
        return
    keeper = _const_str(keeper_node)

    gmb_node = fields.get("generate_moved_block")
    adopt_node = fields.get("adopt_external")
    # A non-literal flag is unknowable statically; stay silent rather than guess.
    if (gmb_node is not None and not isinstance(gmb_node, ast.Constant)) or (
        adopt_node is not None and not isinstance(adopt_node, ast.Constant)
    ):
        return

    names_node = fields.get("profile_names")
    names = (
        [n for n in (_const_str(e) for e in names_node.elts) if n is not None]
        if isinstance(names_node, ast.List)
        else []
    )

    is_read = _is_truthy_const(gmb_node) and bool(names) and not _is_truthy_const(adopt_node)

    if not is_read:
        if _is_truthy_const(adopt_node):
            why = "'adopt_external' takes the removed-only branch before the keeper is read"
        elif not names:
            why = "the entry declares no 'profile_names'"
        else:
            why = "the entry has no \'generate_moved_block\': True"
        yield Finding(
            code="CCN012",
            severity="error",
            path=path,
            line=keeper_node.lineno,
            col=keeper_node.col_offset,
            message=(
                f"cluster {cluster_key!r}: 'keeper' is never read — {why}. "
                "The keeper pin only reaches the generator via "
                "build_moved_consolidated_profiles; without it the moved block "
                "falls back to profile_names[0]. Add the flag to realise the "
                "pin, or drop the dead key"
            ),
        )
        return

    if keeper is not None and keeper not in names:
        yield Finding(
            code="CCN013",
            severity="error",
            path=path,
            line=keeper_node.lineno,
            col=keeper_node.col_offset,
            message=(
                f"cluster {cluster_key!r}: keeper {keeper!r} is not in "
                "'profile_names' — the generated `moved` would point from an "
                "address this cluster does not manage, and every declared record "
                "would get removed{destroy=false}, so nothing carries the "
                "surviving Geni id onto the canonical"
            ),
        )


def _collect_canonical_keys(dict_node: ast.Dict) -> set[str]:
    """Return the set of all string-literal top-level keys in *dict_node*.

    Used by CCN008 to detect forward and backward references: we need the
    complete key set before we start the per-entry loop.
    """
    result: set[str] = set()
    for key_node in dict_node.keys:
        k = _const_str(key_node)
        if k is not None:
            result.add(k)
    return result


def _check_top_dict(
    *,
    path: str,
    var_name: str,
    dict_node: ast.Dict,
    allowed_value_keys: set[str],
    requires_profile_names: bool,
) -> Iterator[Finding]:
    """Run CCN001–CCN014 against a top-level dict literal."""
    seen_keys: dict[str, ast.expr] = {}
    # CCN002 needs to know every stub across every cluster.
    stub_to_cluster: dict[str, str] = {}
    # CCN008: pre-collect all canonical keys (handles forward references).
    canonical_keys = _collect_canonical_keys(dict_node)
    # Determine which names-list field to check for CCN008.
    names_field = "profile_names" if requires_profile_names else "union_names"

    for key_node, value_node in zip(dict_node.keys, dict_node.values, strict=False):
        key = _const_str(key_node)
        if key is None:
            # Non-string top-level key: hard to call without context;
            # skip with a generic note rather than crash.
            yield Finding(
                code="CCN000",
                severity="error",
                path=path,
                line=getattr(key_node, "lineno", 0) or 0,
                col=getattr(key_node, "col_offset", 0) or 0,
                message=f"{var_name} key is not a string literal",
            )
            continue

        # CCN001: duplicate canonical key.
        if key in seen_keys:
            first = seen_keys[key]
            yield Finding(
                code="CCN001",
                severity="error",
                path=path,
                line=key_node.lineno,
                col=key_node.col_offset,
                message=(
                    f"duplicate canonical key {key!r} in {var_name} "
                    f"(first defined at line {first.lineno}); "
                    "Python dict literals silently overwrite — rename one to a `_2` suffix"
                ),
            )
            continue
        assert key_node is not None  # a string key implies a non-None Constant node
        seen_keys[key] = key_node

        if not isinstance(value_node, ast.Dict):
            yield Finding(
                code="CCN004",
                severity="error",
                path=path,
                line=value_node.lineno,
                col=value_node.col_offset,
                message=f"{var_name}[{key!r}] value must be a dict literal",
            )
            continue

        # CCN014: the same key twice inside one cluster. Python dict literals
        # keep the LAST occurrence and discard the earlier one without a word,
        # so a pin pasted above an existing one simply stops existing — the
        # generator then keeps reporting the very conflict the pin resolves,
        # and nothing points at the config. Reported before the schema checks
        # below, whose own dict comprehension collapses the duplicate the same
        # way Python does.
        dup_seen: dict[str, ast.expr] = {}
        for k_node in value_node.keys:
            vk = _const_str(k_node)
            if vk is None:
                continue
            first = dup_seen.get(vk)
            if first is None:
                dup_seen[vk] = k_node
                continue
            yield Finding(
                code="CCN014",
                severity="error",
                path=path,
                line=k_node.lineno,
                col=k_node.col_offset,
                message=(
                    f"duplicate key {vk!r} in {var_name}[{key!r}] "
                    f"(first defined at line {first.lineno}); Python keeps the "
                    "LAST one and silently drops the earlier — merge them into "
                    "a single entry"
                ),
            )

        value_keys = {
            _const_str(k): k for k in value_node.keys if _const_str(k) is not None
        }

        # CCN005: unknown schema keys.
        for vk, vk_node in value_keys.items():
            if vk not in allowed_value_keys:
                yield Finding(
                    code="CCN005",
                    severity="error",
                    path=path,
                    line=vk_node.lineno,
                    col=vk_node.col_offset,
                    message=(
                        f"unknown key {vk!r} in {var_name}[{key!r}]; "
                        f"allowed: {sorted(allowed_value_keys)}"
                    ),
                )

        # CCN004: required key + shape checks.
        if requires_profile_names:
            yield from _check_profile_names(
                path=path,
                cluster_key=key,
                value_node=value_node,
                stub_to_cluster=stub_to_cluster,
            )

        # CCN006: validate GeniProfile(...) kwargs inside the value.
        yield from _check_geni_profile_calls(path=path, cluster_key=key, value_node=value_node)

        # CCN011: `ignore` must not name the value its own `preference` pins.
        yield from _check_preference_ignore_collision(
            path=path, cluster_key=key, value_node=value_node
        )

        # CCN007: generate_moved_block must be a bool.
        for vk, vk_node in value_keys.items():
            if vk == "generate_moved_block":
                idx = list(value_node.keys).index(vk_node)
                val = value_node.values[idx]
                if not (isinstance(val, ast.Constant) and isinstance(val.value, bool)):
                    yield Finding(
                        code="CCN007",
                        severity="error",
                        path=path,
                        line=val.lineno,
                        col=val.col_offset,
                        message=(
                            f"{var_name}[{key!r}]['generate_moved_block'] must be a bool literal"
                        ),
                    )

        # CCN012/CCN013: the `keeper` pin must be read, and must name a record.
        yield from _check_keeper(path=path, cluster_key=key, value_node=value_node)

        # CCN008: names-list entries must be raw source stubs, not canonical keys.
        yield from _check_names_not_canonical(
            path=path,
            cluster_key=key,
            value_node=value_node,
            names_field=names_field,
            canonical_keys=canonical_keys,
        )


def _check_profile_names(
    *,
    path: str,
    cluster_key: str,
    value_node: ast.Dict,
    stub_to_cluster: dict[str, str],
) -> Iterator[Finding]:
    pn_node: ast.AST | None = None
    for k, v in zip(value_node.keys, value_node.values, strict=False):
        if _const_str(k) == "profile_names":
            pn_node = v
            break

    if pn_node is None:
        yield Finding(
            code="CCN004",
            severity="error",
            path=path,
            line=value_node.lineno,
            col=value_node.col_offset,
            message=f"cluster {cluster_key!r} missing required 'profile_names'",
        )
        return

    if not isinstance(pn_node, ast.List):
        yield Finding(
            code="CCN004",
            severity="error",
            path=path,
            line=pn_node.lineno,
            col=pn_node.col_offset,
            message=f"cluster {cluster_key!r}: 'profile_names' must be a list literal",
        )
        return

    if not pn_node.elts:
        yield Finding(
            code="CCN004",
            severity="error",
            path=path,
            line=pn_node.lineno,
            col=pn_node.col_offset,
            message=f"cluster {cluster_key!r}: 'profile_names' must not be empty",
        )
        return

    seen_in_cluster: dict[str, ast.expr] = {}
    for elt in pn_node.elts:
        name = _const_str(elt)
        if name is None:
            yield Finding(
                code="CCN004",
                severity="error",
                path=path,
                line=elt.lineno,
                col=elt.col_offset,
                message=(
                    f"cluster {cluster_key!r}: 'profile_names' entries must be string literals"
                ),
            )
            continue

        # CCN003: duplicate within the same cluster.
        if name in seen_in_cluster:
            first = seen_in_cluster[name]
            yield Finding(
                code="CCN003",
                severity="error",
                path=path,
                line=elt.lineno,
                col=elt.col_offset,
                message=(
                    f"cluster {cluster_key!r}: profile_name {name!r} listed twice "
                    f"(first at line {first.lineno})"
                ),
            )
            continue
        seen_in_cluster[name] = elt

        # CCN002: cross-cluster duplicate.
        if name in stub_to_cluster:
            yield Finding(
                code="CCN002",
                severity="error",
                path=path,
                line=elt.lineno,
                col=elt.col_offset,
                message=(
                    f"profile_name {name!r} appears in two clusters: "
                    f"{stub_to_cluster[name]!r} and {cluster_key!r}"
                ),
            )
            continue
        stub_to_cluster[name] = cluster_key

    # CCN009: profile_names must be sorted. Matches the ordering written by
    # `detector.py --write` (Python lexicographic on the date-prefixed
    # record names, so chronological), so a real fold is a one-line insertion
    # rather than a full re-alphabetization. Run `verso detector --normalize-sort` to fix.
    names_in_order = [n for n in (_const_str(e) for e in pn_node.elts) if n is not None]
    if names_in_order != sorted(names_in_order):
        yield Finding(
            code="CCN009",
            severity="error",
            path=path,
            line=pn_node.lineno,
            col=pn_node.col_offset,
            message=(
                f"cluster {cluster_key!r}: 'profile_names' is not sorted; "
                "run `verso detector --config <village>/generate_config_names.py --normalize-sort` "
                "(verso.ru.consolidation.detector --normalize-sort)"
            ),
        )


def _string_kwargs(call: ast.Call) -> dict[str, ast.expr]:
    """Constant-string keyword arguments of a `GeniProfile(...)` call."""
    out: dict[str, ast.expr] = {}
    for kw in call.keywords:
        if kw.arg and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
            out[kw.arg] = kw.value
    return out


def _cluster_value(value_node: ast.Dict, name: str) -> ast.expr | None:
    for k, v in zip(value_node.keys, value_node.values, strict=True):
        if _const_str(k) == name:
            return v
    return None


def _check_preference_ignore_collision(
    *, path: str, cluster_key: str, value_node: ast.Dict
) -> Iterator[Finding]:
    """CCN011: `ignore` must not list the value its own `preference` pins.

    The keys pull opposite ways on one field: `preference` names the value to
    KEEP, `ignore` names a value to DROP wherever seen. The generator's seed
    scrub (`generator.py` `_merge_consolidated`) runs AFTER `_apply_preference`,
    so an `ignore` naming the pinned value blanks it on the seed record; the
    next record carrying the *rejected* variant then fills the blank and wins.
    The config silently produces the exact value it set out to reject.
    """
    pref_node = _cluster_value(value_node, "preference")
    ignore_node = _cluster_value(value_node, "ignore")
    if pref_node is None or ignore_node is None:
        return
    if not (isinstance(pref_node, ast.Call) and isinstance(ignore_node, ast.List)):
        return
    pinned = _string_kwargs(pref_node)
    if not pinned:
        return
    for elt in ignore_node.elts:
        if not isinstance(elt, ast.Call):
            continue
        for field, node in _string_kwargs(elt).items():
            pinned_node = pinned.get(field)
            if pinned_node is None:
                continue
            assert isinstance(node, ast.Constant) and isinstance(pinned_node, ast.Constant)
            if node.value != pinned_node.value:
                continue
            yield Finding(
                code="CCN011",
                severity="error",
                path=path,
                line=node.lineno,
                col=node.col_offset,
                message=(
                    f"cluster {cluster_key!r}: ignore {field}={node.value!r} names the same "
                    f"value preference pins ({field}={pinned_node.value!r}) — the seed scrub "
                    f"runs after the preference is applied, so this blanks the pinned value "
                    f"and lets the rejected variant win. Ignore the variant you want DROPPED, "
                    f"or drop the `ignore` entry"
                ),
            )


def _check_geni_profile_calls(
    *, path: str, cluster_key: str, value_node: ast.Dict
) -> Iterator[Finding]:
    for call in _iter_geni_profile_calls(value_node):
        if call.args:
            yield Finding(
                code="CCN006",
                severity="error",
                path=path,
                line=call.lineno,
                col=call.col_offset,
                message=(
                    f"cluster {cluster_key!r}: GeniProfile(...) called with positional "
                    "arguments; all fields are keyword-only by convention"
                ),
            )
        for kw in call.keywords:
            if kw.arg is None:
                yield Finding(
                    code="CCN006",
                    severity="error",
                    path=path,
                    line=kw.value.lineno,
                    col=kw.value.col_offset,
                    message=(
                        f"cluster {cluster_key!r}: GeniProfile(**kwargs) splat is not allowed; "
                        "pass fields explicitly"
                    ),
                )
                continue
            if kw.arg in GENI_PROFILE_FIELDS:
                continue
            suggestion = GENI_PROFILE_KWARG_FIXES.get(kw.arg)
            hint = f" — did you mean {suggestion!r}?" if suggestion else ""
            yield Finding(
                code="CCN006",
                severity="error",
                path=path,
                line=kw.value.lineno,
                col=kw.value.col_offset,
                message=(
                    f"cluster {cluster_key!r}: GeniProfile({kw.arg}=...) is not a valid field"
                    f"{hint}"
                ),
            )

        # CCN010: a nickname must not repeat a surname field. `preference` pins
        # the KEPT value per field and `nicknames` preserves the DROPPED
        # variants, so a value in both is a contradiction — Geni renders the
        # surname twice. When the dropped value is already carried by another
        # name field (a married surname kept as last_name while the maiden wins
        # birth_last_name), the right tool is `ignore`, not a nickname.
        kwargs = {kw.arg: kw for kw in call.keywords if kw.arg}
        nick_kw = kwargs.get("nicknames")
        nicknames: dict[str, ast.expr] = {}
        if nick_kw is not None and isinstance(nick_kw.value, ast.List):
            for elt in nick_kw.value.elts:
                if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                    nicknames[elt.value] = elt
        for field in ("last_name", "birth_last_name"):
            fkw = kwargs.get(field)
            if fkw is None or not isinstance(fkw.value, ast.Constant):
                continue
            val = fkw.value.value
            if not isinstance(val, str) or val not in nicknames:
                continue
            elt = nicknames[val]
            yield Finding(
                code="CCN010",
                severity="error",
                path=path,
                line=elt.lineno,
                col=elt.col_offset,
                message=(
                    f"cluster {cluster_key!r}: nickname {val!r} duplicates "
                    f"{field}={val!r} — drop it from nicknames (a value already "
                    f"carried by a name field must not repeat as an alias; if it "
                    f"is a dropped variant already represented elsewhere, silence "
                    f"the conflict with `ignore` instead)"
                ),
            )


#: Rules the `.update({...})` blocks are exempt from. Заманиловка keeps 149
#: clusters in such blocks, and its side-branch additions of July 2026 key a
#: cluster by its own first record and leave the names in record order — 88
#: CCN008 and 32 CCN009 findings when measured (2026-09-29), not one of them a
#: consolidation error. Renaming those keys would pull the familio module (they
#: are familio kin), and sorting could change which record seeds a canonical;
#: every other rule — a stub folded twice (CCN002), a key overwritten (CCN001)
#: — reads the blocks with the literal.
UPDATE_BLOCK_EXEMPT = frozenset({"CCN008", "CCN009"})


def _find_updates(tree: ast.Module, var_name: str) -> list[ast.Dict]:
    """The dict arguments of top-level `<var_name>.update({...})` calls."""
    out: list[ast.Dict] = []
    for node in tree.body:
        call = node.value if isinstance(node, ast.Expr) else None
        if (isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
                and call.func.attr == "update"
                and isinstance(call.func.value, ast.Name)
                and call.func.value.id == var_name):
            out.extend(a for a in call.args if isinstance(a, ast.Dict))
    return out


def lint_file(path: str | Path) -> list[Finding]:
    path = str(path)
    src = Path(path).read_text(encoding="utf-8")
    tree = ast.parse(src, filename=path)

    findings: list[Finding] = []

    profiles = _find_assign(tree, PROFILES_VAR)
    if profiles is None:
        findings.append(Finding(
            code="CCN000",
            severity="error",
            path=path,
            line=1,
            col=0,
            message=f"could not find top-level `{PROFILES_VAR} = {{...}}` assignment",
        ))
    else:
        literal = _check_top_dict(
            path=path,
            var_name=PROFILES_VAR,
            dict_node=profiles,
            allowed_value_keys=PROFILE_SCHEMA_KEYS,
            requires_profile_names=True,
        )
        findings.extend(literal)
        updates = _find_updates(tree, PROFILES_VAR)
        if updates:
            # The literal and the updates read as ONE dict, so the rules that
            # compare clusters see across the two; a finding the literal alone
            # already gave is not repeated.
            merged = ast.copy_location(ast.Dict(
                keys=[*profiles.keys, *(k for d in updates for k in d.keys)],
                values=[*profiles.values, *(v for d in updates for v in d.values)]),
                profiles)
            spans = [(d.lineno, d.end_lineno or d.lineno) for d in updates]
            seen = {(f.code, f.line, f.col, f.message) for f in literal}
            for f in _check_top_dict(path=path, var_name=PROFILES_VAR,
                                     dict_node=merged,
                                     allowed_value_keys=PROFILE_SCHEMA_KEYS,
                                     requires_profile_names=True):
                if (f.code, f.line, f.col, f.message) in seen:
                    continue
                if f.code in UPDATE_BLOCK_EXEMPT and any(a <= f.line <= b for a, b in spans):
                    continue
                findings.append(f)

    unions = _find_assign(tree, UNIONS_VAR)
    if unions is not None:
        findings.extend(_check_top_dict(
            path=path,
            var_name=UNIONS_VAR,
            dict_node=unions,
            allowed_value_keys=UNION_SCHEMA_KEYS,
            requires_profile_names=False,
        ))

    return findings


def _format_findings(findings: Iterable[Finding], *, as_json: bool) -> str:
    if as_json:
        return json.dumps({"findings": [asdict(f) for f in findings]}, ensure_ascii=False, indent=2)
    return "\n".join(f.format_text() for f in findings)


def main(argv: list[str]) -> int:
    args = list(argv)
    as_json = False
    if "--json" in args:
        as_json = True
        args.remove("--json")

    if len(args) == 1:
        target = Path.cwd() / "generate_config_names.py"
    elif len(args) == 2:
        target = Path(args[1])
    else:
        print("usage: verso lint-config [--json] [PATH]", file=sys.stderr)
        return 2

    findings = lint_file(target)
    output = _format_findings(findings, as_json=as_json)
    if output:
        print(output)
    return 1 if any(f.severity == "error" for f in findings) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
