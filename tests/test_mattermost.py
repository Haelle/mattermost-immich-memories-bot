import httpx
import pytest
from fakes import FakeMattermost

from souvenirs.mattermost import MattermostClient


@pytest.fixture
def fake():
    return FakeMattermost()


@pytest.fixture
def client(fake):
    http = httpx.AsyncClient(transport=httpx.MockTransport(fake))
    return MattermostClient("https://mm.example", "bot-token", http)


async def test_direct_channel_pairs_bot_and_user(client, fake):
    channel_id = await client.direct_channel("u1")

    assert channel_id == "dm-channel"
    assert fake.bodies("/api/v4/channels/direct") == [["bot-id", "u1"]]


async def test_post_uploads_images_then_attaches_them(client, fake):
    await client.post("dm-channel", "hello", [b"img1", b"img2"])

    uploads = [request for request in fake.requests if request.url.path == "/api/v4/files"]
    assert len(uploads) == 2
    assert b'name="channel_id"' in uploads[0].content and b"dm-channel" in uploads[0].content
    assert fake.bodies("/api/v4/posts") == [
        {"channel_id": "dm-channel", "message": "hello", "file_ids": ["file-1", "file-2"]}
    ]


async def test_post_attaches_at_most_ten_images(client, fake):
    await client.post("dm-channel", "hello", [b"img"] * 12)

    assert fake.uploaded == 10
    assert len(fake.bodies("/api/v4/posts")[0]["file_ids"]) == 10


async def test_post_failure_raises(fake):
    def failing(request):
        return httpx.Response(500) if request.url.path == "/api/v4/posts" else fake(request)

    client = MattermostClient(
        "https://mm.example", "bot-token", httpx.AsyncClient(transport=httpx.MockTransport(failing))
    )

    with pytest.raises(httpx.HTTPStatusError):
        await client.post("dm-channel", "hello", [])


async def test_open_dialog_sends_trigger_and_callback(client, fake):
    dialog = {"callback_id": "activate", "title": "Souvenirs", "elements": []}

    await client.open_dialog("trigger-1", "http://souvenirs:8000/dialog", dialog)

    assert fake.bodies("/api/v4/actions/dialogs/open") == [
        {"trigger_id": "trigger-1", "url": "http://souvenirs:8000/dialog", "dialog": dialog}
    ]


async def test_deleted_user_is_not_active(client):
    assert await client.user_is_active("u1") is True
    assert await client.user_is_active("u-gone") is False
