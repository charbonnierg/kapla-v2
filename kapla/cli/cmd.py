from pathlib import Path
import sys
from typing import Any, List, Mapping, Optional, Union

from anyio import create_task_group, open_process
from anyio.abc import Process
from anyio.streams.text import TextReceiveStream


def echo(text: str) -> None:
    print(text, file=sys.stdout, end="")

async def run_cmd(
    cmd: Union[str, List[str]],
    cwd: Union[str, bytes, Path, None] = None,
    env: Optional[Mapping[str, str]] = None,
    **kwargs: Any
) -> Process:
    async with await open_process(cmd, cwd=cwd, env=env, **kwargs) as process:
        async with create_task_group() as tg:
            tg.start_soon(print_stdout, process)
            tg.start_soon(print_stderr, process)
    return process


async def print_stdout(process: Process) -> None:
    if process.stdout:
        async for text in TextReceiveStream(process.stdout):
            echo(text)

async def print_stderr(process: Process) -> None:
    if process.stderr:
        async for text in TextReceiveStream(process.stderr):
            echo(text)
