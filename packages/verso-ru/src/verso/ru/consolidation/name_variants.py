#!/usr/bin/env python3
"""Flag a loose record whose SURNAME the canonical of that name already carries.

The fourth discovery channel, and it exists because of a specific asymmetry in
the sources. The 1834 revision records no surnames at all, so canonicals built
from it (and from early metric books, where the scribe often omitted the
surname too) carry only a given name and a patronymic. A later metric book then
names the same person WITH the podvorye surname — «Юлиана Тимофеевна Хохотунова»,
«Елена Антоновна Тарабаева» — and a matcher that demands every name agree
cannot pair them, because one side has no surname to match.

Matching on given+patronymic alone is not an option: it yields hundreds of
candidates on Горюхино, and this project's own history says that prior is where
the traps live — half of pass 18's godparents turned out to be namesakes. So
this channel requires a SECOND, positive signal: a surname of the loose record
must already be carried by one of the canonical's own records — within one
letter (Ежевикин ~ Ежевикен, Тарабаева ~ Тарабуева), or a spelling of the family the
corpus has learned from one man's records carrying both.

Since 2026-09-28 it is the second caller of the matcher `verso reconcile` runs
on (`verso.ru.facts.checks.reconcile`), over the assertions rather than the tree:

- a TARGET is a loose appearance of the corpus proper — a birth, a wedding, a
  burial, a roll — standing as a profile of its own (`LooseIndex`, asked of
  the translation; until then a regex over the res_name, which took a card
  without a year for a canonical and a Заманиловка canonical named after its
  first record for a loose one). A list entry or a card is `reconcile`'s;
- the POOL is every person who is not loose;
- the given name agrees by its base form, the father by the patronymic or the
  record that names him — and he must be written on BOTH sides, as this
  channel always demanded; the surname as above;
- the guards are the matcher's: one list, one двор of one roll, births apart,
  named before the other was born, dead before the other is seen alive.

One match surviving is a CANDIDATE, several AMBIGUOUS — where the old channel
said nothing at all when a name had two canonicals. The config's `nicknames`
are not read: they are the tree, not the records, and half of them are given
names and patronymics («Антропий», «Иосифович») compared as if they were
surnames.

Deliberately NOT reported: a loose record whose canonical has no surname at all.
That is the larger half of the class and it has no cheap structural signal —
the revision gives no surname to compare, and `check-godparent-cooccurrence`
only fires on a RECURRING godparent↔parent pair, which a godmother who serves
many families never forms. Those still need a person named by hand.

`--audit-folded` is the oracle: every folded appearance the channel could have
proposed is taken out of its canonical and matched as if loose.

A candidate is a SIGNAL, not a verdict — read the records before folding.
Read-only, network-free.

Run:
    python3 -m verso.ru.consolidation.name_variants --village Горюхино
    verso name-variants --village Горюхино [--json] [--all] [--audit-folded]
"""
from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from pathlib import Path

from verso.ru.consolidation.reconcile import findings_to_json, format_audit, format_report
from verso.ru.facts.checks.reconcile import (
    Channel, Side, audit_folded, corpus_proper, lists_and_cards, match)
from verso.ru.facts.identity import Identity, IdentityKey, conclusions
from verso.ru.facts.model import AssertionSet
from verso.ru.facts.projection import LooseIndex, consolidated_identity
from verso.ru.messages import t

CHANNEL = "name-variants"
def targets() -> str:
    return str(t("consolidation.name_variants.targets"))


def folded() -> str:
    return str(t("consolidation.name_variants.folded"))


def auditable(side: Side) -> bool:
    """An appearance this channel could propose: of the corpus proper, with a
    surname and a father."""
    return (corpus_proper(side) and not lists_and_cards(side)
            and bool(side.names.roots) and bool(side.names.fathers))


def name_variants_channel(loose: Callable[[IdentityKey], bool]) -> Channel:
    """The loose appearances against everyone who is not loose, the father
    required on both sides."""
    return Channel(is_target=lambda s: loose(s.key) and auditable(s),
                   in_pool=lambda s: not loose(s.key),
                   auditable=auditable, require_father=True)


def loose_keys(facts: AssertionSet, identity: Identity,
               index: LooseIndex) -> frozenset[IdentityKey]:
    """The people made of appearances that each still stand alone."""
    out: set[IdentityKey] = set()
    for key, person in conclusions(facts, identity).items():
        personas = {c.subject for c in person.claims}
        if personas and all(index.is_loose(p) for p in personas):
            out.add(key)
    return frozenset(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Flag a loose record whose surname the canonical of that "
                    "given name + father already carries — the same person "
                    "written once with a podvorye surname and once without.")
    ap.add_argument("--village", default=".", help="village dir (default: cwd)")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--all", action="store_true", dest="all_targets",
                    help="also the targets nobody matches and the retired matches")
    ap.add_argument("--audit-folded", action="store_true",
                    help="run the folds already made by hand through the rule")
    args = ap.parse_args(argv)

    from verso.ru.pipeline.facts import consolidated_facts

    village = Path(args.village)
    facts, gen, slots = consolidated_facts(village)
    believed = facts.believed()
    identity = consolidated_identity(gen, slots.object_of)
    config = village / "generate_config_names.py"
    index = LooseIndex(gen, slots, config.read_text() if config.is_file() else "")
    loose = loose_keys(believed, identity, index)
    channel = name_variants_channel(lambda key: key in loose)
    profiles = gen.canonical_profiles()
    if args.audit_folded:
        audits = audit_folded(believed, identity, channel)
        print(format_audit(audits, profiles, channel=CHANNEL, folded=folded()))
        return 1 if any(a.outcome != "FOUND" for a in audits) else 0
    found = match(believed, identity, channel)
    print(findings_to_json(found) if args.json
          else format_report(found, profiles, all_targets=args.all_targets,
                             channel=CHANNEL, targets=targets()))
    return 1 if any(r.is_candidate for r in found) else 0


if __name__ == "__main__":
    sys.exit(main())
