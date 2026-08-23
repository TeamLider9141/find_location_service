from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class BotUser:
    """A driver the bot has seen, as the admin panel needs to describe them."""

    id: int
    full_name: str
    username: str | None
    first_seen_at: datetime
    last_seen_at: datetime
