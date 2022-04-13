from __future__ import annotations

import os
import shlex
import signal
import sys
from asyncio import iscoroutinefunction
from contextlib import AsyncExitStack
from functools import partial
from pathlib import Path
from subprocess import PIPE
from types import TracebackType
from typing import (
    Any,
    Callable,
    Coroutine,
    Dict,
    Iterable,
    List,
    Mapping,
    Optional,
    Type,
    Union,
)

import chardet
from anyio import create_task_group, move_on_after, open_process
from anyio.abc import Process
from anyio.streams.buffered import BufferedByteReceiveStream

from .errors import CommandFailedError, CommandNotFoundError
from .timeout import get_deadline, get_event_loop_time, get_timeout
from .windows import IS_WINDOWS

STDOUT_SINK = partial(print, end="", sep="", file=sys.stdout)
STDERR_SINK = partial(print, end="", sep="", file=sys.stderr)


class Command:
    """Run a command asynchronously using a context manager"""

    def __init__(
        self,
        cmd: Union[str, List[str]],
        shell: Optional[bool] = None,
        cwd: Union[str, Path, None] = None,
        virtualenv: Union[str, Path, None] = None,
        env: Optional[Mapping[str, str]] = None,
        append_path: Optional[Union[str, Path, List[Union[str, Path]], None]] = None,
        timeout: Optional[float] = None,
        deadline: Optional[float] = None,
        stdin: int = PIPE,
        stdout: int = PIPE,
        stderr: int = PIPE,
        start_new_session: bool = False,
        stdout_sink: Union[
            Callable[[str], None], Callable[[str], Coroutine[None, None, None]], None
        ] = STDOUT_SINK,
        stderr_sink: Union[
            Callable[[str], None], Callable[[str], Coroutine[None, None, None]], None
        ] = STDERR_SINK,
        quiet: bool = False,
        rc: Optional[int] = None,
    ):
        """Create a new command instance"""
        cwd_path = Path(cwd) if cwd else Path.cwd()
        self.cwd = cwd_path.resolve(True)
        # Store private attributes
        self._timeout = get_timeout(timeout, deadline)
        self._deadline = get_deadline(timeout, deadline)
        self._stdin = stdin
        self._stdout = stdout
        self._stderr = stderr
        self._start_new_session = start_new_session
        # Store command
        if shell is None:
            self._cmd = cmd
        elif shell is True:
            self._cmd = cmd if isinstance(cmd, str) else shlex.join(cmd)
        elif shell is False:
            self._cmd = shlex.split(cmd) if isinstance(cmd, str) else cmd
        # Force start new session if cmd is a string
        if isinstance(self._cmd, str):
            self._start_new_session = True
        # Store expected return code
        self._expected_rc = rc
        # Store sinks
        self._stdout_sink = stdout_sink
        self._stderr_sink = stderr_sink
        # If quiet is set to True, remove default sinks
        if quiet:
            if self._stdout_sink is STDOUT_SINK:
                self._stdout_sink = None
            if self._stderr_sink is STDERR_SINK:
                self._stderr_sink = None
        # Fetch current environment
        environment = os.environ.copy()
        # Make sure append_path is a list (and not a string or a path instance)
        if isinstance(append_path, (str, Path)):
            append_path = [append_path]
        # Optionally add user provided environment variables
        if env:
            environment.update(env)
        # Update environment to execute command within virtual environment
        if virtualenv:
            virtualenv_path = Path(virtualenv)
            venv_bin = (
                virtualenv_path / "Scripts" if IS_WINDOWS else virtualenv_path / "bin"
            )
            environment.update({"VIRTUAL_ENV": virtualenv_path.as_posix()})
            if append_path:
                append_path.append(venv_bin)
            else:
                append_path = [venv_bin]
        # Optionally append directories to path environment variable
        if append_path:
            for path in append_path:
                path = Path(path).resolve(True)
                environment["PATH"] = ":".join([path.as_posix(), environment["PATH"]])
        # Store environment
        self.environment = environment
        # Initialize stdout and stderr which whill be parsed from command
        self._stdout_read: str = ""
        self._stderr_read: str = ""

    async def run(self, rc: Optional[int] = ..., timeout: Optional[float] = ..., deadline: Optional[float] = ...) -> Command:  # type: ignore[assignment]
        """Run the command"""
        if timeout is not ... and deadline is not ...:
            self._timeout = get_timeout(timeout, deadline)
            self._deadline = get_deadline(timeout, deadline)
        elif timeout is not ...:
            self._timeout = get_timeout(timeout, None)
            self._deadline = get_deadline(timeout, None)
        elif deadline is not ...:
            self._deadline = get_deadline(None, deadline)
            self._timeout = get_timeout(None, deadline)
        # Update expected rc
        if rc is not ...:
            self._expected_rc = rc
        # Simply enter the context manager to execute the command
        async with self:
            pass
        # Return self to easily chain function calls
        return self

    @property
    def options(self) -> Dict[str, Any]:
        """Get anyio options provided to open_process async context manager"""
        return {
            "command": self._cmd,
            "cwd": self.cwd.as_posix(),
            "env": self.environment,
            "stdin": self._stdin,
            "stdout": self._stdout,
            "stderr": self._stderr,
            "start_new_session": self._start_new_session,
        }

    @property
    def deadline(self) -> float:
        """Get command deadline"""
        return self._deadline

    @property
    def timeout(self) -> Optional[float]:
        """Get command timeout"""
        return self._timeout

    @property
    def pid(self) -> Optional[int]:
        """Return process ID"""
        try:
            return self.process.pid
        except AttributeError:
            return None

    @property
    def pgid(self) -> Optional[int]:
        """Return process group ID"""
        pid = self.pid
        if pid is None:
            return None
        if IS_WINDOWS:
            return None
        return os.getpgid(pid)

    @property
    def code(self) -> Optional[int]:
        """Get command return code (may be None if command is not started or done yet)"""
        try:
            return self.process.returncode
        except AttributeError:
            return None

    @property
    def cmd(self) -> str:
        """Return command as string"""
        if isinstance(self._cmd, str):
            return self._cmd
        else:
            return shlex.join(self._cmd)

    @property
    def tokens(self) -> List[str]:
        """Return command as a list"""
        if isinstance(self._cmd, str):
            return shlex.split(self._cmd)
        else:
            return self._cmd

    @property
    def stdout(self) -> str:
        """Return stdout read from command output"""
        return self._stdout_read

    @property
    def lines(self) -> List[str]:
        """Return lines splited from command output"""
        return self._stdout_read.strip().splitlines(False)

    @property
    def stderr(self) -> str:
        """Teturn stderr read from command output"""
        return self._stderr_read

    def __repr__(self) -> str:
        """Human friendly string representation of a command"""
        return f"Command(cmd={shlex.quote(self.cmd)}, pid={self.pid}, rc={self.code}, cwd={self.cwd.as_posix()})"

    async def __aenter__(self) -> Command:
        """Start the command using an asynchronous context manager"""
        return await self.fire()

    async def __aexit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> None:
        """Exit async context manager by exiting async exit stack"""
        # Wait until process is complete
        await self.gather(exc_type, exc_val, exc_tb)

    async def fire(self) -> Command:
        """Start the command"""
        if self.deadline < get_event_loop_time():
            raise
        # It is needed to ensure that we will properly enter and exit nested context managers
        self._exitstack = AsyncExitStack()
        # Enter the exit stack
        await self._exitstack.__aenter__()
        # Enter process async manager
        try:
            self.process: Process = await self._exitstack.enter_async_context(
                await open_process(**self.options)
            )
        except FileNotFoundError:
            raise CommandNotFoundError(command=self)
        # Enter task group context manager
        self.tg = await self._exitstack.enter_async_context(create_task_group())
        # Kick off processing tasks
        self.tg.start_soon(self._process_stdout)
        self.tg.start_soon(self._process_stderr)
        self.tg.start_soon(self.process.wait)
        # Return command instance
        return self

    async def gather(
        self,
        exc_type: Optional[Type[BaseException]] = None,
        exc_val: Optional[BaseException] = None,
        exc_tb: Optional[TracebackType] = None,
    ) -> None:
        # Exit early if an exception is encountered when exiting context manager
        if exc_type is not None:
            try:
                # Terminate process on exception
                self.terminate()
                # Wait for process to complete
                await self.wait()
            finally:
                # Exit stack
                await self._exitstack.__aexit__(exc_type, exc_val, exc_tb)
                # Exit function
                return
        # Wait for the process to finish using timeout
        try:
            returncode = await self.wait(deadline=self.deadline)
            if returncode is None:
                # Terminate process it is still pending after deadline
                self.terminate()
                # Wait for process to commplete
                await self.wait()
        except BaseException:
            # Terminate process on exception while waiting
            self.terminate()
            # Wait for process to complete
            await self.wait()
            # Raise error back
            raise
        # In any case
        finally:
            # Gather new exc info at this point
            exc_type, exc_val, exc_tb = sys.exc_info()
            # Exit async stack
            await self._exitstack.__aexit__(exc_type, exc_val, exc_tb)
            # Optionally check rc
            if self._expected_rc is not None:
                self.raise_on_error(self._expected_rc)

    async def wait(
        self, timeout: Optional[float] = None, deadline: Optional[float] = None
    ) -> Optional[int]:
        """Wait for command process to complete"""
        pid: Optional[int] = None
        with move_on_after(get_timeout(timeout, deadline)):
            pid = await self.process.wait()
        return pid

    def terminate(self) -> None:
        """Terminate command process (send SIGTERM)"""
        if IS_WINDOWS:
            return self.process.terminate()
        else:
            return self.send_signal(signal.SIGTERM)

    def kill(self) -> None:
        """Kill command process (send SIGKILL)"""
        if IS_WINDOWS:
            return self.process.kill()
        else:
            return self.send_signal(signal.SIGKILL)

    def send_signal(self, _signal: int) -> None:
        """Send signal to command process"""
        valid_signal = signal.Signals(_signal)
        if IS_WINDOWS:
            try:
                return self.process.send_signal(valid_signal)
            except (ProcessLookupError, FileNotFoundError):
                return
        pid = self.pid
        if pid is None:
            return
        try:
            if self._start_new_session:
                pgid = os.getpgid(pid)
                os.killpg(pgid, valid_signal.value)
            else:
                self.process.send_signal(valid_signal)
        except ProcessLookupError:
            return

    async def _process_stderr(self) -> None:
        """Process incoming stream of text received from command stderr"""
        default_encoding = "utf-8"
        if self.process.stderr:
            async for chunk in BufferedByteReceiveStream(self.process.stderr):
                try:
                    text = chunk.decode(default_encoding)
                except UnicodeDecodeError:
                    default_encoding = chardet.detect(chunk)["encoding"]
                    text = chunk.decode(default_encoding)
                self._stderr_read += text
                if iscoroutinefunction(self._stderr_sink):
                    await self._stderr_sink(text)  # type: ignore[misc]
                elif self._stderr_sink:
                    self._stderr_sink(text)

    async def _process_stdout(self) -> None:
        """Process incoming stream if text received from command stdout"""
        default_encoding = "utf-8"
        if self.process.stdout:
            async for chunk in BufferedByteReceiveStream(self.process.stdout):
                try:
                    text = chunk.decode(default_encoding)
                except UnicodeDecodeError:
                    default_encoding = chardet.detect(chunk)["encoding"]
                    text = chunk.decode(default_encoding)
                self._stdout_read += text
                if iscoroutinefunction(self._stdout_sink):
                    await self._stdout_sink(text)  # type: ignore[misc]
                elif self._stdout_sink:
                    self._stdout_sink(text)

    def raise_on_error(self, expected_rc: Optional[int] = None) -> None:
        """Raise an error if command was cancelled or failed.

        Failure is considered when return code is different than expected_rc argument.
        """
        # If no expected return code is provided
        if expected_rc is None:
            # Expect a return code 0 by default
            if self._expected_rc is None:
                expected_rc = 0
            # Expect return code found in command instance if it exists
            else:
                expected_rc = self._expected_rc
        # Raise an error if actual return code is different from expected return code
        if self.process.returncode != expected_rc:
            raise CommandFailedError(command=self, expected_rc=expected_rc)

    def add_argument(
        self, value: str, escape: bool = True, fmt: Optional[str] = None
    ) -> None:
        """Add an argument to the command"""
        if escape:
            value = shlex.quote(value)
        if fmt:
            value = format(value, fmt)
        if isinstance(self._cmd, str):
            self._cmd = " ".join([self._cmd, value])
        else:
            self._cmd.append(value)

    def add_option(
        self,
        flag: str,
        value: Optional[str] = None,
        eq: str = "=",
        escape: bool = True,
        fmt: Optional[str] = None,
    ) -> None:
        """Add an option to the command. Value can optionally be quoted using espace=True"""
        if isinstance(self._cmd, str):
            if value:
                if escape:
                    value = shlex.quote(value)
                if fmt:
                    value = format(value, fmt)
                self._cmd = " ".join([self._cmd, f"{flag}{eq}{value}"])
            else:
                self._cmd = " ".join([self._cmd, flag])
        else:
            if value:
                self._cmd.extend([flag, value])
            else:
                self._cmd.append(flag)

    def add_repeat_option(
        self,
        flag: str,
        values: Union[str, Iterable[str]],
        eq: str = "=",
        sep: Optional[str] = None,
        escape: bool = True,
        fmt: Optional[str] = None,
    ) -> None:
        """Add an option which can be repeated to the command"""
        if isinstance(values, str):
            values = [values]
        if sep is None:
            for value in values:
                self.add_option(flag, value, eq=eq, escape=escape, fmt=fmt)
        else:
            if not isinstance(values, str):
                values = sep.join(values)
            self.add_option(flag, values, eq=eq, escape=escape, fmt=fmt)

    def add_kv_option(
        self,
        flag: str,
        options: Optional[Mapping[str, str]] = None,
        sep: str = ",",
        eq: str = "=",
        inner_eq: str = "=",
        escape: bool = True,
        fmt: Optional[str] = None,
        **kwargs: str,
    ) -> None:
        """Add a key value option such as --build-arg=KEY=VALUE"""
        _values: List[str] = []
        options = {**options} if options else {}
        if kwargs:
            options.update(kwargs)
        for key, value in options.items():
            if fmt:
                value = format(value, fmt)
            _values.append(inner_eq.join([key, value]))

        self.add_option(flag, sep.join(_values), eq=eq, escape=escape, fmt=None)

    def add_repeat_options(
        self,
        flag: str,
        values: Union[Iterable[Union[Iterable[str], str]], str],
        eq: str = "=",
        sep: str = ",",
        escape: bool = True,
    ) -> None:
        if isinstance(values, str):
            values = [values]
        for value in values:
            self.add_repeat_option(flag, value, eq=eq, sep=sep, escape=escape)

    def add_kv_options(
        self,
        flag: str,
        options: Union[Dict[str, str], Iterable[Mapping[str, str]]],
        eq: str = "=",
        inner_eq: str = "=",
        sep: str = ",",
        escape: bool = True,
    ) -> None:
        """Add a key value option such as --build-arg=KEY=VALUE"""
        if isinstance(options, dict):
            options = [options]
        for _options in options:
            self.add_kv_option(
                flag, _options, sep=sep, eq=eq, inner_eq=inner_eq, escape=escape
            )

    def add_options(
        self,
        options: Mapping[str, Union[str, Iterable[str]]],
        escape: bool = True,
    ) -> None:
        """Add a bunch of options from a mapping"""
        for flag, values in options.items():
            # add_repeat_option accept both string or iterable of strings
            self.add_repeat_option(flag, values, escape=escape)


