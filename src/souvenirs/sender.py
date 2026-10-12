import logging
from collections.abc import Awaitable, Callable
from datetime import date, datetime
from enum import Enum

import httpx

from souvenirs.immich import ImmichClient, ImmichKeyRejected, ImmichUnavailable, Memory
from souvenirs.mattermost import MAX_ATTACHMENTS, MattermostClient
from souvenirs.message import format_message
from souvenirs.schedule import is_due
from souvenirs.store import Store, User

logger = logging.getLogger(__name__)

KEY_REJECTED_WARNING = "Ta clé Immich ne fonctionne plus, relance `/souvenirs activer`."


class Outcome(Enum):
    SENT = "sent"
    NO_MEMORIES = "no_memories"
    KEY_REJECTED = "key_rejected"
    FAILED = "failed"


class Sender:
    def __init__(
        self,
        store: Store,
        mattermost: MattermostClient,
        immich_for: Callable[[str], ImmichClient],
        link_template: str,
        interval_minutes: int,
    ):
        self._store = store
        self._mattermost = mattermost
        self._immich_for = immich_for
        self._link_template = link_template
        self._interval_minutes = interval_minutes

    async def run_tick(self, tick: datetime) -> None:
        for user in self._store.active_users():
            if user.last_sent_on == tick.date() or not is_due(user.send_time, tick.time(), self._interval_minutes):
                continue
            try:
                if not await self._mattermost.user_is_active(user.mm_user_id):
                    logger.info("user=%s skipped: deactivated in Mattermost", user.mm_user_id)
                    continue
            except httpx.HTTPError as error:
                logger.error("user=%s skipped: Mattermost lookup failed: %s", user.mm_user_id, error)
                continue
            await self.deliver(user, tick.date())

    async def deliver(self, user: User, day: date) -> Outcome:
        async def memories_of_the_day(immich: ImmichClient) -> tuple[date, list[Memory]]:
            return day, await immich.memories_on(day)

        return await self._deliver(user, memories_of_the_day, mark_sent=True)

    async def deliver_latest(self, user: User) -> Outcome:
        async def latest_memory(immich: ImmichClient) -> tuple[date, list[Memory]] | None:
            latest = await immich.latest_memory()
            return (latest[0], [latest[1]]) if latest else None

        return await self._deliver(user, latest_memory, mark_sent=False)

    async def _deliver(
        self,
        user: User,
        fetch: Callable[[ImmichClient], Awaitable[tuple[date, list[Memory]] | None]],
        mark_sent: bool,
    ) -> Outcome:
        immich = self._immich_for(user.immich_key)
        try:
            found = await fetch(immich)
        except ImmichKeyRejected as error:
            self._store.deactivate(user.mm_user_id, str(error))
            await self._warn_key_rejected(user)
            return self._log(user, 0, Outcome.KEY_REJECTED, str(error))
        except (ImmichUnavailable, httpx.HTTPError) as error:
            self._store.record_error(user.mm_user_id, str(error))
            return self._log(user, 0, Outcome.FAILED, str(error))

        if not found or not found[1]:
            return self._log(user, 0, Outcome.NO_MEMORIES)
        day, memories = found

        covers = await self._covers(immich, memories)
        try:
            await self._mattermost.post(user.dm_channel_id, format_message(day, memories, self._link_template), covers)
        except httpx.HTTPError as error:
            self._store.record_error(user.mm_user_id, f"Mattermost post failed: {error}")
            return self._log(user, len(memories), Outcome.FAILED, str(error))
        if mark_sent:
            self._store.mark_sent(user.mm_user_id, day)
        return self._log(user, len(memories), Outcome.SENT)

    async def _covers(self, immich: ImmichClient, memories: list[Memory]) -> list[bytes]:
        covers = []
        for memory in memories[:MAX_ATTACHMENTS]:
            try:
                covers.append(await immich.thumbnail(memory.cover_asset_id))
            except (ImmichUnavailable, httpx.HTTPError) as error:
                logger.warning("memory=%s cover skipped: %s", memory.id, error)
        return covers

    async def _warn_key_rejected(self, user: User) -> None:
        try:
            await self._mattermost.post(user.dm_channel_id, KEY_REJECTED_WARNING, [])
        except httpx.HTTPError as error:
            logger.error("user=%s key rejection warning failed: %s", user.mm_user_id, error)

    def _log(self, user: User, memory_count: int, outcome: Outcome, detail: str = "") -> Outcome:
        logger.info("user=%s memories=%d outcome=%s %s", user.mm_user_id, memory_count, outcome.value, detail)
        return outcome
