"""`verso <команда>`: one command for each module of the library that runs as a program.

A command is its module's name with hyphens — `verso generate-tf` is
`python -m verso.ru.cli.generate_tf` —, but for five names too general to stand alone
(`records-schema`, `ui-schema`, `verify-batch`, `validate-import`, `import-sheets`). The module runs as
`__main__` through runpy, so it reads its arguments, prints and exits as under `python -m`,
but that its usage names the program `verso <команда>`.
`--lang LANG` speaks LANG: it is `VERSO_LANG=LANG` for this command (`verso.core.i18n`).
`--workspace DIR` runs it in that workspace: it is `VERSO_WORKSPACE=DIR` for this command
— a `workspace.use()` here would not reach `verso workspace`, which runpy runs as a second
copy of the module, and this module imports nothing of the library for that reason.

The core's five commands are here; each installed plugin brings its own (`Plugin.commands`),
found by the registry without a workspace: `verso --help` lists them all, the core's
first, then each plugin's by its name. The tables are strings: the core imports none of the
commands' modules.
"""
from __future__ import annotations

import argparse
import os
import re
import runpy
import sys
from collections.abc import Generator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from verso.core.i18n import Message
from verso.core.messages import t

# verso.core.workspace's ENV and CONFIG; importing the module would make `verso workspace` a
# second copy of it (runpy warns, and the copy's own use() stack would be another one).
_ENV = "VERSO_WORKSPACE"
_CONFIG = "verso.toml"

# The core's own commands; each installed plugin brings its own (`Plugin.commands`).
COMMANDS: dict[str, str] = {
    "records-schema": "verso.core.records.schema",
    "scans":          "verso.core.scans.cli",
    "tools":          "verso.core.tools",
    "ui-schema":      "verso.core.records.ui",
    "workspace":      "verso.core.workspace",
}


def _say(message: object) -> str:
    """A message's text in the workspace's language: the workspace is imported here, to say
    it, and never before a command runs — `verso workspace` runs that module as `__main__`."""
    import verso.core.workspace  # noqa: F401 — it tells verso.core.i18n where the language comes from
    return str(message)


def _plugins() -> list[tuple[str, Mapping[str, str]]]:
    """Each installed plugin's name and commands, by name. The registry reads no workspace:
    a command is found wherever verso is run, `verso --help` with no workspace at all."""
    from verso.core import plugins
    return [(name, plugin.commands) for name, plugin in plugins.installed().items()]


def commands() -> dict[str, str]:
    """Every command: the core's, then each installed plugin's — refused when two name one."""
    from verso.core.plugins import PluginError
    out, owner = dict(COMMANDS), dict.fromkeys(COMMANDS, "")
    for name, given in _plugins():
        for command, module in given.items():
            if command in owner:
                where = t("cli.where_plugins", first=owner[command], second=name) if owner[command] \
                    else t("cli.where_core", plugin=name)
                raise PluginError(t("cli.command_twice", command=command, where=where))
            out[command], owner[command] = module, name
    return out


