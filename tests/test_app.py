from datetime import date, datetime, time, timedelta

import httpx
import pytest
from cryptography.fernet import Fernet
from fakes import FakeImmich, FakeMattermost, memory_payload
from fastapi.testclient import TestClient

from souvenirs.app import create_app
from souvenirs.immich import ImmichClient
from souvenirs.mattermost import MattermostClient
from souvenirs.sender import Sender
from souvenirs.store import Store

NOW = datetime(2026, 10, 11, 14, 0)


class Clock:
    def __init__(self):
        self.now = NOW

    def __call__(self):
        return self.now


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
def clock():
    return Clock()


@pytest.fixture
def client(store, immich, mattermost, clock):
    immich_http = httpx.AsyncClient(transport=httpx.MockTransport(immich))
    mattermost_client = MattermostClient(
        "https://mm.example", "bot-token", httpx.AsyncClient(transport=httpx.MockTransport(mattermost))
    )

    def immich_for(api_key):
        return ImmichClient("http://immich:2283", api_key, immich_http, retry_delay_seconds=0)

    sender = Sender(store, mattermost_client, immich_for, "immich://memory?id={id}", interval_minutes=60)
    app = create_app(
        store=store,
        mattermost=mattermost_client,
        immich_for=immich_for,
        sender=sender,
        command_tokens={"team-a-token", "team-b-token"},
        callback_url="http://souvenirs:8000",
        clock=clock,
    )
    return TestClient(app)


def command(client, text, user_id="u1", token="team-a-token"):
    return client.post(
        "/command",
        data={
            "token": token,
            "team_id": "team-a",
            "channel_id": "town-square",
            "user_id": user_id,
            "user_name": "alex",
            "command": "/souvenirs",
            "text": text,
            "trigger_id": "trigger-1",
            "response_url": "https://mm.example/hooks/commands/x",
        },
    )


def open_activation_dialog(client, mattermost, user_id="u1"):
    command(client, "activer", user_id=user_id)
    return mattermost.bodies("/api/v4/actions/dialogs/open")[-1]


def submit_dialog(client, dialog, immich_key, user_id="u1", send_time="09:00"):
    return client.post(
        "/dialog",
        json={
            "type": "dialog_submission",
            "callback_id": dialog["dialog"]["callback_id"],
            "state": dialog["dialog"]["state"],
            "user_id": user_id,
            "channel_id": "town-square",
            "team_id": "team-a",
            "submission": {"immich_key": immich_key, "send_time": send_time},
            "cancelled": False,
        },
    )


def test_command_with_unknown_token_is_rejected(client):
    response = command(client, "statut", token="forged")

    assert response.status_code == 401


def test_command_without_argument_shows_ephemeral_help(client):
    response = command(client, "")

    assert response.json()["response_type"] == "ephemeral"
    assert "/souvenirs activer" in response.json()["text"]


def test_activer_opens_dialog_with_masked_key_and_send_time_fields(client, mattermost):
    dialog = open_activation_dialog(client, mattermost)

    assert dialog["trigger_id"] == "trigger-1"
    assert dialog["url"] == "http://souvenirs:8000/dialog"
    key_field, time_field = dialog["dialog"]["elements"]
    assert key_field["name"] == "immich_key"
    assert key_field["subtype"] == "password"
    assert time_field["name"] == "send_time"
    assert time_field["default"] == "09:00"
    assert dialog["dialog"]["state"]


def test_activer_prefills_the_current_send_time_of_a_registered_user(client, store, mattermost):
    store.register("u1", "dm1", "key", time(7, 30))

    dialog = open_activation_dialog(client, mattermost)

    assert dialog["dialog"]["elements"][1]["default"] == "07:30"


def test_valid_key_registers_user_with_chosen_time_and_confirms_in_direct_message(client, store, mattermost):
    dialog = open_activation_dialog(client, mattermost)

    response = submit_dialog(client, dialog, "good-key", send_time="7:30")

    assert response.status_code == 200
    assert "errors" not in response.json()
    user = store.get("u1")
    assert user.immich_key == "good-key"
    assert user.send_time == time(7, 30)
    assert user.dm_channel_id == "dm-channel"
    [confirmation] = mattermost.bodies("/api/v4/posts")
    assert confirmation["channel_id"] == "dm-channel"
    assert "activés" in confirmation["message"]
    assert "07:30" in confirmation["message"]


def test_invalid_send_time_keeps_dialog_open_and_stores_nothing(client, store, mattermost):
    dialog = open_activation_dialog(client, mattermost)

    response = submit_dialog(client, dialog, "good-key", send_time="9h")

    assert "send_time" in response.json()["errors"]
    assert store.get("u1") is None


