from __future__ import annotations

from argparse import ArgumentParser, _SubParsersAction
from typing import Any, Optional

from anyio import run

from kapla.projects.krepo import KRepo


def set_repair_parser(parser: _SubParsersAction[Any], parent: ArgumentParser) -> None:
    parser.add_parser("repair", parents=[parent])


def do_repair(args: Optional[Any] = None) -> None:
    """repair command line operation"""

    # Find repo
    repo = KRepo.find_current()

    # Run repair
    run(repo.add_missing_dependencies)
