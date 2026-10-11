import sqlite3
from datetime import date, time

import pytest
from cryptography.fernet import Fernet, InvalidToken

from souvenirs.store import Store

IMMICH_KEY = "immich-secret-key-123"


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "souvenirs.db"


@pytest.fixture
def store(db_path):
    return Store(db_path, Fernet.generate_key())


def test_registered_user_gets_send_time_and_decrypted_key(store):
    store.register("u1", "dm1", IMMICH_KEY, time(7, 30))

    user = store.get("u1")

    assert user.dm_channel_id == "dm1"
    assert user.immich_key == IMMICH_KEY
    assert user.send_time == time(7, 30)
    assert user.active is True
    assert user.last_sent_on is None


def test_immich_key_is_not_stored_in_clear(store, db_path):
    store.register("u1", "dm1", IMMICH_KEY, time(9, 0))

    raw = db_path.read_bytes()

    assert IMMICH_KEY.encode() not in raw


def test_key_cannot_be_read_with_another_master_key(store, db_path):
    store.register("u1", "dm1", IMMICH_KEY, time(9, 0))
    other = Store(db_path, Fernet.generate_key())

    with pytest.raises(InvalidToken):
        other.get("u1")


def test_reregistering_replaces_key_and_send_time_and_reactivates(store):
    store.register("u1", "dm1", "old-key", time(9, 0))
    store.deactivate("u1", "key rejected")

    store.register("u1", "dm1", "new-key", time(7, 30))

    user = store.get("u1")
    assert user.immich_key == "new-key"
    assert user.send_time == time(7, 30)
    assert user.active is True
    assert user.last_error is None


def test_unknown_user_is_none(store):
    assert store.get("nobody") is None


def test_delete_removes_the_row(store, db_path):
    store.register("u1", "dm1", IMMICH_KEY, time(9, 0))

    store.delete("u1")

    assert store.get("u1") is None
    assert sqlite3.connect(db_path).execute("select count(*) from users").fetchone() == (0,)


def test_active_users_excludes_deactivated(store):
    store.register("u1", "dm1", "k1", time(9, 0))
    store.register("u2", "dm2", "k2", time(9, 0))
    store.deactivate("u2", "key rejected")

    assert [user.mm_user_id for user in store.active_users()] == ["u1"]


def test_mark_sent_records_day_and_clears_error(store):
    store.register("u1", "dm1", IMMICH_KEY, time(9, 0))
    store.record_error("u1", "immich unreachable")

    store.mark_sent("u1", date(2026, 10, 11))

    user = store.get("u1")
    assert user.last_sent_on == date(2026, 10, 11)
    assert user.last_error is None


def test_deactivate_keeps_error_for_status(store):
    store.register("u1", "dm1", IMMICH_KEY, time(9, 0))

    store.deactivate("u1", "key rejected")

    user = store.get("u1")
    assert user.active is False
    assert user.last_error == "key rejected"
