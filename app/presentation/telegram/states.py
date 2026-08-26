from aiogram.fsm.state import State, StatesGroup


class AddPlace(StatesGroup):
    # Declared in the order the driver walks them: location first — it is the
    # one thing they have to be standing at.
    location = State()
    category = State()
    name = State()
    note = State()
    preview = State()
    duplicate = State()


class EditPlace(StatesGroup):
    """Rewriting one field of an existing place; the id rides in the data."""

    name = State()
    note = State()
    location = State()


class AddDocument(StatesGroup):
    # The place first — the document means nothing unpinned. Then one step
    # that takes both the optional file and the note, then a look before
    # anything is written.
    place = State()
    content = State()
    preview = State()


class EditDocument(StatesGroup):
    """Rewriting one part of an existing document; the id rides in the data."""

    note = State()
    file = State()


class FindPlace(StatesGroup):
    query = State()


class NearbyPlace(StatesGroup):
    location = State()


class AdminBroadcast(StatesGroup):
    message = State()
