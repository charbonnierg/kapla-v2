from __future__ import annotations

from argparse import REMAINDER, ArgumentParser, _SubParsersAction
from functools import partial
from typing import Any

from anyio import run

from kapla.projects.krepo import KRepo


def set_run_parser(parser: _SubParsersAction[Any], parent: ArgumentParser) -> None:
    run_parser = parser.add_parser("run", parents=[parent])
    run_parser.add_argument("cmd", nargs=REMAINDER)


def do_run_cmd(args: Any) -> None:
    # Parse args
    cmd = args.cmd
    # Find repo
    repo = KRepo.find_current()
    run_cmd = partial(repo.run_cmd, cmd)
    # Update run
    run(run_cmd)
