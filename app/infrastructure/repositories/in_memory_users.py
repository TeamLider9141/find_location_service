from collections import Counter
from dataclasses import replace
from datetime import datetime, timezone

from app.domain.entities.bot_user import BotUser


class InMemoryUserRepository:
    """Test double for UserRepository. Same contract, no database."""

    def __init__(self) -> None:
        self._users: dict[int, BotUser] = {}
        self._searches: list[tuple[int, str]] = []

    def record_seen(self, user_id: int, full_name: str, username: str | None) -> bool:
        now = _now()
        existing = self._users.get(user_id)
        if existing is None:
            self._users[user_id] = BotUser(
                id=user_id,
                full_name=full_name,
                username=username,
                first_seen_at=now,
                last_seen_at=now,
            )
            return True

        self._users[user_id] = replace(
            existing,
            full_name=full_name,
            username=username,
            last_seen_at=now,
        )
        return False

    def get(self, user_id: int) -> BotUser | None:
        return self._users.get(user_id)

    def count(self) -> int:
        return len(self._users)

    def list_page(
        self, offset: int, limit: int, exclude_ids: tuple[int, ...] = ()
    ) -> tuple[int, list[BotUser]]:
        ordered = sorted(
            (user for user in self._users.values() if user.id not in exclude_ids),
            key=lambda user: (user.last_seen_at, user.id),
            reverse=True,
        )
        start = max(offset, 0)
        return len(ordered), ordered[start : start + max(limit, 0)]

    def all_ids(self) -> list[int]:
        return sorted(self._users)

    def record_search(self, user_id: int, query: str) -> None:
        cleaned = query.strip()
        if not cleaned:
            return

        self._searches.append((user_id, cleaned.lower()))

    def search_count(self, user_id: int) -> int:
        return sum(1 for logged_user_id, _ in self._searches if logged_user_id == user_id)

    def total_searches(self) -> int:
        return len(self._searches)

    def top_searches(self, limit: int = 10) -> list[tuple[str, int]]:
        counts = Counter(query for _, query in self._searches)
        # Ties break on the query text, the same ORDER BY the SQL uses, so a
        # test that passes here cannot fail against the real database.
        ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        return ranked[: max(limit, 0)]


def _now() -> datetime:
    # CURRENT_TIMESTAMP is naive UTC with one-second resolution; matching it here
    # keeps the two implementations comparable.
    return datetime.now(timezone.utc).replace(microsecond=0, tzinfo=None)