async def run_command(
    cmd: Union[str, List[str]],
    shell: Optional[bool] = None,
    cwd: Union[str, Path, None] = None,
    virtualenv: Union[str, Path, None] = None,
    env: Optional[Mapping[str, str]] = None,
    append_path: Optional[Union[str, Path, List[Union[str, Path]], None]] = None,
    timeout: Optional[float] = None,
    deadline: Optional[float] = None,
    stdin: int = PIPE,
    stdout: int = PIPE,
    stderr: int = PIPE,
    start_new_session: bool = False,
    stdout_sink: Union[
        Callable[[str], None], Callable[[str], Coroutine[None, None, None]], None
    ] = STDOUT_SINK,
    stderr_sink: Union[
        Callable[[str], None], Callable[[str], Coroutine[None, None, None]], None
    ] = STDERR_SINK,
    quiet: bool = False,
    rc: Optional[int] = None,
) -> Command:
    """Run a command asynchronously.

    By default, both stdout and stderr and printed to console.
    """
    command = Command(
        cmd,
        shell=shell,
        cwd=cwd,
        virtualenv=virtualenv,
        env=env,
        append_path=append_path,
        timeout=timeout,
        deadline=deadline,
        stdin=stdin,
        stdout=stdout,
        stderr=stderr,
        start_new_session=start_new_session,
        stdout_sink=stdout_sink,
        stderr_sink=stderr_sink,
        quiet=quiet,
        rc=rc,
    )
    return await command.run()


