from datetime import date, datetime, time

import httpx
import pytest
from cryptography.fernet import Fernet
from fakes import FakeImmich, FakeMattermost, memory_payload

from souvenirs.immich import ImmichClient
from souvenirs.mattermost import MattermostClient
from souvenirs.sender import Outcome, Sender
from souvenirs.store import Store

DAY = date(2026, 10, 11)


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "souvenirs.db", Fernet.generate_key())


@pytest.fixture
def immich():
    return FakeImmich()


@pytest.fixture
def mattermost():
    return FakeMattermost()


@pytest.fixture
def sender(store, immich, mattermost):
    immich_http = httpx.AsyncClient(transport=httpx.MockTransport(immich))
    mattermost_http = httpx.AsyncClient(transport=httpx.MockTransport(mattermost))
    return Sender(
        store=store,
        mattermost=MattermostClient("https://mm.example", "bot-token", mattermost_http),
        immich_for=lambda api_key: ImmichClient("http://immich:2283", api_key, immich_http, retry_delay_seconds=0),
        link_template="immich://memory?id={id}",
        interval_minutes=60,
    )


def posted_messages(mattermost):
    return mattermost.bodies("/api/v4/posts")


async def test_deliver_posts_memories_with_covers_and_marks_sent(sender, store, immich, mattermost):
    store.register("u1", "dm-u1", "key-u1", time(9, 0))
    immich.memories_by_key["key-u1"] = [
        memory_payload("m2021", 2021, ["a1", "a2"]),
        memory_payload("m2016", 2016, ["a3"]),
    ]

    outcome = await sender.deliver(store.get("u1"), DAY)

    assert outcome is Outcome.SENT
    [post] = posted_messages(mattermost)
    assert post["channel_id"] == "dm-u1"
    assert "immich://memory?id=m2021" in post["message"]
    assert "immich://memory?id=m2016" in post["message"]
    assert post["file_ids"] == ["file-1", "file-2"]
    uploads = [request.content for request in mattermost.requests if request.url.path == "/api/v4/files"]
    assert b"jpeg-a1" in uploads[0] and b"jpeg-a3" in uploads[1]
    assert store.get("u1").last_sent_on == DAY


async def test_no_memories_sends_nothing(sender, store, mattermost):
    store.register("u1", "dm-u1", "key-u1", time(9, 0))

    outcome = await sender.deliver(store.get("u1"), DAY)

    assert outcome is Outcome.NO_MEMORIES
    assert posted_messages(mattermost) == []
    assert store.get("u1").last_sent_on is None


async def test_missing_thumbnail_still_sends_link(sender, store, immich, mattermost):
    store.register("u1", "dm-u1", "key-u1", time(9, 0))
    immich.memories_by_key["key-u1"] = [memory_payload("m2021", 2021, ["broken"])]
    immich.missing_thumbnails.add("broken")

    outcome = await sender.deliver(store.get("u1"), DAY)

    assert outcome is Outcome.SENT
    [post] = posted_messages(mattermost)
    assert "immich://memory?id=m2021" in post["message"]
    assert post["file_ids"] == []


async def test_rejected_key_deactivates_and_warns_once(sender, store, immich, mattermost):
    store.register("u1", "dm-u1", "key-u1", time(9, 0))
    immich.rejected_keys.add("key-u1")

    outcome = await sender.deliver(store.get("u1"), DAY)

    assert outcome is Outcome.KEY_REJECTED
    user = store.get("u1")
    assert user.active is False
    assert user.last_error
    [warning] = posted_messages(mattermost)
    assert warning["channel_id"] == "dm-u1"
    assert "/souvenirs activer" in warning["message"]


async def test_immich_down_records_error_without_message(sender, store, immich, mattermost):
    store.register("u1", "dm-u1", "key-u1", time(9, 0))
    immich.down = True

    outcome = await sender.deliver(store.get("u1"), DAY)

    assert outcome is Outcome.FAILED
    assert posted_messages(mattermost) == []
    user = store.get("u1")
    assert user.active is True
    assert "503" in user.last_error


async def test_mattermost_failure_does_not_mark_sent(sender, store, immich, mattermost):
    store.register("u1", "dm-u1", "key-u1", time(9, 0))
    immich.memories_by_key["key-u1"] = [memory_payload("m2021", 2021, ["a1"])]
    mattermost.failing_posts = True

    outcome = await sender.deliver(store.get("u1"), DAY)

    assert outcome is Outcome.FAILED
    user = store.get("u1")
    assert user.last_sent_on is None
    assert "500" in user.last_error


async def test_tick_sends_only_to_due_users_not_yet_served_today(sender, store, immich, mattermost):
    for user_id in ["due", "later", "served", "u-gone"]:
        store.register(user_id, f"dm-{user_id}", f"key-{user_id}", time(9, 0))
        immich.memories_by_key[f"key-{user_id}"] = [memory_payload(f"m-{user_id}", 2021, ["a1"])]
    store.set_send_time("due", time(8, 30))
    store.set_send_time("later", time(10, 0))
    store.mark_sent("served", DAY)

    await sender.run_tick(datetime(2026, 10, 11, 9, 0))

    assert [post["channel_id"] for post in posted_messages(mattermost)] == ["dm-due"]


async def test_tick_continues_after_a_failing_user(sender, store, immich, mattermost):
    store.register("a-broken", "dm-broken", "key-broken", time(9, 0))
    store.register("b-fine", "dm-fine", "key-fine", time(9, 0))
    immich.rejected_keys.add("key-broken")
    immich.memories_by_key["key-fine"] = [memory_payload("m2021", 2021, ["a1"])]

    await sender.run_tick(datetime(2026, 10, 11, 9, 0))

    assert store.get("b-fine").last_sent_on == DAY
    assert store.get("a-broken").active is False
