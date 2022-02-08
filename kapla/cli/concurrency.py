from __future__ import annotations

import asyncio
import sys
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from functools import partial
from multiprocessing import cpu_count
from types import TracebackType
from typing import (
    Any,
    Awaitable,
    Callable,
    Dict,
    Optional,
    Set,
    Tuple,
    Type,
    TypedDict,
    TypeVar,
)

if sys.version_info >= (3, 9):
    from collections import Counter
else:
    from typing_extensions import Counter

if sys.version_info >= (3, 10):
    from typing import ParamSpec
else:
    from typing_extensions import ParamSpec


T = TypeVar("T")
T_Return = TypeVar("T_Return")
T_Params = ParamSpec("T_Params")


class TaskPoolFullError(Exception):
    """Too many tasks are already running in task pool"""

    pass


class TaskPoolClosedError(Exception):
    """Task pool is closed and can no longer accept new tasks"""

    pass


class TaskPoolDrainingError(TaskPoolClosedError):
    """Task pool is draining and can no longer accept new tasks"""

    pass


class CancelledTimeoutError(asyncio.TimeoutError):
    """Task cancellation did not finish before timeout"""

    pass


class TaskPoolStats(TypedDict):
    """Statistics exposed by a task pool instance"""

    created: int
    completed: int
    cancelled: int
    failed: int
    pending: int


