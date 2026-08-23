import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path
from sqlite3 import Row

from app.domain.entities.bot_user import BotUser


class SQLiteUserRepository:
    def __init__(self, database_path: Path | str) -> None:
        self._database_path = Path(database_path)
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def record_seen(self, user_id: int, full_name: str, username: str | None) -> None:
        # ON CONFLICT keeps first_seen_at as it was inserted: the row already
        # holds the answer to "when did this driver join", and an UPSERT that
        # rewrote it would make every returning user look new.
        with closing(self._connect()) as connection:
            connection.execute(
                """
                INSERT INTO users (id, full_name, username)
                VALUES (?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    full_name = excluded.full_name,
                    username = excluded.username,
                    last_seen_at = CURRENT_TIMESTAMP
                """,
                (user_id, full_name, username),
            )
            connection.commit()

    def get(self, user_id: int) -> BotUser | None:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT id, full_name, username, first_seen_at, last_seen_at "
                "FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()

        return _map_user(row) if row is not None else None

    def count(self) -> int:
        with closing(self._connect()) as connection:
            row = connection.execute("SELECT COUNT(*) AS total FROM users").fetchone()

        return int(row["total"])

    def list_page(self, offset: int, limit: int) -> tuple[int, list[BotUser]]:
        with closing(self._connect()) as connection:
            total = int(
                connection.execute("SELECT COUNT(*) AS total FROM users").fetchone()["total"]
            )
            rows = connection.execute(
                """
                SELECT id, full_name, username, first_seen_at, last_seen_at
                FROM users
                ORDER BY last_seen_at DESC, id DESC
                LIMIT ? OFFSET ?
                """,
                (max(limit, 0), max(offset, 0)),
            ).fetchall()

        return total, [_map_user(row) for row in rows]

    def all_ids(self) -> list[int]:
        with closing(self._connect()) as connection:
            rows = connection.execute("SELECT id FROM users ORDER BY id").fetchall()

        return [int(row["id"]) for row in rows]

    def record_search(self, user_id: int, query: str) -> None:
        cleaned = query.strip()
        if not cleaned:
            return

        with closing(self._connect()) as connection:
            connection.execute(
                "INSERT INTO search_log (user_id, query) VALUES (?, ?)",
                (user_id, cleaned.lower()),
            )
            connection.commit()

    def search_count(self, user_id: int) -> int:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS total FROM search_log WHERE user_id = ?",
                (user_id,),
            ).fetchone()

        return int(row["total"])

    def top_searches(self, limit: int = 10) -> list[tuple[str, int]]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT query, COUNT(*) AS times
                FROM search_log
                GROUP BY query
                ORDER BY times DESC, query ASC
                LIMIT ?
                """,
                (max(limit, 0),),
            ).fetchall()

        return [(str(row["query"]), int(row["times"])) for row in rows]

    def _initialize(self) -> None:
        with closing(self._connect()) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY,
                    full_name TEXT NOT NULL,
                    username TEXT,
                    first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS search_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    query TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_search_log_user ON search_log(user_id)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_search_log_query ON search_log(query)"
            )
            connection.commit()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_path)
        connection.row_factory = Row
        return connection


def _map_user(row: Row) -> BotUser:
    username = row["username"]
    return BotUser(
        id=int(row["id"]),
        full_name=str(row["full_name"]),
        username=str(username) if username else None,
        first_seen_at=_parse_timestamp(str(row["first_seen_at"])),
        last_seen_at=_parse_timestamp(str(row["last_seen_at"])),
    )


def _parse_timestamp(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return datetime.min