async def check_command(
    cmd: Union[str, List[str]],
    shell: Optional[bool] = None,
    cwd: Union[str, Path, None] = None,
    virtualenv: Union[str, Path, None] = None,
    env: Optional[Mapping[str, str]] = None,
    append_path: Optional[Union[str, Path, List[Union[str, Path]], None]] = None,
    timeout: Optional[float] = None,
    deadline: Optional[float] = None,
    stdin: int = PIPE,
    stdout: int = PIPE,
    stderr: int = PIPE,
    start_new_session: bool = False,
    stdout_sink: Union[
        Callable[[str], None], Callable[[str], Coroutine[None, None, None]], None
    ] = STDOUT_SINK,
    stderr_sink: Union[
        Callable[[str], None], Callable[[str], Coroutine[None, None, None]], None
    ] = STDERR_SINK,
    quiet: bool = True,
    rc: int = 0,
) -> Command:
    """Run a command asynchronously.

    By default, both stdout and stderr and printed to console.
    """
    command = Command(
        cmd,
        shell=shell,
        cwd=cwd,
        virtualenv=virtualenv,
        env=env,
        append_path=append_path,
        timeout=timeout,
        deadline=deadline,
        stdin=stdin,
        stdout=stdout,
        stderr=stderr,
        start_new_session=start_new_session,
        stdout_sink=stdout_sink,
        stderr_sink=stderr_sink,
        quiet=quiet,
        rc=rc,
    )
    return await command.run()


