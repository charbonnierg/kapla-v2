from __future__ import annotations

import os
import shlex
import sys
from contextlib import AsyncExitStack
from functools import partial
from pathlib import Path
from typing import Any, Callable, Iterable, List, Mapping, Optional, TextIO, Union

from anyio import create_task_group, move_on_after, open_process
from anyio._core._eventloop import get_asynclib
from anyio.streams.text import TextReceiveStream

from .errors import CommandCancelledError, CommandFailedError
from .logger import logger


def echo(text: str, file: TextIO = sys.stdout) -> None:
    """Default function to handle text characters.

    Note that this function does not process lines, but strings of arbitrary length which may or may not be whole lines.
    That's why `end=""` is used.
    """
    print(text, file=file, end="")


def current_clock_time() -> float:
    """Get current clock time. Do not use as timestamp !"""
    return get_asynclib().current_time()  # type: ignore[no-any-return]


def get_deadline(
    timeout: Optional[float] = None, deadline: Optional[float] = None
) -> float:
    return (
        deadline
        if deadline
        else current_clock_time() + timeout
        if timeout
        else float("inf")
    )


class Command:
    def __init__(
        self,
        cmd: Union[str, List[str]],
        cwd: Union[str, Path, None] = None,
        env: Optional[Mapping[str, str]] = None,
        append_path: Optional[Union[str, Path, List[Union[str, Path]], None]] = None,
        timeout: Optional[float] = None,
        deadline: Optional[float] = None,
        echo_stdout: Optional[Callable[[str], None]] = echo,
        echo_stderr: Optional[Callable[[str], None]] = partial(echo, file=sys.stderr),
        **kwargs: Any,
    ) -> None:
        """Run a command asynchronously using a context manager"""
        self.cmd = cmd
        self.cwd = Path(cwd) if cwd else Path.cwd()
        self._deadline = deadline
        self._timeout = timeout
        self.echo_stdout = echo_stdout
        self.echo_stderr = echo_stderr
        environment = os.environ.copy()
        if isinstance(append_path, (str, Path)):
            append_path = [append_path]
        if append_path:
            for path in append_path:
                path = Path(path).resolve(True)
                environment["PATH"] = ":".join([path.as_posix(), environment["PATH"]])
        if env:
            environment.update(env)
        self.options = {
            "cwd": cwd,
            "env": environment,
            **kwargs,
        }
        self.stdout: str = ""
        self.stderr: str = ""

    @property
    def cancelled(self) -> bool:
        try:
            return self._cancel_scope.cancel_called
        except AttributeError:
            return False

    @property
    def deadline(self) -> float:
        try:
            return self._cancel_scope.deadline
        except AttributeError:
            if self._deadline:
                return self._deadline
            elif self._timeout:
                return current_clock_time() + self._timeout
            else:
                return float("inf")

    @property
    def timeout(self) -> Optional[float]:
        return (
            self._deadline - current_clock_time() if self._deadline else self._timeout
        )

    @property
    def code(self) -> Optional[int]:
        try:
            return self.process.returncode
        except AttributeError:
            return False

    async def _process_stderr(self) -> None:
        if self.process.stderr:
            async for text in TextReceiveStream(self.process.stderr):
                self.stderr += text
                if self.echo_stderr:
                    self.echo_stderr(text)

    async def _process_stdout(self) -> None:
        if self.process.stdout:
            async for text in TextReceiveStream(self.process.stdout):
                self.stdout += text
                if self.echo_stdout:
                    self.echo_stdout(text)

    def __repr__(self) -> str:
        return f"Command(cmd={self.cmd}, done={self.code is not None}, rc={self.code}, cwd={self.cwd.as_posix()})"

    async def __aenter__(self) -> Command:
        self._exitstack = AsyncExitStack()

        await self._exitstack.__aenter__()
        self._cancel_scope = await self._exitstack.enter_async_context(
            move_on_after(self.timeout)
        )
        logger.info("Running command", cwd=self.cwd, cmd=self.cmd)
        self.process = await self._exitstack.enter_async_context(
            await open_process(self.cmd, **self.options)  # type: ignore[arg-type]
        )
        self.tg = await self._exitstack.enter_async_context(create_task_group())
        self.tg.start_soon(self._process_stdout)
        self.tg.start_soon(self._process_stderr)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):  # type: ignore[no-untyped-def]
        return await self._exitstack.__aexit__(exc_type, exc_val, exc_tb)

    def raise_on_error(self, success_rc: int = 0) -> None:
        """Raise an error if command was cancelled or failed.

        Failure is considered when return code is different than success_rc argument.
        """
        if self.cancelled:
            raise CommandCancelledError(command=self)
        if self.process.returncode != success_rc:
            raise CommandFailedError(command=self, expected_rc=success_rc)

    async def run(self, rc: Optional[int] = None) -> Command:
        """Run the command"""
        async with self:
            pass
        if rc is not None:
            self.raise_on_error(rc)
        # Return self in order to easily chain functions
        return self

    def add_argument(self, value: str) -> None:
        """Add an argument to the command"""
        if isinstance(self.cmd, str):
            self.cmd = " ".join([self.cmd, value])
        else:
            self.cmd.append(value)

    def add_option(
        self, flag: str, value: Optional[str] = None, escape: bool = False
    ) -> None:
        """Add an option to the command. Value can optionally be quoted using espace=True"""
        if isinstance(self.cmd, str):
            if value:
                if escape:
                    value = shlex.quote(value)
                self.cmd = " ".join([self.cmd, f"{flag}={value}"])
            else:
                self.cmd = " ".join([self.cmd, flag])
        else:
            if value:
                self.cmd.extend([flag, value])
            else:
                self.cmd.append(flag)

    def add_repeat_option(self, flag: str, values: Union[str, Iterable[str]]) -> None:
        """Add an option which can be repeated to the command"""
        if isinstance(values, str):
            values = [values]
        for value in values:
            self.add_option(flag, value)

    def add_separated_option(
        self, flag: str, values: Union[str, Iterable[str]], delimiter: str = ","
    ) -> None:
        """Add an option which accept a list of values separated by a delimiter"""
        if not isinstance(values, str):
            values = delimiter.join(values)
        self.add_option(flag, values)


