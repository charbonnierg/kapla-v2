from __future__ import annotations

from argparse import ArgumentParser, _SubParsersAction
from functools import partial
from typing import Any, Optional, Tuple

from anyio import run

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


def do_build(args: Any) -> None:
    """Build command line operation"""

    # Parse arguments
    include_projects: Optional[Tuple[str]] = args.projects or None
    exclude_projects: Optional[Tuple[str]] = args.exclude_projects or None
    clean: bool = not args.no_clean

    # Find repo
    repo = KRepo.find_current()

    # Define function to perform build
    build = partial(
        repo.build_projects,
        include_projects=include_projects,
        exclude_projects=exclude_projects,
        clean=clean,
    )

    # Run build
    run(build)
