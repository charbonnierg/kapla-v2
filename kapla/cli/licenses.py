from __future__ import annotations

from argparse import ArgumentParser, _SubParsersAction
from typing import Any, Optional, Tuple

import pkg_resources
from rich.console import Console
from rich.table import Table

from kapla.core.repo import KRepo


def get_pkg_license(pkg: pkg_resources.Distribution) -> Tuple[str, str]:
    try:
        lines = pkg.get_metadata_lines("METADATA")
    except Exception:
        lines = pkg.get_metadata_lines("PKG-INFO")

    license: Optional[str] = None
    url: Optional[str] = None
    for line in lines:
        if line.startswith("License:"):
            license = str(line[9:])
        elif line.startswith("Project-URL"):
            url = str(line).split(" ")[-1].strip()
    return (license or "  -  ", url or "  -  ")


class LicensesTable(Table):
    @classmethod
    def from_repo(cls, repo: KRepo) -> LicensesTable:
        table = cls(
            "Package",
            "Version",
            "License",
            "Project URL",
            title="Dependencies licenses",
        )
        for dep in repo.packages_lock:
            if dep in repo.projects:
                continue
            if dep == "python":
                continue
            try:
                dists = pkg_resources.require(dep)
            except pkg_resources.DistributionNotFound:
                table.add_row(
                    dep,
                    repo.packages_lock.get(dep, {}).get("version", "  ?  "),
                    "  ?  ",
                    "  ?  ",
                )
                continue
            for dist in dists:
                license, url = get_pkg_license(dist)
                table.add_row(
                    dist.project_name,
                    dist.version,
                    license,
                    url,
                )
        return table


def set_licenses_parser(parser: _SubParsersAction[Any], parent: ArgumentParser) -> None:
    parser.add_parser("licenses", parents=[parent])


def do_show_licenses(args: Any) -> None:
    repo = KRepo.find_current()
    console = Console()
    table = LicensesTable.from_repo(repo)
    console.print(table)
