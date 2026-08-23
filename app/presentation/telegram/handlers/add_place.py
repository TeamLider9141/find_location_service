from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.presentation.telegram.keyboards.menu import ADD_PLACE_BUTTON
from app.presentation.telegram.keyboards.places import build_category_choice_keyboard
from app.presentation.telegram.states import AddPlace

router = Router(name="add_place")

ASK_NAME_MESSAGE = "Joy nomini yozing. Masalan: Газпром yoki Кафе У Дороги."
ASK_CATEGORY_MESSAGE = "Kategoriyani tanlang."
BLANK_NAME_MESSAGE = "Nom bo'sh bo'lmasligi kerak. Joy nomini yozing."


@router.message(F.text == ADD_PLACE_BUTTON)
async def handle_add_place_start(message: Message, state: FSMContext) -> None:
    # Clear before setting the state: an abandoned flow leaves its name and
    # coordinates in storage, and carrying them into a fresh attempt would file
    # the new place at the old location.
    await state.set_data({})
    await state.set_state(AddPlace.name)
    await message.answer(ASK_NAME_MESSAGE)


@router.message(AddPlace.name, F.text)
async def handle_name(message: Message, state: FSMContext) -> None:
    name = (message.text or "").strip()
    if not name:
        await message.answer(BLANK_NAME_MESSAGE)
        return

    await state.update_data(name=name)
    await state.set_state(AddPlace.category)
    await message.answer(
        ASK_CATEGORY_MESSAGE,
        reply_markup=build_category_choice_keyboard("add_place:category"),
    )
