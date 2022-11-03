from __future__ import annotations

from argparse import ArgumentParser, _SubParsersAction
from typing import Any, Optional

from anyio import run

from kapla.projects.krepo import KRepo


def set_venv_parser(
    parser: _SubParsersAction[ArgumentParser], parent: ArgumentParser
) -> None:
    venv_parser = parser.add_parser("venv", description="venv projects")
    venv_actions_subparser = venv_parser.add_subparsers(title="venv", dest="action")
    venv_actions_subparser.add_parser("update", parents=[parent])


def do_venv_update(args: Optional[Any] = None) -> None:
    # Find repo
    repo = KRepo.find_current()
    # Update venv
    run(repo.update_venv)


def do_ensure_venv(args: Optional[Any] = None) -> None:
    # Find repo
    repo = KRepo.find_current()
    # Ensure venv
    run(repo.ensure_venv)
