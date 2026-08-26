from typing import Protocol

from app.domain.value_objects.add_access import AddAccessStatus


class AddAccessRepository(Protocol):
    """Who may write to the shared database, as the admins decided."""

    def status(self, user_id: int) -> AddAccessStatus | None:
        """Return where this driver stands, or None when they never asked."""

    def set_status(self, user_id: int, status: AddAccessStatus) -> None:
        """Record the latest word — the driver's request or the admin's answer."""

    def clear(self, user_id: int) -> None:
        """Forget this driver entirely, as if they never asked."""

    def allowed_ids(self) -> set[int]:
        """Return every driver who may add — approved only, pending is not yet.

        Asked for whole so the admin's user list can mark and rank hundreds of
        rows without a status query each.
        """
