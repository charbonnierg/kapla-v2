from __future__ import annotations

import asyncio
from typing import Optional, Tuple

from kapla.core.errors import CommandFailedError

from .cmd import check_command_stdout


async def get_current_git_tag() -> Optional[str]:
    try:
        return await check_command_stdout("git describe --exact-match --tags HEAD")
    except CommandFailedError:
        return None


async def get_current_git_branch() -> Optional[str]:
    try:
        return await check_command_stdout("git rev-parse --abbrev-ref HEAD")
    except CommandFailedError:
        return None


async def get_current_git_commit() -> Optional[str]:
    try:
        return await check_command_stdout("git rev-parse --short HEAD")
    except CommandFailedError:
        return None


async def get_git_infos() -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Return tag, branch, commit as strings"""
    tag, branch, commit = await asyncio.gather(
        get_current_git_tag(),
        get_current_git_branch(),
        get_current_git_commit(),
    )
    return (
        tag.strip() if tag else None,
        branch.strip() if branch else None,
        commit.strip() if commit else None,
    )
