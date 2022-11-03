from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Optional, Union

from kapla.core.cmd import Command
from kapla.core.logger import logger


async def build(
    directory: Union[Path, str, None] = None,
    virtualenv: Optional[Path] = None,
    dist_format: Optional[str] = None,
    quiet: bool = False,
    raise_on_error: bool = False,
    timeout: Optional[float] = None,
    deadline: Optional[float] = None,
    **kwargs: Any,
) -> Command:
    if "rc" not in kwargs and raise_on_error:
        kwargs["rc"] = 0
    cmd = Command(
        "poetry build",
        cwd=directory,
        virtualenv=virtualenv,
        timeout=timeout,
        deadline=deadline,
        quiet=quiet,
        **kwargs,
    )

    if dist_format:
        cmd.add_option("--format", dist_format)

    return await cmd.run()


async def install(
    directory: Union[str, Path, None] = None,
    virtualenv: Union[str, Path, None] = None,
    exclude_groups: Union[Iterable[str], str, None] = None,
    include_groups: Union[Iterable[str], str, None] = None,
    only_groups: Union[Iterable[str], str, None] = None,
    default: bool = False,
    sync: bool = False,
    no_root: bool = False,
    dry_run: bool = False,
    extras: Union[Iterable[str], str, None] = None,
    quiet: bool = False,
    raise_on_error: bool = False,
    timeout: Optional[float] = None,
    deadline: Optional[float] = None,
    **kwargs: Any,
) -> Command:
    """Install poetry package.

    Reference: https://python-poetry.org/docs/master/cli/#install
    """
    if "rc" not in kwargs and raise_on_error:
        kwargs["rc"] = 0

    cmd = Command(
        "poetry install",
        cwd=directory,
        virtualenv=virtualenv,
        timeout=timeout,
        deadline=deadline,
        quiet=quiet,
        **kwargs,
    )

    if exclude_groups:
        cmd.add_repeat_option("--without", exclude_groups)
    if include_groups:
        cmd.add_repeat_option("--with", include_groups)
    if only_groups:
        cmd.add_repeat_option("--only", only_groups)
    if default:
        cmd.add_option("--default")
    if sync:
        cmd.add_option("--sync")
    if no_root:
        cmd.add_option("--no-root")
    if dry_run:
        cmd.add_option("--dry-run")
    if extras:
        cmd.add_option("--extras")

    logger.debug("Installing using poetry", cmd=cmd.cmd)
    return await cmd.run()


async def lock(
    directory: Union[str, Path, None] = None,
    virtualenv: Union[str, Path, None] = None,
    check: bool = False,
    no_update: bool = False,
    quiet: bool = False,
    raise_on_error: bool = False,
    timeout: Optional[float] = None,
    deadline: Optional[float] = None,
    **kwargs: Any,
) -> Command:
    """This command locks (without installing) the dependencies specified in pyproject.toml.

    Reference: https://python-poetry.org/docs/master/cli/#lock
    """
    if "rc" not in kwargs and raise_on_error:
        kwargs["rc"] = 0

    cmd = Command(
        "poetry lock",
        cwd=directory,
        virtualenv=virtualenv,
        timeout=timeout,
        deadline=deadline,
        quiet=quiet,
        **kwargs,
    )
    if check:
        cmd.add_option("--check")
    if no_update:
        cmd.add_option("--no-update")

    return await cmd.run()


async def update(
    directory: Union[str, Path, None] = None,
    virtualenv: Union[str, Path, None] = None,
    dry_run: bool = False,
    lock: bool = False,
    quiet: bool = False,
    raise_on_error: bool = False,
    timeout: Optional[float] = None,
    deadline: Optional[float] = None,
    **kwargs: Any,
) -> Command:
    """Perform package update. Use lock=True if you wish to update package lock only.

    Reference: https://python-poetry.org/docs/master/cli/#update
    """
    if "rc" not in kwargs and raise_on_error:
        kwargs["rc"] = 0

    cmd = Command(
        "poetry update",
        cwd=directory,
        virtualenv=virtualenv,
        quiet=quiet,
        timeout=timeout,
        deadline=deadline,
        **kwargs,
    )
    if dry_run:
        cmd.add_option("--dry-run")
    if lock:
        cmd.add_option("--lock-only")

    return await cmd.run()


