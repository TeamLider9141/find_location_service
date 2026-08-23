import sqlite3

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.application.use_cases.places import AddPlaceUseCase
from app.domain.value_objects.category import PlaceCategory
from app.domain.value_objects.coordinates import Coordinates
from app.presentation.telegram.errors import (
    EXPIRED_MESSAGE,
    answerable_message,
    report_service_error,
    user_id_of,
)
from app.presentation.telegram.formatters import (
    format_duplicate_warning,
    format_place_card,
)
from app.presentation.telegram.keyboards.menu import (
    ADD_PLACE_BUTTON,
    build_main_menu_keyboard,
)
from app.presentation.telegram.keyboards.places import (
    build_category_choice_keyboard,
    build_duplicate_confirmation_keyboard,
)
from app.presentation.telegram.location_input import parse_coordinates_from_text
from app.presentation.telegram.states import AddPlace

router = Router(name="add_place")

ASK_NAME_MESSAGE = "Joy nomini yozing. Masalan: Газпром yoki Кафе У Дороги."
ASK_CATEGORY_MESSAGE = "Kategoriyani tanlang."
BLANK_NAME_MESSAGE = "Nom bo'sh bo'lmasligi kerak. Joy nomini yozing."
ASK_LOCATION_MESSAGE = (
    "Endi lokatsiyani yuboring.\n\n"
    "📎 → Lokatsiya, yoki xarita linkini, yoki koordinatani yozing: 55.75, 37.61"
)
ASK_LOCATION_AGAIN_MESSAGE = (
    "Buni lokatsiya sifatida o'qiy olmadim. "
    "Telegram lokatsiyasini yuboring yoki koordinatani yozing: 55.75, 37.61"
)
ASK_NOTE_MESSAGE = (
    "Izoh qo'shasizmi? Masalan: M5, 120-km, kechasi ochiq.\n"
    "Kerak bo'lmasa /skip yuboring."
)
INVALID_CATEGORY_MESSAGE = "Bunday kategoriya yo'q. Ro'yxatdan tanlang."
CANCELLED_MESSAGE = "Bekor qilindi. Boshlang'ich menyuga qaytdingiz."
SAVE_FAILED_MESSAGE = "Saqlab bo'lmadi. Qaytadan urinib ko'ring."
DATABASE_ERROR_MESSAGE = "Baza bilan muammo. Birozdan so'ng urinib ko'ring."


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


@router.callback_query(AddPlace.category, F.data.startswith("add_place:category:"))
async def handle_category(callback_query: CallbackQuery, state: FSMContext) -> None:
    category = _parse_category(callback_query.data)
    if category is None:
        await callback_query.answer(INVALID_CATEGORY_MESSAGE)
        return

    message = answerable_message(callback_query)
    if message is None:
        await callback_query.answer(EXPIRED_MESSAGE)
        return

    await state.update_data(category=category.value)
    await state.set_state(AddPlace.location)
    await message.answer(ASK_LOCATION_MESSAGE)
    await callback_query.answer()


@router.message(AddPlace.location)
async def handle_location(
    message: Message,
    state: FSMContext,
    add_place: AddPlaceUseCase,
) -> None:
    coordinates = _coordinates_from_message(message)
    if coordinates is None:
        await message.answer(ASK_LOCATION_AGAIN_MESSAGE)
        return

    await state.update_data(
        latitude=coordinates.latitude,
        longitude=coordinates.longitude,
    )

    data = await state.get_data()
    # Ask before the note step, not at save time: a driver who is about to
    # re-add a place someone else already shared should find out before
    # spending effort on it.
    duplicates = add_place.find_duplicates(
        name=str(data["name"]),
        coordinates=coordinates,
    )
    if duplicates:
        await state.set_state(AddPlace.duplicate)
        await message.answer(
            format_duplicate_warning(duplicates),
            reply_markup=build_duplicate_confirmation_keyboard(),
        )
        return

    await state.set_state(AddPlace.note)
    await message.answer(ASK_NOTE_MESSAGE)


def _parse_category(data: str | None) -> PlaceCategory | None:
    prefix = "add_place:category:"
    if data is None or not data.startswith(prefix):
        return None
    try:
        return PlaceCategory(data.removeprefix(prefix))
    except ValueError:
        return None


def _coordinates_from_message(message: Message) -> Coordinates | None:
    location = getattr(message, "location", None)
    if location is not None:
        return Coordinates(latitude=location.latitude, longitude=location.longitude)

    venue = getattr(message, "venue", None)
    if venue is not None and getattr(venue, "location", None) is not None:
        return Coordinates(
            latitude=venue.location.latitude,
            longitude=venue.location.longitude,
        )

    text = getattr(message, "text", None)
    if text:
        return parse_coordinates_from_text(text)

    return None


@router.callback_query(AddPlace.duplicate, F.data.startswith("add_place:duplicate:"))
async def handle_duplicate_answer(
    callback_query: CallbackQuery,
    state: FSMContext,
) -> None:
    message = answerable_message(callback_query)
    if message is None:
        await state.clear()
        await callback_query.answer(EXPIRED_MESSAGE)
        return

    # Only an explicit yes continues. Anything else — including a garbled
    # callback — falls through to the cancel branch rather than being read as
    # consent to add a second copy of a place someone already shared.
    if callback_query.data == "add_place:duplicate:yes":
        await state.set_state(AddPlace.note)
        await message.answer(ASK_NOTE_MESSAGE)
    else:
        await state.clear()
        await message.answer(CANCELLED_MESSAGE, reply_markup=build_main_menu_keyboard())

    await callback_query.answer()


@router.message(AddPlace.note, Command("skip"))
async def handle_skip_note(
    message: Message,
    state: FSMContext,
    add_place: AddPlaceUseCase,
) -> None:
    await _save(message, state, add_place, note="")


@router.message(AddPlace.note, F.text)
async def handle_note(
    message: Message,
    state: FSMContext,
    add_place: AddPlaceUseCase,
) -> None:
    await _save(message, state, add_place, note=message.text or "")


@router.message(AddPlace(), Command("cancel"))
async def handle_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(CANCELLED_MESSAGE, reply_markup=build_main_menu_keyboard())


async def _save(
    message: Message,
    state: FSMContext,
    add_place: AddPlaceUseCase,
    note: str,
) -> None:
    data = await state.get_data()
    user_id = user_id_of(message)
    if user_id is None:
        await state.clear()
        return

    try:
        place = add_place.execute(
            user_id=user_id,
            name=str(data["name"]),
            category=PlaceCategory(str(data["category"])),
            coordinates=Coordinates(
                latitude=float(data["latitude"]),
                longitude=float(data["longitude"]),
            ),
            note=note,
        )
    # A flow that lost a step leaves the state short of a key, and a place
    # written without it would land at the wrong coordinates rather than fail.
    except (KeyError, ValueError) as error:
        report_service_error(error, "add place")
        await state.clear()
        await message.answer(SAVE_FAILED_MESSAGE, reply_markup=build_main_menu_keyboard())
        return
    except sqlite3.Error as error:
        report_service_error(error, "add place")
        await state.clear()
        await message.answer(DATABASE_ERROR_MESSAGE, reply_markup=build_main_menu_keyboard())
        return

    await state.clear()
    await message.answer(
        f"✅ Saqlandi.\n\n{format_place_card(place)}",
        reply_markup=build_main_menu_keyboard(),
    )
