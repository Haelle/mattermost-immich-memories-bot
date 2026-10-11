import asyncio
from dataclasses import dataclass
from datetime import date

import httpx

RETRIES = 2


class ImmichKeyRejected(Exception):
    pass


class ImmichUnavailable(Exception):
    pass


@dataclass(frozen=True)
class Memory:
    id: str
    year: int
    asset_count: int
    cover_asset_id: str


class ImmichClient:
    def __init__(self, base_url: str, api_key: str, http: httpx.AsyncClient, retry_delay_seconds: float = 5):
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._http = http
        self._retry_delay_seconds = retry_delay_seconds

    async def memories_on(self, day: date) -> list[Memory]:
        response = await self._get("/api/memories", params={"for": day.isoformat()})
        memories = [
            Memory(
                id=item["id"],
                year=item["data"]["year"],
                asset_count=len(item["assets"]),
                cover_asset_id=item["assets"][0]["id"],
            )
            for item in response.json()
            if item["type"] == "on_this_day" and item["assets"]
        ]
        return sorted(memories, key=lambda memory: memory.year, reverse=True)

    async def thumbnail(self, asset_id: str) -> bytes:
        response = await self._get(f"/api/assets/{asset_id}/thumbnail", params={"size": "preview"})
        return response.content

    async def _get(self, path: str, params: dict[str, str]) -> httpx.Response:
        failure = ""
        for attempt in range(RETRIES + 1):
            if attempt:
                await asyncio.sleep(self._retry_delay_seconds)
            try:
                response = await self._http.get(
                    self._base_url + path, params=params, headers={"x-api-key": self._api_key}
                )
            except httpx.TransportError as error:
                failure = type(error).__name__
                continue
            if response.status_code in (401, 403):
                raise ImmichKeyRejected(f"Immich rejected the API key ({response.status_code})")
            if response.status_code >= 500:
                failure = f"HTTP {response.status_code}"
                continue
            response.raise_for_status()
            return response
        raise ImmichUnavailable(f"Immich unavailable after {RETRIES + 1} attempts: {failure}")