def test_rejected_key_keeps_dialog_open_and_stores_nothing(client, store, immich, mattermost):
    immich.rejected_keys.add("bad-key")
    dialog = open_activation_dialog(client, mattermost)

    response = submit_dialog(client, dialog, "bad-key")

    assert "immich_key" in response.json()["errors"]
    assert store.get("u1") is None


def test_dialog_state_is_single_use(client, mattermost):
    dialog = open_activation_dialog(client, mattermost)
    submit_dialog(client, dialog, "good-key")

    response = submit_dialog(client, dialog, "good-key")

    assert response.status_code == 403


def test_dialog_state_is_bound_to_the_user(client, store, mattermost):
    dialog = open_activation_dialog(client, mattermost, user_id="u1")

    response = submit_dialog(client, dialog, "attacker-key", user_id="u2")

    assert response.status_code == 403
    assert store.get("u2") is None


def test_dialog_state_expires_after_ten_minutes(client, clock, mattermost):
    dialog = open_activation_dialog(client, mattermost)
    clock.now = NOW + timedelta(minutes=11)

    response = submit_dialog(client, dialog, "good-key")

    assert response.status_code == 403


def test_rejected_key_submission_can_be_retried_with_same_dialog(client, store, immich, mattermost):
    immich.rejected_keys.add("bad-key")
    dialog = open_activation_dialog(client, mattermost)
    submit_dialog(client, dialog, "bad-key")

    submit_dialog(client, dialog, "good-key")

    assert store.get("u1").immich_key == "good-key"


def test_statut_for_unregistered_user(client):
    response = command(client, "statut")

    assert "pas inscrit" in response.json()["text"]


def test_statut_shows_send_time_and_last_error(client, store):
    store.register("u1", "dm1", "key", time(9, 0))
    store.record_error("u1", "Immich unavailable")

    text = command(client, "statut").json()["text"]

    assert "09:00" in text
    assert "Immich unavailable" in text
    assert "key" not in text.replace("clé", "")


def test_heure_sets_send_time(client, store):
    store.register("u1", "dm1", "key", time(9, 0))

    response = command(client, "heure 7:30")

    assert store.get("u1").send_time == time(7, 30)
    assert "07:30" in response.json()["text"]


@pytest.mark.parametrize("value", ["25:00", "9h", "demain"])
def test_heure_rejects_invalid_time(client, store, value):
    store.register("u1", "dm1", "key", time(9, 0))

    response = command(client, f"heure {value}")

    assert store.get("u1").send_time == time(9, 0)
    assert "HH:MM" in response.json()["text"]


def test_heure_without_value_shows_current_time(client, store):
    store.register("u1", "dm1", "key", time(9, 0))

    assert "09:00" in command(client, "heure").json()["text"]


def test_test_sends_today_memories_even_if_already_sent(client, store, immich, mattermost):
    store.register("u1", "dm1", "key", time(9, 0))
    store.mark_sent("u1", date(2026, 10, 11))
    immich.memories_by_key["key"] = [memory_payload("m2021", 2021, ["a1"])]

    response = command(client, "test")

    [post] = mattermost.bodies("/api/v4/posts")
    assert post["channel_id"] == "dm1"
    assert "immich://memory?id=m2021" in post["message"]
    assert response.json()["response_type"] == "ephemeral"


def test_test_without_memories_today_sends_the_latest_one(client, store, immich, mattermost):
    store.register("u1", "dm1", "key", time(9, 0))
    immich.latest_by_key["key"] = [memory_payload("m2019", 2019, ["a1"], show_at="2026-10-08T12:00:00.000Z")]

    response = command(client, "test")

    [post] = mattermost.bodies("/api/v4/posts")
    assert "immich://memory?id=m2019" in post["message"]
    assert "dernier" in response.json()["text"]
    assert store.get("u1").last_sent_on is None


def test_test_without_any_memory_says_so(client, store, mattermost):
    store.register("u1", "dm1", "key", time(9, 0))

    response = command(client, "test")

    assert mattermost.bodies("/api/v4/posts") == []
    assert "Aucun souvenir dans Immich" in response.json()["text"]


@pytest.mark.parametrize("text", ["désactiver", "desactiver"])
def test_desactiver_deletes_registration(client, store, text):
    store.register("u1", "dm1", "key", time(9, 0))

    response = command(client, text)

    assert store.get("u1") is None
    assert response.json()["response_type"] == "ephemeral"
