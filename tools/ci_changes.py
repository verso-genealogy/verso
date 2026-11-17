"""Whether a pull request touches anything CI's tests read with the library installed — `ci.yml`, job «What changed».

A pull request that changes prose alone — the root's Markdown, the guides in docs/, the IDE plugins' READMEs — runs
the text checks (tests/repo/test_public_texts.py: the translations, no phase labels, no pointers into a corpus) and
gitleaks, not the whole suite. Everything else is code, Markdown included where a test or the library reads it:
the plugins' skills (tests/plugins), the reading prompts and the packages' READMEs (packages/), the example
(tests/test_examples.py), docs/reference (written from the code, `make reference-check`) and docs/scans*.md
(tests/ru/scans/test_surface.py holds the scan tools' names to them). A test that starts reading another of the
prose files moves it out of PROSE.

    git diff --name-only HEAD^1 HEAD | python3 tools/ci_changes.py     # prints code=true or code=false
"""
from __future__ import annotations

import re
import sys
from collections.abc import Iterable

#: The prose no test reads with the library installed.
PROSE = re.compile(r"[^/]+\.md|docs/(?!scans(?:\.ru)?\.md$)[^/]+\.md|ide/[^/]+/README\.md")


def touches_code(paths: Iterable[str]) -> bool:
    """True unless every path is prose; an empty change is code too — there is nothing to tell it by."""
    listed = [p for p in (path.strip() for path in paths) if p]
    return not listed or not all(PROSE.fullmatch(p) for p in listed)


def main() -> int:
    print(f"code={'true' if touches_code(sys.stdin) else 'false'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
