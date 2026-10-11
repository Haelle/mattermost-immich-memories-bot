import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Protocol

from souvenirs.schedule import next_tick

logger = logging.getLogger(__name__)


class TickRunner(Protocol):
    async def run_tick(self, tick: datetime) -> None: ...


async def run_scheduler(
    sender: TickRunner,
    interval_minutes: int,
    clock: Callable[[], datetime] = datetime.now,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> None:
    while True:
        tick = next_tick(clock(), interval_minutes)
        await sleep((tick - clock()).total_seconds())
        try:
            await sender.run_tick(tick)
        except Exception:
            logger.exception("tick %s failed", tick.isoformat(timespec="minutes"))
