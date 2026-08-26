from datetime import datetime, timezone
from typing import Callable

from app.domain.value_objects.add_access import AddAccessStatus, has_gone_stale


class InMemoryAddAccessRepository:
    def __init__(self, clock: Callable[[], datetime] | None = None) -> None:
        self._clock = clock if clock is not None else _now
        self._statuses: dict[int, tuple[AddAccessStatus, datetime]] = {}

    def status(self, user_id: int) -> AddAccessStatus | None:
        recorded = self._statuses.get(user_id)
        if recorded is None:
            return None

        # A request the admins let sit for a day reads as no request at all,
        # rather than leaving the driver waiting on an answer nobody will give.
        status, changed_at = recorded
        return None if has_gone_stale(status, changed_at, self._clock()) else status

    def set_status(self, user_id: int, status: AddAccessStatus) -> None:
        self._statuses[user_id] = (status, self._clock())

    def clear(self, user_id: int) -> None:
        self._statuses.pop(user_id, None)

    def statuses(self) -> dict[int, AddAccessStatus]:
        now = self._clock()
        return {
            user_id: status
            for user_id, (status, changed_at) in self._statuses.items()
            if not has_gone_stale(status, changed_at, now)
        }


def _now() -> datetime:
    """UTC, to the second — the clock every stored timestamp is read against."""
    return datetime.now(timezone.utc).replace(microsecond=0, tzinfo=None)
