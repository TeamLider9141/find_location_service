from typing import Protocol

from app.domain.entities.bot_user import BotUser


class UserRepository(Protocol):
    """Who uses the bot, and what they look for.

    Nothing in the driver-facing flows reads this; it exists so the admin can
    see who contributes and what people search for.
    """

    def record_seen(self, user_id: int, full_name: str, username: str | None) -> bool:
        """Create or refresh a user; True when this is their first ever visit.

        The first visit timestamp is never rewritten.
        """

    def get(self, user_id: int) -> BotUser | None:
        """Return one user, or None when the bot has never seen them."""

    def count(self) -> int:
        """Return how many distinct users the bot has seen."""

    def list_page(
        self, offset: int, limit: int, exclude_ids: tuple[int, ...] = ()
    ) -> tuple[int, list[BotUser]]:
        """Return the total user count and one page, most recently active first.

        ``exclude_ids`` hides those users from the page and the total both —
        the ordinary admin rung is not shown the super admins.
        """

    def all_ids(self) -> list[int]:
        """Return every user id — the broadcast recipient list."""

    def record_search(self, user_id: int, query: str) -> None:
        """Log a search. Blank queries are ignored."""

    def search_count(self, user_id: int) -> int:
        """Return how many searches this user has run."""

    def total_searches(self) -> int:
        """Return how many searches every user has run together."""

    def top_searches(self, limit: int = 10) -> list[tuple[str, int]]:
        """Return the most repeated queries, most frequent first."""
