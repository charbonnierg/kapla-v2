from __future__ import annotations

from argparse import ArgumentParser, _SubParsersAction
from functools import partial
from typing import Any, Optional, Tuple

from anyio import run

from kapla.projects.krepo import KRepo


def set_install_parser(parser: _SubParsersAction[Any], parent: ArgumentParser) -> None:
    install_parser = parser.add_parser("install", parents=[parent])
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
        "-g",
        "--group",
        "--with",
        "--include-group",
        dest="include_groups",
        nargs="+",
    )
    install_parser.add_argument(
        "--without",
        "--exclude-group",
        dest="exclude_groups",
        nargs="+",
    )
    install_parser.add_argument(
        "-o", "--only", "--only-group", action="append", dest="only_groups", nargs="+"
    )
    install_parser.add_argument(
        "-d", "--default", action="store_true", default=False, dest="default"
    )
    install_parser.add_argument(
        "--venv", action="store_true", default=False, dest="update_venv"
    )
    install_parser.add_argument(
        "--from-scratch", action="store_true", default=False, dest="recreate_venv"
    )
    install_parser.add_argument(
        "--no-clean", action="store_true", default=False, dest="no_clean"
    )


def do_install(args: Any) -> None:
    """Projects install command line operation"""

    # Parse arguments
    include_projects: Optional[Tuple[str]] = args.projects
    exclude_projects: Optional[Tuple[str]] = args.exclude_projects
    include_groups: Optional[Tuple[str]] = args.include_groups or None
    exclude_groups: Optional[Tuple[str]] = args.exclude_groups or None
    only_groups: Optional[Tuple[str]] = args.only_groups or None
    default: bool = args.default
    update_venv: bool = args.update_venv
    recreate_venv: bool = args.recreate_venv
    clean: bool = not args.no_clean
    # Find repo
    repo = KRepo.find_current()
    # Check if we should delete venv
    if recreate_venv:
        repo.remove_venv()
        # Force venv creation
        update_venv = True
    # Define function to perform install
    install = partial(
        repo.install_editable_projects,
        include_projects=include_projects,
        exclude_projects=exclude_projects,
        exclude_groups=exclude_groups,
        include_groups=include_groups,
        only_groups=only_groups,
        default=default,
        update_venv=update_venv,
        clean=clean,
    )
    # Run install
    run(install)
