import asyncio
from datetime import datetime, timedelta

import pytest

from souvenirs.scheduler import run_scheduler


class SimulatedTime:
    def __init__(self, start):
        self.now = start
        self.sleeps = []

    def clock(self):
        return self.now

    async def sleep(self, seconds):
        self.sleeps.append(seconds)
        if len(self.sleeps) > 3:
            raise asyncio.CancelledError
        self.now += timedelta(seconds=seconds)


class RecordingSender:
    def __init__(self, failing_ticks=0):
        self.ticks = []
        self.failing_ticks = failing_ticks

    async def run_tick(self, tick):
        self.ticks.append(tick)
        if len(self.ticks) <= self.failing_ticks:
            raise RuntimeError("boom")


async def test_scheduler_runs_on_interval_boundaries():
    simulated = SimulatedTime(datetime(2026, 10, 11, 9, 47, 12))
    sender = RecordingSender()

    with pytest.raises(asyncio.CancelledError):
        await run_scheduler(sender, 15, simulated.clock, simulated.sleep)

    assert sender.ticks == [
        datetime(2026, 10, 11, 10, 0),
        datetime(2026, 10, 11, 10, 15),
        datetime(2026, 10, 11, 10, 30),
    ]
    assert simulated.sleeps[0] == 12 * 60 + 48


async def test_scheduler_survives_a_failing_tick():
    simulated = SimulatedTime(datetime(2026, 10, 11, 9, 0, 30))
    sender = RecordingSender(failing_ticks=1)

    with pytest.raises(asyncio.CancelledError):
        await run_scheduler(sender, 60, simulated.clock, simulated.sleep)

    assert len(sender.ticks) == 3
