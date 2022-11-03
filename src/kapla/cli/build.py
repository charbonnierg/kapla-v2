from __future__ import annotations

import sys
from argparse import ArgumentParser, _SubParsersAction
from functools import partial
from typing import Any, Optional, Tuple

from anyio import run

from kapla.core.errors import CommandFailedError
from kapla.core.logger import logger
from kapla.projects.krepo import KRepo


def set_build_parser(parser: _SubParsersAction[Any], parent: ArgumentParser) -> None:
    build_parser = parser.add_parser("build", parents=[parent])
    build_parser.add_argument(
        "projects",
        nargs="*",
    )
    build_parser.add_argument(
        "-e",
        "--exclude-project",
        dest="exclude_projects",
        nargs="+",
    )
    build_parser.add_argument(
        "--no-clean", action="store_true", default=False, dest="no_clean"
    )
    build_parser.add_argument(
        "-l", "--lock", action="store_true", default=False, dest="lock_versions"
    )


def do_build(args: Any) -> None:
    """Build command line operation"""

    # Parse arguments
    include_projects: Optional[Tuple[str]] = args.projects or None
    exclude_projects: Optional[Tuple[str]] = args.exclude_projects or None
    lock_versions: bool = args.lock_versions
    clean: bool = not args.no_clean

    # Find repo
    repo = KRepo.find_current()

    # Define function to perform build
    build = partial(
        repo.build_projects,
        include_projects=include_projects,
        exclude_projects=exclude_projects,
        lock_versions=lock_versions,
        clean=clean,
    )

    # Run build
    try:
        run(build)
    except CommandFailedError:
        logger.error("Build failed")
        sys.exit(1)
