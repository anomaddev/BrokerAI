from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from typing import TypeVar

T = TypeVar("T")


async def gather_limited(
    coros: list[Awaitable[T]],
    *,
    limit: int,
    return_exceptions: bool = True,
) -> list[T | BaseException]:
    """Run awaitables concurrently with a semaphore cap."""
    if not coros:
        return []

    sem = asyncio.Semaphore(max(1, limit))

    async def run(coro: Awaitable[T]) -> T:
        async with sem:
            return await coro

    return await asyncio.gather(
        *(run(coro) for coro in coros),
        return_exceptions=return_exceptions,
    )