async def add(
    *package: str,
    directory: Union[str, Path, None] = None,
    virtualenv: Union[str, Path, None] = None,
    group: Optional[str] = None,
    editable: bool = False,
    extras: Union[str, Iterable[str], None] = None,
    optional: bool = False,
    python: Optional[str] = None,
    platform: Union[str, Iterable[str], None] = None,
    source: Optional[str] = None,
    allow_prereleases: bool = False,
    dry_run: bool = False,
    lock: bool = False,
    quiet: bool = False,
    raise_on_error: bool = False,
    timeout: Optional[float] = None,
    deadline: Optional[float] = None,
    **kwargs: Any,
) -> Command:
    """Add a package dependency.

    Reference: https://python-poetry.org/docs/master/cli/#add
    """
    if "rc" not in kwargs and raise_on_error:
        kwargs["rc"] = 0

    cmd = Command(
        "poetry add",
        cwd=directory,
        virtualenv=virtualenv,
        quiet=quiet,
        timeout=timeout,
        deadline=deadline,
        **kwargs,
    )

    if group:
        cmd.add_option("--group", group)
    if optional:
        cmd.add_option("--optional")
    if python:
        cmd.add_option("--python", python)
    if platform:
        cmd.add_repeat_option("--platform", platform)
    if source:
        cmd.add_option("--source", source)
    if extras:
        cmd.add_repeat_option("--extras", extras)
    if allow_prereleases:
        cmd.add_option("--allow-prereleases")
    if dry_run:
        cmd.add_option("--dry-run")
    if lock:
        cmd.add_option("--lock")
    if editable:
        cmd.add_option("--editable")

    for pkg in package:
        cmd.add_argument(pkg)

    return await cmd.run()


async def remove(
    package: Union[str, Iterable[str]],
    directory: Union[str, Path, None] = None,
    virtualenv: Union[str, Path, None] = None,
    group: Optional[str] = None,
    dry_run: bool = False,
    quiet: bool = False,
    raise_on_error: bool = False,
    timeout: Optional[float] = None,
    deadline: Optional[float] = None,
    **kwargs: Any,
) -> Command:
    """Remove a package dependency

    Reference: https://python-poetry.org/docs/master/cli/#remove
    """
    if "rc" not in kwargs and raise_on_error:
        kwargs["rc"] = 0

    cmd = Command(
        "poetry remove",
        cwd=directory,
        virtualenv=virtualenv,
        quiet=quiet,
        timeout=timeout,
        deadline=deadline,
        **kwargs,
    )

    if group:
        cmd.add_option("--group", group)
    if dry_run:
        cmd.add_option("--dry-run")

    if isinstance(package, str):
        package = [package]

    for pkg in package:
        cmd.add_argument(pkg)

    return await cmd.run()


async def show(
    directory: Union[str, Path, None] = None,
    virtualenv: Union[str, Path, None] = None,
    exclude_groups: Union[Iterable[str], str, None] = None,
    include_groups: Union[Iterable[str], str, None] = None,
    only_groups: Union[Iterable[str], str, None] = None,
    default: Union[Iterable[str], str, None] = None,
    tree: bool = False,
    latest: bool = False,
    outdated: bool = False,
    quiet: bool = False,
    raise_on_error: bool = False,
    timeout: Optional[float] = None,
    deadline: Optional[float] = None,
    **kwargs: Any,
) -> Command:
    """Show project dependencies"""
    if "rc" not in kwargs and raise_on_error:
        kwargs["rc"] = 0

    cmd = Command(
        "poetry show",
        cwd=directory,
        virtualenv=virtualenv,
        quiet=quiet,
        timeout=timeout,
        deadline=deadline,
    )

    if exclude_groups:
        cmd.add_repeat_option("--without", exclude_groups)
    if include_groups:
        cmd.add_repeat_option("--with", include_groups)
    if only_groups:
        cmd.add_repeat_option("--only", only_groups)
    if default:
        cmd.add_option("--default")
    if tree:
        cmd.add_option("--tree")
    if latest:
        cmd.add_option("--latest")
    if outdated:
        cmd.add_option("--outdated")

    return await cmd.run()


async def publish(
    directory: Union[str, Path, None] = None,
    virtualenv: Union[str, Path, None] = None,
    repository: Optional[str] = None,
    username: Optional[str] = None,
    password: Optional[str] = None,
    dry_run: Optional[str] = None,
    quiet: bool = False,
    raise_on_error: bool = False,
    timeout: Optional[float] = None,
    deadline: Optional[float] = None,
    **kwargs: Any,
) -> Command:
    """This command publishes the package, previously built with the build command, to the remote repository.

    Reference: https://python-poetry.org/docs/master/cli/#publish
    """
    if "rc" not in kwargs and raise_on_error:
        kwargs["rc"] = 0

    cmd = Command(
        "poetry publish",
        cwd=directory,
        virtualenv=virtualenv,
        quiet=quiet,
        timeout=timeout,
        deadline=deadline,
        **kwargs,
    )
    if repository:
        cmd.add_option("--repository", repository)
    if username:
        cmd.add_option("--username", username)
    if password:
        cmd.add_option("--password", password)
    if dry_run:
        cmd.add_option("--dry-run", dry_run)

    return await cmd.run()
