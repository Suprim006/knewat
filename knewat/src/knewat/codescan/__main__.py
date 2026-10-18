# ruff: noqa: E501  (long prose lines, as in mcp/ and cli.py)
"""``python -m plexus.codescan <scan|baseline|hook-claude|hook-git|hook-run> ...``: the ``plexus code`` group without
importing the rest of the CLI (the hooks use it so they start fast)."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from plexus.codescan.cli import add_code_commands


def main(argv: Sequence[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="python -m plexus.codescan")
    add_code_commands(p.add_subparsers(dest="group", required=True))
    args = p.parse_args(["code", *(sys.argv[1:] if argv is None else argv)])
    try:
        code = args.fn(args)
    except KeyboardInterrupt:
        code = 130
    sys.exit(code)


if __name__ == "__main__":
    main()