class TaskPool:
    """A task pool can be used to submit coroutine to the event loop while enforing a maximum number of coroutines to run at the same time.

    It's also useful to wait for a bunch of task created at different moment to finish.
    """

    def __init__(
        self,
        max_concurrency: Optional[int] = 1,
        thread_pool_size: Optional[int] = None,
        process_pool_size: Optional[int] = None,
    ) -> None:
        """Create a new instance of TaskPool.

        A task pool can be used as a concurrency limiter. It provides a create_method like asyncio

        Arguments:
            max_concurrency: Maximum number of tasks which can run in parallel in the task pool.
        """
        self.max_concurrency = int(max_concurrency) if max_concurrency else 0
        self._limiter: asyncio.Queue[None] = asyncio.Queue(maxsize=self.max_concurrency)
        self._stats = Counter[str]()
        self.tasks: Dict[str, asyncio.Task[Any]] = {}
        # An asyncio Future which will have a result set once task pool is closed
        self._will_close: asyncio.Future[None] = asyncio.Future()
        # A task pool is opened by default so there's no open attribute
        # It can be in two other states
        # Draining means that task pool no longer accept new tasks bure pending tasks have yet to finish.
        self.draining: bool = False
        # Closed means that task pool  no longer accept new tasks and all tasks have finished
        self.closed: bool = False
        total_cpu = cpu_count()
        max_cpu = total_cpu // 2 if total_cpu > 1 else total_cpu
        # Create a processpool and a threadpool execute
        self.process_pool = ProcessPoolExecutor(
            max_workers=process_pool_size or max_cpu
        )
        self.thread_pool = ThreadPoolExecutor(
            max_workers=thread_pool_size or max_cpu * 8
        )

    @property
    def stats(self) -> TaskPoolStats:
        return {
            "created": self._stats["created"],
            "completed": self._stats["completed"],
            "cancelled": self._stats["cancelled"],
            "failed": self._stats["failed"],
            "pending": len(self.tasks),
        }

    def _close_cb(self) -> None:
        self.closed = True
        self._will_close.set_result(None)
        self.process_pool.shutdown(wait=False)
        self.thread_pool.shutdown(wait=False)

    def _done_cb(self, name: str) -> None:
        """Callback executed after each task is finished.

        Each task is stored under self.tasks attribute using its name as key.
        When a task is finished, it must be removed else the dictionary would always keep growing in size.
        We also have the opportunity to execute a callback on an error at this moment, but the context is not asynchronous
        """
        # Queue act as a semaphore
        self._limiter.get_nowait()
        # Remove the task using its name
        task = self.tasks.pop(name, None)
        # No need to do anything if task is None
        if task is None:
            return
        # Increase finished counter
        self._stats["finished"] += 1
        # Fetch task exception (both can be None)
        if task is not None:
            try:
                exception = task.exception()
            except asyncio.CancelledError:
                # Increase cancelled counter
                self._stats["cancelled"] += 1
            else:
                # Increase failed counter
                if exception:
                    self._stats["failed"] += 1
                # Increase completed counter
                else:
                    self._stats["completed"] += 1
        # Notify limiter that task has been processed
        self._limiter.task_done()

    def _raise_on_state(self, msg: str) -> None:
        """Raise an error if task pool is closed or draining"""
        if self.closed:
            raise TaskPoolClosedError(msg)
        if self.draining:
            raise TaskPoolDrainingError(msg)

    def cancel(self) -> asyncio.Future[None]:
        """Cancel all pending tasks"""
        # Create a future which can be used to wait until all tasks are finished
        all_finished: asyncio.Future[None] = asyncio.Future()
        # Return future after setting result if there is no task
        if not self.tasks:
            all_finished.set_result(None)
            return all_finished
        # Cancel all tasks and get a list of futures which can be used to wait until tasks are finished
        cancelled_finished = [self.cancel_task(name) for name in self.tasks]
        # Create a new task which will wait until all pool tasks are finished
        task = asyncio.create_task(
            asyncio.wait(cancelled_finished, return_when=asyncio.ALL_COMPLETED)
        )
        # Once all pool tasks are finished set the all_cancelled future result
        task.add_done_callback(lambda _: all_finished.set_result(None))
        # Return the future
        return all_finished

    async def acancel(self, timeout: Optional[float] = None) -> None:
        """Cancel all pending tasks and wait until they are finished. If one or more task is not finished before timeout, a CancelTimeoutError is raised"""
        if not self.tasks:
            return
        _, pending = await asyncio.wait(
            [asyncio.create_task(self.acancel_task(name)) for name in self.tasks],
            timeout=timeout,
        )
        if pending:
            raise CancelledTimeoutError(
                f"Task were cancelled but {len(pending)} did not finish before timeout (timeout={timeout:.2f})"
            )

    def cancel_task(self, name: str) -> asyncio.Future[None]:
        """Cancel a task and return an asyncio.Future which can be awaited until task is finished"""
        # Create an asyncio.Future instance to denote when task is finished
        finished: asyncio.Future[None] = asyncio.Future()
        # Fetch the task from state
        # If it does not exist, no error is raised
        try:
            task = self.tasks[name]
        except KeyError:
            finished.set_result(None)
            return finished
        # Schedule a function to set result on the asyncio.Future instance once task is finished
        task.add_done_callback(lambda _: finished.set_result(None))
        # Cancel the task
        task.cancel()
        # Return the asyncio.Future instance
        return finished

    async def acancel_task(self, name: str, timeout: Optional[float] = None) -> None:
        """Cancel a task and wait for it to finish"""
        # Cancel and get an asyncio.Future instance
        cancelled = self.cancel_task(name)
        # Wait for the asyncio.Future to complete
        _, pending = await asyncio.wait([cancelled], timeout=timeout)
        # Raise an error which inherit from asyncio.TimeoutError but is more specific
        if pending:
            raise CancelledTimeoutError(
                f"Task was cancelled but did not finish before timeout (task={name}, timeout={timeout:.2f})"
            )

    def _create_task(
        self, coro: Awaitable[T], name: Optional[str] = None
    ) -> asyncio.Task[T]:
        """Create a new task without acquiring any lock. Use with caution."""
        # Kick off the task in the event loop
        task = asyncio.create_task(coro, name=name)
        # Increase created counter
        self._stats["created"] += 1
        # Name will either be generated by asyncio or will be user provided name
        task_name = task.get_name()
        # Store the task for later usage
        self.tasks[task_name] = task
        # Callback will be executed regardless of success or failure
        task.add_done_callback(lambda _: self._done_cb(task_name))
        # Return an asyncio task
        return task

    def add_task(self, task: asyncio.Task[Any]) -> None:
        """Attach an existing task to the task group"""
        task_name = task.get_name()
        self.tasks[task_name] = task
        task.add_done_callback(lambda _: self._done_cb(task_name))

    def create_task(
        self,
        coro: Awaitable[T],
        name: Optional[str] = None,
        retry: Optional[int] = None,
    ) -> asyncio.Task[T]:
        """Create a new task to run in the task pool. If task pool is full, an error is raised.

        If you want to wait for the task pool to have a free slot, or wait with a timeout, use
        `acreate_task` method instead.

        Arguments:
            coro: The coroutine to run in the task loop
            name: An optional string used as task name. Useful when debugging.

        Returns:
            An asyncio.Task instance that can be awaited upon using asyncio.wait_for

        Raises:
            TaskPoolFullError: When maximum number of tasks are already running in task pool
        """
        self._raise_on_state("Cannot create new task")
        # Don't wait, only try to acquire semaphore
        try:
            self._limiter.put_nowait(None)
        except asyncio.QueueFull:
            # Raise an appropriate error
            raise TaskPoolFullError(
                f"Failed to create task: concurrency limit is reached (limit={self.max_concurrency})"
            )
        # Return an asyncio task
        return self._create_task(coro, name=name)

    async def acreate_task(
        self,
        coro: Awaitable[T],
        name: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> asyncio.Task[T]:
        """Create a new task to run in the task pool. If task pool is full, the function waits until first task is finished and then submit the task.

        Arguments:
            coro: The coroutine to run in the task loop
            name: An optional string used as task name. Useful when debugging.

        Returns:
            An asyncio.Task instance that can be awaited upon using asyncio.wait_for
        """
        try:
            return self.create_task(coro, name=name)
        except TaskPoolFullError:
            try:
                asyncio.wait_for(self._limiter.put(None), timeout)
            except asyncio.TimeoutError:
                raise TaskPoolFullError(
                    f"Concurrency limit is reached (were limit={self.max_concurrency})"
                )
        return self._create_task(coro, name)

    async def drain(self, timeout: Optional[float] = None) -> None:
        """Wait for all tasks to finish until timeout then cancel pending tasks.

        As soon as drain is called, task pool no longer accept new tasks.
        """
        self._raise_on_state("Cannot drain task pool")
        # Close TaskPool
        self.draining = True

        # If there are no running tasks simply return
        if not self.tasks:
            self._close_cb()
            return

        # A try/except block used to ensure task pool is closed
        try:
            # Wait for all tasks to finish using a timeout
            _, pending = await asyncio.wait(
                list(self.tasks.values()),
                timeout=timeout,
                return_when=asyncio.ALL_COMPLETED,
            )
            # If there are remaining pending tasks
            if pending:
                # Cancel all tasks without timeout
                await self.acancel(None)
        finally:
            # Mark task pool as closed
            self._close_cb()

    def close(self) -> asyncio.Future[None]:
        """Close the task pool.

        If tasks are still running, pool might not be closed immediately.
        This function returns an asyncio.Future which can be used to wait until task pool is really closed.
        """
        if self.closed:
            return self._will_close
        all_finished = self.cancel()
        all_finished.add_done_callback(lambda _: self._close_cb())
        return all_finished

    async def aclose(self) -> None:
        """Close the task pool and wait for all pending tasks to finish after cancel.

        This function is similar to the synchronous close method except it waits for all tasks to finish.
        """
        closed = self.close()
        await asyncio.wait_for(closed, None)

    async def join(self) -> None:
        """Wait for all tasks to finish and task pool is closed"""
        await asyncio.wait_for(self._will_close, None)

    async def wait(
        self,
        timeout: Optional[float] = None,
        return_when: str = asyncio.ALL_COMPLETED,
    ) -> Tuple[Set[asyncio.Task[Any]], Set[asyncio.Task[Any]]]:
        """Wait for all pending tasks to finish. It does not close the task pool.

        This function behave like asyncio.wait and accept the same options timeout and return_when.
        """
        if not self.tasks:
            return (set(), set())
        return await asyncio.wait(
            list(self.tasks.values()), timeout=timeout, return_when=return_when
        )

    async def __aenter__(self) -> TaskPool:
        self._raise_on_state("Cannot activate task pool")
        return self

    async def __aexit__(
        self,
        exc_type: Type[BaseException],
        exc_val: BaseException,
        exc_tb: Optional[TracebackType],
    ) -> None:
        await self.drain()

    def create_task_in_process(
        self,
        func: Callable[T_Params, T_Return],
        name: Optional[str] = None,
    ) -> Callable[T_Params, Awaitable[T_Return]]:
        self._raise_on_state("Cannot create new task")

        def wrapper(
            *args: T_Params.args, **kwargs: T_Params.kwargs
        ) -> asyncio.Task[T_Return]:

            partial_f = partial(func, *args, **kwargs)

            async def submit() -> T_Return:
                return await asyncio.wait_for(
                    asyncio.get_running_loop().run_in_executor(
                        self.process_pool, partial_f
                    ),
                    None,
                )

            return self.create_task(submit(), name=name)

        return wrapper

    def create_task_in_thread(
        self,
        func: Callable[T_Params, T_Return],
        name: Optional[str] = None,
    ) -> Callable[T_Params, Awaitable[T_Return]]:
        self._raise_on_state("Cannot create new task")

        def wrapper(
            *args: T_Params.args, **kwargs: T_Params.kwargs
        ) -> asyncio.Task[T_Return]:

            partial_f = partial(func, *args, **kwargs)

            async def submit() -> T_Return:
                return await asyncio.wait_for(
                    asyncio.get_running_loop().run_in_executor(
                        self.thread_pool, partial_f
                    ),
                    None,
                )

            return self.create_task(submit(), name=name)

        return wrapper