class _Parser(argparse.ArgumentParser):
    """verso's own parser: its texts are the catalog's, put together only when the help or the
    usage is printed — a command that prints neither never asks for the language, nor so reads the
    workspace (`verso workspace` runs that module as `__main__`)."""

    def __init__(self, groups: list[tuple[Message, dict[str, str]]], **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.groups = groups
        self.lazy: list[tuple[object, str, Message]] = []    # (what, its attribute, the text)

    def text(self, what: object, attribute: str, message: Message) -> None:
        self.lazy.append((what, attribute, message))

    @contextmanager
    def _rendered(self) -> Generator[None]:
        width = max(len(name) for _, given in self.groups for name in given)
        listing = "\n\n".join(f"{_say(title)}:\n" + "\n".join(f"  {name:<{width}}  {module}" for name, module in given.items())
                              for title, given in self.groups if given)
        if len(self.groups) == 1:
            listing += f"\n\n{_say(t('cli.no_plugins'))}"
        texts = [*self.lazy, (self, "epilog", t("cli.epilog", listing=listing))]
        before = [(what, attribute, getattr(what, attribute)) for what, attribute, _ in texts]
        for what, attribute, message in texts:
            setattr(what, attribute, _say(message))
        try:
            yield
        finally:
            for what, attribute, value in before:
                setattr(what, attribute, value)

    def format_help(self) -> str:
        with self._rendered():
            return super().format_help()

    def format_usage(self) -> str:
        with self._rendered():
            return super().format_usage()


def build_parser() -> argparse.ArgumentParser:
    groups = [(t("cli.core_group"), dict(COMMANDS)),
              *((t("cli.plugin_group", name=name), dict(given)) for name, given in _plugins())]
    parser = _Parser(groups, prog="verso", formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.text(parser, "description", t("cli.description"))
    parser.text(parser.add_argument("--workspace", type=Path, metavar="DIR"), "help", t("cli.workspace_help"))
    parser.text(parser.add_argument("--lang", metavar="LANG"), "help", t("cli.lang_help"))
    parser.text(parser.add_argument("command", nargs="?"), "metavar", t("cli.command_metavar"))
    parser.text(parser.add_argument("args", nargs=argparse.REMAINDER), "metavar", t("cli.args_metavar"))
    return parser


# How a parser names a module run as a program: Python 3.14's default under `-m`
# («python3 -m verso.ru.cli.svyatcy»), or a module's own prog written so («python -m <module>»).
_AS_A_MODULE = re.compile(r"^python[\d.]* -m \S+")


@contextmanager
def _named(program: str) -> Generator[None]:
    """While a command runs, a parser that would name the program as a module names it
    `program`; a subcommand's parser follows, as argparse builds its name from its parent's."""
    init = argparse.ArgumentParser.__init__

    def named(self: argparse.ArgumentParser, *args: Any, **kwargs: Any) -> None:
        init(self, *args, **kwargs)
        self.prog = _AS_A_MODULE.sub(lambda _: program, self.prog, count=1)

    setattr(argparse.ArgumentParser, "__init__", named)  # noqa: B010 — a method assigned, which pyright refuses
    try:
        yield
    finally:
        setattr(argparse.ArgumentParser, "__init__", init)  # noqa: B010


def _exit_code(code: object) -> int:
    """What the process would exit with, raising SystemExit(code)."""
    if code is None:
        return 0
    if isinstance(code, int):
        return code
    print(code, file=sys.stderr)
    return 1


def _missing_plugin() -> str | None:
    """Why a command may be missing: the workspace enables a plugin nobody installed (`make
    bootstrap` after a pull); None when it does not, or there is no workspace here."""
    from verso.core import plugins, workspace
    try:
        plugins.enabled()
    except plugins.PluginError as error:
        return str(error)
    except workspace.WorkspaceError:
        return None
    return None


def _early(argv: list[str]) -> dict[str, str]:
    """verso's own `--lang` and `--workspace`, read before the parser prints anything (its help,
    its usage, an error): the options before the command, as the parser takes them."""
    out: dict[str, str] = {}
    words = iter(argv)
    for word in words:
        if not word.startswith("-"):
            break                   # the command: what follows is its own
        name, eq, value = word.partition("=")
        if name in ("--lang", "--workspace"):
            value = value if eq else next(words, "")
            if value:
                out[name[2:]] = value
    return out


def main(argv: list[str] | None = None) -> int:
    from verso.core import i18n
    from verso.core.plugins import PluginError
    early = _early(sys.argv[1:] if argv is None else argv)
    if "lang" in early:
        os.environ[i18n.ENV] = early["lang"]
    if "workspace" in early and (Path(early["workspace"]) / _CONFIG).is_file():
        os.environ[_ENV] = str(Path(early["workspace"]).resolve())
    try:                            # a language nobody speaks: `--lang`, `VERSO_LANG`
        i18n.check()
    except i18n.CatalogError as error:
        print(f"verso: {error}", file=sys.stderr)
        return 2
    try:                            # a plugin's entry point that does not load, two plugins' command
        parser = build_parser()
        args = parser.parse_args(argv)
        if args.command is None:
            parser.print_help()
            return 2
        module = commands().get(args.command)
    except PluginError as error:
        print(f"verso: {_say(error)}", file=sys.stderr)
        return 2
    if module is None:
        print(_say(t("cli.no_command", command=args.command)), file=sys.stderr)
        if (why := _missing_plugin()) is not None:
            print(f"verso: {why}", file=sys.stderr)
        return 2
    if args.workspace is not None:
        if not (args.workspace / _CONFIG).is_file():
            print(_say(t("cli.workspace_no_config", workspace=args.workspace, config=_CONFIG)), file=sys.stderr)
            return 2
        os.environ[_ENV] = str(args.workspace.resolve())
    sys.argv = [f"verso {args.command}", *args.args]
    with _named(sys.argv[0]):
        try:
            runpy.run_module(module, run_name="__main__", alter_sys=True)
        except SystemExit as done:
            return _exit_code(done.code)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
