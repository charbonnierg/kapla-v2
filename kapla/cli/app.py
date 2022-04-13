from __future__ import annotations

import argparse

from kapla.cli.licenses import do_show_licenses, set_licenses_parser
from kapla.cli.list import do_list_projects, set_list_parser
from kapla.cli.repair import do_repair, set_repair_parser

from .build import do_build, set_build_parser
from .install import do_install, set_install_parser
from .project import (
    do_add_dependency,
    do_build_docker,
    do_build_project,
    do_create_new_project,
    do_install_project,
    do_remove_dependency,
    do_write_project,
    set_project_parser,
)
from .run import do_run_cmd, set_run_parser
from .uninstall import do_uninstall, set_uninstall_parser
from .venv import do_ensure_venv, do_venv_update, set_venv_parser

parent_parser = argparse.ArgumentParser(add_help=False)
main_parser = argparse.ArgumentParser(add_help=True)
command_subparser = main_parser.add_subparsers(title="command", dest="command")

set_install_parser(command_subparser, parent=parent_parser)
set_run_parser(command_subparser, parent=parent_parser)
set_venv_parser(command_subparser, parent=parent_parser)
set_build_parser(command_subparser, parent=parent_parser)
set_project_parser(command_subparser, parent=parent_parser)
set_list_parser(command_subparser, parent=parent_parser)
set_licenses_parser(command_subparser, parent=parent_parser)
set_repair_parser(command_subparser, parent=parent_parser)
set_uninstall_parser(command_subparser, parent=parent_parser)


def app() -> None:
    """Parse arguments and dispatch commands to functions"""
    args = main_parser.parse_args()

    if args.command == "install":
        do_install(args)

    if args.command == "uninstall":
        do_uninstall(args)

    elif args.command == "build":
        do_build(args)

    elif args.command == "repair":
        do_repair(args)

    elif args.command == "list":
        do_list_projects(args)

    elif args.command == "licenses":
        do_show_licenses(args)

    elif args.command == "run":
        do_run_cmd(args)

    elif args.command == "venv":
        if args.action == "update":
            do_venv_update(args)
        else:
            do_ensure_venv(args)

    elif args.command == "project":

        if args.action == "write":
            do_write_project(args)

        elif args.action == "build":
            do_build_project(args)

        elif args.action == "install":
            do_install_project(args)

        elif args.action == "remove":
            do_remove_dependency(args)

        elif args.action == "add":
            do_add_dependency(args)

        elif args.action == "new":
            do_create_new_project(args)

        elif args.action == "docker":
            do_build_docker(args)
