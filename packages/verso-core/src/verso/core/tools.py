"""Where terraform and geni are: PATH first, then the workspace's `[tools] path`.

Until 0.1.0 four modules hardcoded the absolute path where one machine keeps each tool,
and four more ran a bare "terraform" from PATH. Every call now asks here; a machine
that keeps a tool off PATH says where in verso.toml. A Makefile asks too, by
`python -m verso.core.tools terraform`, once terraform is off PATH.
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys

from verso.core import workspace
from verso.core.workspace import WorkspaceError
from verso.core.messages import t


class ToolNotFound(WorkspaceError):
    """A tool neither PATH nor the workspace's [tools] path holds."""


def find_tool(name: str) -> str | None:
    """`name` on PATH, else in the workspace's [tools] path, in its order; None when neither has it."""
    found = shutil.which(name)
    if found is not None:
        return found
    extra = workspace.current().tool_path
    return shutil.which(name, path=os.pathsep.join(map(str, extra))) if extra else None


def tool(name: str) -> str:
    """`find_tool(name)`, or `ToolNotFound` saying where it looked."""
    found = find_tool(name)
    if found is None:
        ws = workspace.current()
        raise ToolNotFound(t("tools.not_found", name=name, path=ws.root / workspace.CONFIG))
    return found


def main(argv: list[str] | None = None) -> int:
    """`python -m verso.core.tools NAME`: print where NAME is, or say on stderr why not (exit 1)."""
    parser = argparse.ArgumentParser(prog="verso tools",
                                     description=str(t("tools.description")))
    parser.add_argument("name", help="terraform, geni …")
    args = parser.parse_args(argv)
    try:
        print(tool(args.name))
    except WorkspaceError as e:
        print(e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
