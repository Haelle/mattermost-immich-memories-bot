import asyncio
import contextlib
import logging
import os
from contextlib import asynccontextmanager

import httpx
import uvicorn
from fastapi import FastAPI

from souvenirs.app import create_app
from souvenirs.config import Settings
from souvenirs.immich import ImmichClient
from souvenirs.mattermost import MattermostClient
from souvenirs.scheduler import run_scheduler
from souvenirs.sender import Sender
from souvenirs.store import Store

logger = logging.getLogger("souvenirs")


async def log_immich_version(http: httpx.AsyncClient, immich_url: str) -> None:
    try:
        version = (await http.get(immich_url.rstrip("/") + "/api/server/version")).raise_for_status().json()
        logger.info("Immich server version %s.%s.%s", version["major"], version["minor"], version["patch"])
    except (httpx.HTTPError, KeyError, ValueError) as error:
        logger.warning("Immich server version unknown: %s", error)


def build_app(settings: Settings) -> FastAPI:
    http = httpx.AsyncClient(timeout=30)
    store = Store(settings.db_path, settings.master_key)
    mattermost = MattermostClient(settings.mm_url, settings.mm_bot_token, http)

    def immich_for(api_key: str) -> ImmichClient:
        return ImmichClient(settings.immich_url, api_key, http)

    sender = Sender(store, mattermost, immich_for, settings.link_template, settings.check_interval_minutes)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await log_immich_version(http, settings.immich_url)
        scheduler = asyncio.create_task(run_scheduler(sender, settings.check_interval_minutes))
        yield
        scheduler.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await scheduler
        await http.aclose()

    return create_app(
        store=store,
        mattermost=mattermost,
        immich_for=immich_for,
        sender=sender,
        command_tokens=settings.command_tokens,
        callback_url=settings.callback_url,
        lifespan=lifespan,
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = Settings.from_env(os.environ)
    uvicorn.run(build_app(settings), host="0.0.0.0", port=8000)
