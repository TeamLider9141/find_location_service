from datetime import datetime, timedelta
from enum import Enum


class AddAccessStatus(str, Enum):
    """Where a driver stands on the right to add places.

    Reading the shared database is open to everyone; writing to it is not, so
    the right to add is handed out by an admin. No status at all means the
    driver has never asked.
    """

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


# How long an unanswered request keeps a driver waiting. Past it they stand
# where they did before asking: silence from the admins must not lock someone
# out forever, and their next attempt files a fresh request the admins hear.
PENDING_WINDOW = timedelta(hours=24)


def has_gone_stale(status: AddAccessStatus, changed_at: datetime, now: datetime) -> bool:
    """True when this standing no longer counts. Only the waiting expires.

    A granted permission and a refusal both stand however old they are; it is
    the request nobody answered that goes quiet.
    """
    return status == AddAccessStatus.PENDING and now - changed_at >= PENDING_WINDOW