async def check_command_stdout(
    cmd: Union[str, List[str]],
    shell: Optional[bool] = None,
    cwd: Union[str, Path, None] = None,
    virtualenv: Union[str, Path, None] = None,
    env: Optional[Mapping[str, str]] = None,
    append_path: Optional[Union[str, Path, List[Union[str, Path]], None]] = None,
    timeout: Optional[float] = None,
    deadline: Optional[float] = None,
    stdin: int = PIPE,
    start_new_session: bool = False,
    rc: Optional[int] = 0,
    strip: bool = False,
) -> str:
    """Run a command asynchronously and return stdout content as a string"""
    command = Command(
        cmd,
        shell=shell,
        cwd=cwd,
        virtualenv=virtualenv,
        env=env,
        append_path=append_path,
        timeout=timeout,
        deadline=deadline,
        stdin=stdin,
        stdout=PIPE,
        stderr=PIPE,
        start_new_session=start_new_session,
        stdout_sink=None,
        stderr_sink=None,
        quiet=True,
        rc=rc,
    )
    # Return command stdout
    await command.run()
    if strip:
        return command.stdout.strip()
    else:
        return command.stdout


async def check_command_sterr(
    cmd: Union[str, List[str]],
    shell: Optional[bool] = None,
    cwd: Union[str, Path, None] = None,
    virtualenv: Union[str, Path, None] = None,
    env: Optional[Mapping[str, str]] = None,
    append_path: Optional[Union[str, Path, List[Union[str, Path]], None]] = None,
    timeout: Optional[float] = None,
    deadline: Optional[float] = None,
    stdin: int = PIPE,
    start_new_session: bool = False,
    rc: Optional[int] = None,
    strip: bool = False,
) -> str:
    """Run a command asynchronously and return stderr read from output"""
    command = Command(
        cmd,
        shell=shell,
        cwd=cwd,
        virtualenv=virtualenv,
        env=env,
        append_path=append_path,
        timeout=timeout,
        deadline=deadline,
        stdin=stdin,
        stdout=PIPE,
        stderr=PIPE,
        start_new_session=start_new_session,
        stdout_sink=None,
        stderr_sink=None,
        quiet=True,
        rc=rc,
    )
    # Return command stdout
    await command.run()
    if strip:
        return command.stderr.strip()
    else:
        return command.stderr
