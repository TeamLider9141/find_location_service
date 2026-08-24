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
