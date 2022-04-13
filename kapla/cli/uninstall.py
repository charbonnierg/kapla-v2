from __future__ import annotations

from argparse import ArgumentParser, _SubParsersAction
from functools import partial
import sys
from typing import Any, Optional, Tuple

from anyio import run
from kapla.core.errors import CommandFailedError
from kapla.core.logger import logger
from kapla.projects.krepo import KRepo


def set_uninstall_parser(
    parser: _SubParsersAction[Any], parent: ArgumentParser
) -> None:
    install_parser = parser.add_parser("uninstall", parents=[parent])
    install_parser.add_argument(
        "projects",
        nargs="*",
    )
    install_parser.add_argument(
        "-e",
        "--exclude-project",
        dest="exclude_projects",
        nargs="+",
    )
    install_parser.add_argument(
        "--verbose",
        "-v",
        dest="verbose",
        action="store_true",
        default=False,
    )


def do_uninstall(args: Any) -> None:
    """Projects install command line operation"""

    # Parse arguments
    include_projects: Optional[Tuple[str]] = args.projects
    exclude_projects: Optional[Tuple[str]] = args.exclude_projects
    quiet: bool = not args.verbose
    # Find repo
    repo = KRepo.find_current()
    # Define function to perform install
    uninstall = partial(
        repo.uninstall_editable_projects,
        include_projects=include_projects,
        exclude_projects=exclude_projects,
        pip_quiet=quiet,
    )
    # Run install
    try:
        run(uninstall)
    except CommandFailedError:
        logger.error("Failed to uninstall package")
        sys.exit(1)
