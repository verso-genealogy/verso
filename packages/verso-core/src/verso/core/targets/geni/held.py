"""What of a corpus is on Geni while unreviewed: the village's list the review ratchet keeps
(`verso.core.ratchet`), and the mark a record listed there carries once loaded (the Geni
target's, out of the ratchet's mechanism)."""
from __future__ import annotations

LIST_FILE = "unreviewed_on_geni.tsv"
# The attribute a loaded record carries while the list admits it onto Geni unreviewed.
ON_GENI = "on_geni"

# The header a new list is written with; a list keeps the header it has (`ratchet.read_header`):
# the lists written before 0.1.0 keep theirs, in Russian.
HEADER = """\
# Unreviewed records already on Geni — the review ratchet (verso/core/ratchet.py).
# A record with reviewed=False reaches Geni only while its fingerprint is here; a new
# one, or one changed without a review, is held. Lines only shrink: a review in Verso
# and `verso review-ratchet --prune` strike them; never add one by hand.
# A record changed without a review stays on Geni only if its line is rebound
# (`verso review-ratchet --rebind`): the same call, number, sex and leaf, line for line.
# file\tfingerprint\trecord
"""
