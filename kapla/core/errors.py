from __future__ import annotations

import asyncio
import multiprocessing
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .cmd import Command


class PythonNotFoundError(FileNotFoundError):
    """Cannot find python interpreter"""

    pass


class PyprojectNotFoundError(FileNotFoundError):
    """No pyproject.toml were found in current directory or parent directories"""

    pass


class KProjectNotFoundError(FileNotFoundError):
    """No project.yml were found in the current directory or parent directories"""

    pass


class WorkspaceDoesNotExistError(KeyError):
    """Workspace does not exist"""

    pass


class CommandCancelledError(asyncio.CancelledError):
    def __init__(self, command: Command) -> None:
        msg = "Command failed"
        super().__init__(msg)
        self.command = command
        self.msg = msg


class CommandFailedError(multiprocessing.ProcessError):
    def __init__(self, command: Command, expected_rc: int = 0) -> None:
        msg = f"Command failed. Expected: rc={expected_rc} Actual: rc={command.process.returncode}."
        super().__init__(msg)
        self.command = command
        self.expected_rc = expected_rc
        self.rc = command.process.returncode
        self.msg = msg
