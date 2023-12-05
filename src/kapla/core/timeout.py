from __future__ import annotations

from typing import Optional

from anyio import current_time


def get_deadline(
    timeout: Optional[float] = None, deadline: Optional[float] = None
) -> float:
    """Get a deadline from either a timeout or a deadline.
    If both are None, float("inf") is returned.

    Args:
        timeout: value in seconds
        deadline: event loop time

    Returns:
        A float representing event loop time at which point timeout is reached
    """
    return (
        deadline if deadline else current_time() + timeout if timeout else float("inf")
    )


def get_timeout(
    timeout: Optional[float] = None, deadline: Optional[float] = None
) -> float:
    """Get a timeout from either a timeout or a deadline.
    If both are None, float("inf") is returned.

    Args:
        timeout: value in seconds
        deadline: event loop time

    Returns:
        A float representing number of seconds to wait before timeout is reached
    """
    return (
        timeout if timeout else deadline - current_time() if deadline else float("inf")
    )


def check_deadline(value: float) -> bool:
    """Check if deadline is still valid"""
    return value > current_time()
