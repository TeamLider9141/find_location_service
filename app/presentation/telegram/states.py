from aiogram.fsm.state import State, StatesGroup


class AddPlace(StatesGroup):
    name = State()
    category = State()
    location = State()
    duplicate = State()
    note = State()


class FindPlace(StatesGroup):
    query = State()


class NearbyPlace(StatesGroup):
    location = State()