async def run_command(
    cmd: Union[str, List[str]],
    cwd: Union[str, Path, None] = None,
    env: Optional[Mapping[str, str]] = None,
    append_path: Optional[Union[str, Path, List[Union[str, Path]], None]] = None,
    timeout: Optional[float] = None,
    deadline: Optional[float] = None,
    echo_stdout: Optional[Callable[[str], None]] = echo,
    echo_stderr: Optional[Callable[[str], None]] = echo,
    rc: Optional[int] = None,
    **kwargs: Any,
) -> Command:
    """Run a command asynchronously.

    By default, both stdout and stderr and printed to console.
    """
    command = Command(
        cmd,
        cwd=cwd,
        env=env,
        append_path=append_path,
        timeout=timeout,
        deadline=deadline,
        echo_stdout=echo_stdout,
        echo_stderr=echo_stderr,
        **kwargs,
    )
    return await command.run(rc=rc)


async def check_command(
    cmd: Union[str, List[str]],
    cwd: Union[str, Path, None] = None,
    env: Optional[Mapping[str, str]] = None,
    append_path: Optional[Union[str, Path, List[Union[str, Path]], None]] = None,
    timeout: Optional[float] = None,
    deadline: Optional[float] = None,
    echo_stdout: Optional[Callable[[str], None]] = None,
    echo_stderr: Optional[Callable[[str], None]] = None,
    rc: int = 0,
    **kwargs: Any,
) -> Command:
    """Run a command asynchronously.

    Behaves the same as run_command but raises an error in case of process error or when process is cancelled
    """
    command = Command(
        cmd,
        cwd=cwd,
        env=env,
        append_path=append_path,
        timeout=timeout,
        deadline=deadline,
        echo_stdout=echo_stdout,
        echo_stderr=echo_stderr,
        **kwargs,
    )
    return await command.run(rc)


async def check_command_stdout(
    cmd: Union[str, List[str]],
    cwd: Union[str, Path, None] = None,
    env: Optional[Mapping[str, str]] = None,
    timeout: Optional[float] = None,
    append_path: Optional[Union[str, Path, List[Union[str, Path]], None]] = None,
    deadline: Optional[float] = None,
    echo_stdout: Optional[Callable[[str], None]] = None,
    echo_stderr: Optional[Callable[[str], None]] = None,
    rc: Optional[int] = 0,
    **kwargs: Any,
) -> str:
    """Run a command asynchronously.

    Behaves the same as run_command but raises an error in case of process error or when process is cancelled by default.
    Disable raising error by setting rc=None.

    Return stdout content as a string.
    """
    command = Command(
        cmd,
        cwd=cwd,
        env=env,
        append_path=append_path,
        timeout=timeout,
        deadline=deadline,
        echo_stdout=echo_stdout,
        echo_stderr=echo_stderr,
        **kwargs,
    )
    await command.run(rc)
    return command.stdout


async def check_command_sterr(
    cmd: Union[str, List[str]],
    cwd: Union[str, Path, None] = None,
    env: Optional[Mapping[str, str]] = None,
    append_path: Optional[Union[str, Path, List[Union[str, Path]], None]] = None,
    timeout: Optional[float] = None,
    deadline: Optional[float] = None,
    echo_stdout: Optional[Callable[[str], None]] = None,
    echo_stderr: Optional[Callable[[str], None]] = None,
    rc: Optional[int] = 0,
    **kwargs: Any,
) -> str:
    """Run a command asynchronously.

    Behaves the same as run_command but can raises error if `raise_on_error` is set to True (default to False).

    Return stderr content as a string.
    """
    command = Command(
        cmd,
        cwd=cwd,
        env=env,
        append_path=append_path,
        timeout=timeout,
        deadline=deadline,
        echo_stdout=echo_stdout,
        echo_stderr=echo_stderr,
        **kwargs,
    )
    await command.run(rc)
    return command.stdout
