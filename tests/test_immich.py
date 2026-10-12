from datetime import date

import httpx
import pytest
from fakes import memory_payload

from souvenirs.immich import ImmichClient, ImmichKeyRejected, ImmichUnavailable, Memory


def client_for(handler):
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return ImmichClient("http://immich:2283", "user-key", http, retry_delay_seconds=0)


async def test_memories_keep_only_on_this_day_most_recent_first():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(
            200,
            json=[
                memory_payload("m2016", 2016, ["a1"]),
                memory_payload("other", 2020, ["a9"], memory_type="some_future_type"),
                memory_payload("m2021", 2021, ["a2", "a3", "a4"]),
            ],
        )

    memories = await client_for(handler).memories_on(date(2026, 10, 11))

    assert memories == [
        Memory(id="m2021", year=2021, asset_count=3, cover_asset_id="a2"),
        Memory(id="m2016", year=2016, asset_count=1, cover_asset_id="a1"),
    ]
    assert requests[0].url == "http://immich:2283/api/memories?for=2026-10-11"
    assert requests[0].headers["x-api-key"] == "user-key"


async def test_memory_without_assets_is_ignored():
    def handler(request):
        return httpx.Response(200, json=[memory_payload("empty", 2020, [])])

    assert await client_for(handler).memories_on(date(2026, 10, 11)) == []


@pytest.mark.parametrize("status", [401, 403])
async def test_rejected_key_raises_without_retry(status):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(status, json={"message": "Invalid API key"})

    with pytest.raises(ImmichKeyRejected):
        await client_for(handler).memories_on(date(2026, 10, 11))
    assert len(calls) == 1


async def test_server_error_is_retried_twice_then_raises_unavailable():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(502)

    with pytest.raises(ImmichUnavailable):
        await client_for(handler).memories_on(date(2026, 10, 11))
    assert len(calls) == 3


async def test_transient_failure_recovers_on_retry():
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            raise httpx.ConnectError("connection refused")
        return httpx.Response(200, json=[])

    assert await client_for(handler).memories_on(date(2026, 10, 11)) == []
    assert len(calls) == 2


async def test_latest_memory_is_the_most_recently_shown_with_its_day():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(
            200, json=[memory_payload("m2019", 2019, ["a1", "a2"], show_at="2026-10-08T12:00:00.000Z")]
        )

    latest = await client_for(handler).latest_memory()

    assert latest == (date(2026, 10, 8), Memory(id="m2019", year=2019, asset_count=2, cover_asset_id="a1"))
    assert requests[0].url.params == httpx.QueryParams(
        {"type": "on_this_day", "isUpcoming": "false", "order": "desc", "size": "1"}
    )


async def test_latest_memory_is_none_when_immich_has_none():
    def handler(request):
        return httpx.Response(200, json=[])

    assert await client_for(handler).latest_memory() is None


async def test_thumbnail_returns_preview_bytes():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, content=b"\xff\xd8jpeg", headers={"content-type": "image/jpeg"})

    content = await client_for(handler).thumbnail("a2")

    assert content == b"\xff\xd8jpeg"
    assert requests[0].url == "http://immich:2283/api/assets/a2/thumbnail?size=preview"
