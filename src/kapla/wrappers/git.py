from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Union

from kapla.core.cmd import Command, check_command, check_command_stdout
from kapla.core.errors import CommandFailedError


@dataclass
class GitInfos:
    """A class to store git infos"""

    commit: Optional[str] = None
    branch: Optional[str] = None
    tag: Optional[str] = None


async def get_infos(directory: Union[Path, str, None] = None) -> GitInfos:
    """Return tag, branch, commit as strings"""
    tag, branch, commit = await asyncio.gather(
        get_tag(directory),
        get_branch(directory),
        get_commit(directory),
    )
    return GitInfos(
        commit=commit.strip() if commit else None,
        branch=branch.strip() if branch else None,
        tag=tag.strip() if tag else None,
    )


async def get_tag(directory: Union[Path, str, None] = None) -> Optional[str]:
    """Get current git tag name"""
    try:
        return await check_command_stdout(
            "git describe --exact-match --tags HEAD", strip=True, cwd=directory
        )
    except CommandFailedError:
        return None


async def get_branch(directory: Union[Path, str, None] = None) -> Optional[str]:
    """Get current git branch name"""
    try:
        return await check_command_stdout(
            "git rev-parse --abbrev-ref HEAD", strip=True, cwd=directory
        )
    except CommandFailedError:
        return None


async def get_commit(directory: Union[Path, str, None] = None) -> Optional[str]:
    """Get current git commit short sha"""
    try:
        return await check_command_stdout(
            "git rev-parse --short HEAD", strip=True, cwd=directory
        )
    except CommandFailedError:
        return None


async def get_files(directory: Union[Path, str, None] = None) -> List[str]:
    """Get list of files tracked by git"""
    try:
        cmd = await check_command("git ls-files", cwd=directory)
    except CommandFailedError:
        return []
    return cmd.lines


async def get_log(
    n: Optional[int] = 3,
    stat: bool = False,
    directory: Union[Path, str, None] = None,
) -> Optional[str]:
    """Get logs of previous commit (3 by default)"""
    cmd = Command("git log", cwd=directory)
    if n is not None:
        cmd.add_option("-n", str(n))
    if stat:
        cmd.add_option("--stat")
    try:
        await cmd.run(rc=0)
    except CommandFailedError:
        return None
    return cmd.stdout.strip()
