from enum import Enum


class AttachmentKind(str, Enum):
    """What kind of file rides with a document note.

    Telegram sends the two differently — a photo has sizes, a file has a name —
    and they are sent back differently too, so the kind is stored rather than
    guessed at send time.
    """

    PHOTO = "photo"
    FILE = "file"
