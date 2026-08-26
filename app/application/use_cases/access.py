"""Who may add places.

Reading the shared database is open to everyone. Writing is not: one bored
user pasting garbage would poison the answers every driver gets, so the right
to add is handed out by an admin, once per user.
"""

from app.domain.interfaces.add_access import AddAccessRepository
from app.domain.value_objects.add_access import AddAccessStatus


class RequestAddAccessUseCase:
    """A driver asks for the right to add places."""

    def __init__(self, access: AddAccessRepository) -> None:
        self._access = access

    def execute(self, user_id: int) -> AddAccessStatus | None:
        """Return the status the driver had, marking them pending if they had none.

        The caller reads the return as: APPROVED — let them through; PENDING —
        already waiting, say so; anything else — a fresh request the admins
        should hear about.

        A rejected driver may ask again. Admins change their minds, and to the
        driver a permanent silence is indistinguishable from a broken bot.
        """
        previous = self._access.status(user_id)
        if previous not in (AddAccessStatus.APPROVED, AddAccessStatus.PENDING):
            self._access.set_status(user_id, AddAccessStatus.PENDING)
        return previous


class HasAddAccessUseCase:
    """Whether this driver already holds the right to add.

    A read, not a request: asking must not file anything — the main menu asks
    this for every driver just to decide which buttons to draw.
    """

    def __init__(self, access: AddAccessRepository) -> None:
        self._access = access

    def execute(self, user_id: int) -> bool:
        return self._access.status(user_id) == AddAccessStatus.APPROVED


class DecideAddAccessUseCase:
    """The admin answers a driver's request."""

    def __init__(self, access: AddAccessRepository) -> None:
        self._access = access

    def execute(self, user_id: int, allow: bool) -> None:
        status = AddAccessStatus.APPROVED if allow else AddAccessStatus.REJECTED
        self._access.set_status(user_id, status)


class RevokeAddAccessUseCase:
    """The admin takes a driver's permission back.

    Cleared rather than rejected: the driver returns to the state of never
    having asked, so their next attempt files a fresh request instead of
    running into a standing refusal.
    """

    def __init__(self, access: AddAccessRepository) -> None:
        self._access = access

    def execute(self, user_id: int) -> None:
        self._access.clear(user_id)
