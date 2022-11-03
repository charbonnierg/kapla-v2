from __future__ import annotations

from argparse import ArgumentParser, _SubParsersAction
from typing import Any, List

from rich.console import Console
from rich.table import Table

from kapla.projects.krepo import KRepo


class ProjectsTable(Table):
    @classmethod
    def from_repo(cls, repo: KRepo, **kwargs: Any) -> ProjectsTable:
        """Create a new table from a list of projects"""
        table = cls(
            "Name",
            "Version",
            "Installed",
            "Path",
            "Scripts",
            "Apps",
            title=f"{repo.name} packages",
        )
        for project in repo.list_projects():
            all_plugins = project.spec.plugins
            apps: List[str] = []
            for plugin_type, plugins in all_plugins.items():
                if plugin_type == "quara.apps":
                    apps = list(plugins)
            table.add_row(
                project.name,
                project.version,
                "✔" if project.is_already_installed() else "💥",
                project.root.relative_to(repo.root).as_posix(),
                ", ".join(project.spec.scripts),
                ", ".join(apps),
            )
        return table


def set_list_parser(parser: _SubParsersAction[Any], parent: ArgumentParser) -> None:
    parser.add_parser("list", parents=[parent])


def do_list_projects(args: Any) -> None:
    repo = KRepo.find_current()
    console = Console()
    table = ProjectsTable.from_repo(repo)
    console.print(table)
