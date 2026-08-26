from dataclasses import dataclass
from datetime import datetime

from app.domain.value_objects.attachment import AttachmentKind


@dataclass(frozen=True)
class PlaceDocument:
    """Papers a place asks for, pinned to that place by a contributor.

    The note says what documents a driver needs there; the attachment — a
    photo or a file — shows them. ``file_id`` is Telegram's own handle: the
    bot never stores the bytes, it asks Telegram to resend them.

    ``added_by_user_id`` is not a reading fence — anyone may look — it only
    decides who may edit.
    """

    id: int
    place_id: int
    added_by_user_id: int
    note: str
    file_id: str | None
    file_kind: AttachmentKind | None
    created_at: datetime

    @property
    def has_attachment(self) -> bool:
        return self.file_id is not None and self.file_kind is not None
