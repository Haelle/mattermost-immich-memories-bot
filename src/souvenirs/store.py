import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path

from cryptography.fernet import Fernet

SCHEMA = """
create table if not exists users (
    mm_user_id text primary key,
    dm_channel_id text not null,
    immich_key_enc blob not null,
    send_time text not null,
    active integer not null default 1,
    created_at text not null,
    last_sent_on text,
    last_error text
)
"""


@dataclass(frozen=True)
class User:
    mm_user_id: str
    dm_channel_id: str
    immich_key: str
    send_time: time
    active: bool
    created_at: datetime
    last_sent_on: date | None
    last_error: str | None


class Store:
    def __init__(self, db_path: Path | str, master_key: bytes | str):
        self._db_path = db_path
        self._fernet = Fernet(master_key)
        with self._connect() as connection:
            connection.execute(SCHEMA)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        with closing(sqlite3.connect(self._db_path)) as connection, connection:
            connection.row_factory = sqlite3.Row
            yield connection

    def _execute(self, sql: str, parameters: tuple = ()) -> None:
        with self._connect() as connection:
            connection.execute(sql, parameters)

    def register(self, mm_user_id: str, dm_channel_id: str, immich_key: str, send_time: time) -> User:
        self._execute(
            """
            insert into users (mm_user_id, dm_channel_id, immich_key_enc, send_time, created_at)
            values (?, ?, ?, ?, ?)
            on conflict (mm_user_id) do update set
                dm_channel_id = excluded.dm_channel_id,
                immich_key_enc = excluded.immich_key_enc,
                send_time = excluded.send_time,
                active = 1,
                last_error = null
            """,
            (
                mm_user_id,
                dm_channel_id,
                self._fernet.encrypt(immich_key.encode()),
                send_time.isoformat("minutes"),
                datetime.now().isoformat(timespec="seconds"),
            ),
        )
        return self._require(mm_user_id)

    def _require(self, mm_user_id: str) -> User:
        user = self.get(mm_user_id)
        if user is None:
            raise LookupError(mm_user_id)
        return user

    def get(self, mm_user_id: str) -> User | None:
        with self._connect() as connection:
            row = connection.execute("select * from users where mm_user_id = ?", (mm_user_id,)).fetchone()
        return self._to_user(row) if row else None

    def active_users(self) -> list[User]:
        with self._connect() as connection:
            rows = connection.execute("select * from users where active = 1 order by mm_user_id").fetchall()
        return [self._to_user(row) for row in rows]

    def delete(self, mm_user_id: str) -> None:
        self._execute("delete from users where mm_user_id = ?", (mm_user_id,))

    def set_send_time(self, mm_user_id: str, send_time: time) -> None:
        self._execute(
            "update users set send_time = ? where mm_user_id = ?",
            (send_time.isoformat("minutes"), mm_user_id),
        )

    def mark_sent(self, mm_user_id: str, day: date) -> None:
        self._execute(
            "update users set last_sent_on = ?, last_error = null where mm_user_id = ?",
            (day.isoformat(), mm_user_id),
        )

    def record_error(self, mm_user_id: str, error: str) -> None:
        self._execute("update users set last_error = ? where mm_user_id = ?", (error, mm_user_id))

    def deactivate(self, mm_user_id: str, error: str) -> None:
        self._execute("update users set active = 0, last_error = ? where mm_user_id = ?", (error, mm_user_id))

    def _to_user(self, row: sqlite3.Row) -> User:
        return User(
            mm_user_id=row["mm_user_id"],
            dm_channel_id=row["dm_channel_id"],
            immich_key=self._fernet.decrypt(row["immich_key_enc"]).decode(),
            send_time=time.fromisoformat(row["send_time"]),
            active=bool(row["active"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            last_sent_on=date.fromisoformat(row["last_sent_on"]) if row["last_sent_on"] else None,
            last_error=row["last_error"],
        )
