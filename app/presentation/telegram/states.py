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


class FindPlace(StatesGroup):
    query = State()


class NearbyPlace(StatesGroup):
    location = State()


class AdminBroadcast(StatesGroup):
    message = State()
