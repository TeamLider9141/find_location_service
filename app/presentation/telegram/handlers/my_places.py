import sqlite3

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.application.use_cases.places import (
    DeletePlaceUseCase,
    ListMyPlacesUseCase,
    UpdatePlaceUseCase,
)
from app.domain.value_objects.category import PlaceCategory
from app.presentation.telegram.errors import (
    EXPIRED_MESSAGE,
    answerable_message,
    report_service_error,
    user_id_of,
)
from app.domain.interfaces.links import LinkResolver
from app.presentation.telegram.formatters import format_place_card
from app.presentation.telegram.location_resolution import coordinates_from_message
from app.presentation.telegram.prompts import with_cancel_hint
from app.presentation.telegram.states import EditPlace
from app.presentation.telegram.notifications import announce_owner_deletion
from app.presentation.telegram.keyboards.places import (
    BORDER_GROUP_VALUE,
    CHOOSE_BORDER_MESSAGE,
    build_border_choice_keyboard,
    build_my_place_actions_keyboard,
    build_place_delete_confirmation_keyboard,
    build_update_category_keyboard,
)

router = Router(name="my_places")

EMPTY_MESSAGE = (
    "Siz hali joy qo'shmagansiz.\n\n"
    "➕ Joy qo'shish orqali birinchi joyingizni qo'shing."
)
NOT_YOURS_MESSAGE = "Bu joyni faqat uni qo'shgan foydalanuvchi o'zgartira oladi."
INVALID_SELECTION_MESSAGE = "Tanlov eskirgan. 📒 Mening joylarim dan qaytadan oching."
DELETED_MESSAGE = "🗑 O'chirildi."
CANCELLED_MESSAGE = "O'chirish bekor qilindi."
DATABASE_ERROR_MESSAGE = "Baza bilan muammo. Birozdan so'ng urinib ko'ring."
ASK_NEW_NAME_MESSAGE = with_cancel_hint("Yangi nomini yozing.")
BLANK_NAME_MESSAGE = with_cancel_hint("Nom bo'sh bo'lmasligi kerak. Yangi nomini yozing.")
ASK_NEW_NOTE_MESSAGE = with_cancel_hint(
    "Yangi izohni yozing. Izohni olib tashlash uchun /skip."
)
ASK_NEW_LOCATION_MESSAGE = with_cancel_hint(
    "Yangi lokatsiyani yuboring — Telegram lokatsiyasi, xarita linki "
    "yoki koordinata: 55.75, 37.61"
)
NOT_A_LOCATION_MESSAGE = with_cancel_hint(
    "Buni lokatsiya sifatida o'qiy olmadim. "
    "Lokatsiya, xarita linki yoki koordinata yuboring."
)
UPDATED_MESSAGE = "✅ Yangilandi."

_EDIT_PLACE_KEY = "edit_place_id"


# Reached from inside "Mening ma'lumotlarim" — the gate on that section
# already decided who gets this far, so the list itself only needs an owner.
@router.callback_query(F.data == "my_data:places")
async def handle_my_places(
    callback_query: CallbackQuery,
    list_my_places: ListMyPlacesUseCase,
) -> None:
    user_id = user_id_of(callback_query)
    message = answerable_message(callback_query)
    if user_id is None or message is None:
        await callback_query.answer(EXPIRED_MESSAGE)
        return

    try:
        places = list_my_places.execute(user_id)
    except sqlite3.Error as error:
        report_service_error(error, "list my places")
        await message.answer(DATABASE_ERROR_MESSAGE)
        await callback_query.answer()
        return

    if not places:
        await message.answer(EMPTY_MESSAGE)
        await callback_query.answer()
        return

    # One message per place: the action buttons under a card target a single
    # place, so two places cannot share one card without the buttons lying.
    for place in places:
        await message.answer(
            format_place_card(place),
            reply_markup=build_my_place_actions_keyboard(place.id),
        )
    await callback_query.answer()


@router.callback_query(F.data.startswith("my_place:category:"))
async def handle_category_prompt(callback_query: CallbackQuery) -> None:
    place_id = _parse_id(callback_query.data, "my_place:category:")
    if place_id is None:
        await callback_query.answer(INVALID_SELECTION_MESSAGE)
        return

    message = answerable_message(callback_query)
    if message is None:
        await callback_query.answer(EXPIRED_MESSAGE)
        return

    await message.answer(
        "Yangi kategoriyani tanlang.",
        reply_markup=build_update_category_keyboard(place_id),
    )
    await callback_query.answer()


@router.callback_query(F.data.startswith("my_place:set_category:"))
async def handle_set_category(
    callback_query: CallbackQuery,
    update_place: UpdatePlaceUseCase,
) -> None:
    message = answerable_message(callback_query)
    if message is None:
        await callback_query.answer(EXPIRED_MESSAGE)
        return

    # The borders hide behind one button; opening them keeps the place id in
    # the callbacks, so the eventual choice still knows its target.
    group_place_id = _parse_border_group(callback_query.data)
    if group_place_id is not None:
        await message.answer(
            CHOOSE_BORDER_MESSAGE,
            reply_markup=build_border_choice_keyboard(
                f"my_place:set_category:{group_place_id}"
            ),
        )
        await callback_query.answer()
        return

    parsed = _parse_id_and_category(callback_query.data)
    user_id = user_id_of(callback_query)
    if parsed is None or user_id is None:
        await callback_query.answer(INVALID_SELECTION_MESSAGE)
        return

    place_id, category = parsed
    try:
        place = update_place.execute(
            place_id=place_id,
            user_id=user_id,
            category=category,
        )
    except sqlite3.Error as error:
        report_service_error(error, "update place category")
        await message.answer(DATABASE_ERROR_MESSAGE)
        await callback_query.answer()
        return

    # The refusal comes from the update itself returning None rather than a
    # separate ownership read: one source of truth for who may edit, and no
    # window between the check and the write.
    if place is None:
        await callback_query.answer(NOT_YOURS_MESSAGE)
        return

    await message.answer(
        format_place_card(place),
        reply_markup=build_my_place_actions_keyboard(place.id),
    )
    await callback_query.answer()


@router.callback_query(F.data.startswith("my_place:rename:"))
async def handle_rename_prompt(callback_query: CallbackQuery, state: FSMContext) -> None:
    await _prompt_edit(
        callback_query, state, "my_place:rename:", EditPlace.name, ASK_NEW_NAME_MESSAGE
    )


@router.callback_query(F.data.startswith("my_place:renote:"))
async def handle_renote_prompt(callback_query: CallbackQuery, state: FSMContext) -> None:
    await _prompt_edit(
        callback_query, state, "my_place:renote:", EditPlace.note, ASK_NEW_NOTE_MESSAGE
    )


@router.callback_query(F.data.startswith("my_place:move:"))
async def handle_move_prompt(callback_query: CallbackQuery, state: FSMContext) -> None:
    await _prompt_edit(
        callback_query,
        state,
        "my_place:move:",
        EditPlace.location,
        ASK_NEW_LOCATION_MESSAGE,
    )


async def _prompt_edit(
    callback_query: CallbackQuery,
    state: FSMContext,
    prefix: str,
    next_state,
    ask: str,
) -> None:
    """Remember which place is being edited and ask for the new value.

    Ownership is not checked here: the write itself refuses a stranger, and
    one source of truth beats a prompt-time check a forged callback could
    outrun anyway.
    """
    place_id = _parse_id(callback_query.data, prefix)
    if place_id is None:
        await callback_query.answer(INVALID_SELECTION_MESSAGE)
        return

    message = answerable_message(callback_query)
    if message is None:
        await callback_query.answer(EXPIRED_MESSAGE)
        return

    await state.set_state(next_state)
    await state.update_data(**{_EDIT_PLACE_KEY: place_id})
    await message.answer(ask)
    await callback_query.answer()


@router.message(EditPlace.name, F.text)
async def handle_rename(
    message: Message, state: FSMContext, update_place: UpdatePlaceUseCase
) -> None:
    name = (message.text or "").strip()
    if not name:
        # Same rule as adding one: a place has to keep a name other drivers
        # can search for.
        await message.answer(BLANK_NAME_MESSAGE)
        return

    await _apply_edit(message, state, update_place, name=name)


@router.message(EditPlace.note, Command("skip"))
async def handle_clear_note(
    message: Message, state: FSMContext, update_place: UpdatePlaceUseCase
) -> None:
    # /skip clears: a blank note is a value here, not an omission.
    await _apply_edit(message, state, update_place, note="")


@router.message(EditPlace.note, F.text)
async def handle_renote(
    message: Message, state: FSMContext, update_place: UpdatePlaceUseCase
) -> None:
    await _apply_edit(message, state, update_place, note=message.text or "")


@router.message(EditPlace.location)
async def handle_move(
    message: Message,
    state: FSMContext,
    update_place: UpdatePlaceUseCase,
    link_resolver: LinkResolver | None = None,
) -> None:
    # The same reader the add flow uses: location, venue, coordinates, full
    # map link, or a short link chased through its redirect.
    coordinates = await coordinates_from_message(message, link_resolver)
    if coordinates is None:
        await message.answer(NOT_A_LOCATION_MESSAGE)
        return

    await _apply_edit(message, state, update_place, coordinates=coordinates)


async def _apply_edit(
    message: Message,
    state: FSMContext,
    update_place: UpdatePlaceUseCase,
    **changes,
) -> None:
    data = await state.get_data()
    raw_place_id = data.get(_EDIT_PLACE_KEY)
    user_id = user_id_of(message)
    await state.clear()

    if raw_place_id is None or user_id is None:
        await message.answer(INVALID_SELECTION_MESSAGE)
        return

    try:
        place = update_place.execute(
            place_id=int(raw_place_id), user_id=user_id, **changes
        )
    except sqlite3.Error as error:
        report_service_error(error, "edit place")
        await message.answer(DATABASE_ERROR_MESSAGE)
        return

    # The refusal comes from the update itself returning None rather than a
    # separate ownership read: one source of truth for who may edit.
    if place is None:
        await message.answer(NOT_YOURS_MESSAGE)
        return

    await message.answer(
        f"{UPDATED_MESSAGE}\n\n{format_place_card(place)}",
        reply_markup=build_my_place_actions_keyboard(place.id),
    )


@router.callback_query(F.data.startswith("my_place:delete:"))
async def handle_delete_prompt(callback_query: CallbackQuery) -> None:
    place_id = _parse_id(callback_query.data, "my_place:delete:")
    if place_id is None:
        await callback_query.answer(INVALID_SELECTION_MESSAGE)
        return

    message = answerable_message(callback_query)
    if message is None:
        await callback_query.answer(EXPIRED_MESSAGE)
        return

    await message.answer(
        "Bu joyni o'chirasizmi?",
        reply_markup=build_place_delete_confirmation_keyboard(place_id),
    )
    await callback_query.answer()


@router.callback_query(F.data.startswith("my_place:confirm_delete:"))
async def handle_confirm_delete(
    callback_query: CallbackQuery,
    delete_place: DeletePlaceUseCase,
    super_admin_ids: tuple[int, ...] = (),
    bot: Bot | None = None,
) -> None:
    place_id = _parse_id(callback_query.data, "my_place:confirm_delete:")
    user_id = user_id_of(callback_query)
    if place_id is None or user_id is None:
        await callback_query.answer(INVALID_SELECTION_MESSAGE)
        return

    # Guard before the delete, not after: a place removed behind a driver who
    # cannot be told about it is a silent loss of shared data.
    message = answerable_message(callback_query)
    if message is None:
        await callback_query.answer(EXPIRED_MESSAGE)
        return

    try:
        deleted_place = delete_place.execute(place_id=place_id, user_id=user_id)
    except sqlite3.Error as error:
        report_service_error(error, "delete place")
        await message.answer(DATABASE_ERROR_MESSAGE)
        await callback_query.answer()
        return

    if deleted_place is None:
        await callback_query.answer(NOT_YOURS_MESSAGE)
        return

    await message.answer(DELETED_MESSAGE)

    # Deleting your own place is a right, but a spree of it is how the shared
    # database emptied once — the supers hear about each one immediately. A
    # super deleting their own place is spared the echo of themselves.
    if bot is not None:
        sender = callback_query.from_user
        recipients = tuple(
            admin_id for admin_id in super_admin_ids if admin_id != user_id
        )
        await announce_owner_deletion(
            bot,
            recipients,
            full_name=(sender.full_name or "") if sender else "",
            username=sender.username if sender else None,
            user_id=user_id,
            place_name=deleted_place.name,
        )

    await callback_query.answer()


@router.callback_query(F.data == "my_place:cancel_delete")
async def handle_cancel_delete(callback_query: CallbackQuery) -> None:
    message = answerable_message(callback_query)
    if message is not None:
        await message.answer(CANCELLED_MESSAGE)

    # The spinner is closed even when the message is gone: an unanswered
    # callback spins on the driver's screen until Telegram times it out.
    await callback_query.answer()


def _parse_id(data: str | None, prefix: str) -> int | None:
    if data is None or not data.startswith(prefix):
        return None
    raw = data.removeprefix(prefix)
    return int(raw) if raw.isdigit() else None


def _parse_id_and_category(data: str | None) -> tuple[int, PlaceCategory] | None:
    prefix = "my_place:set_category:"
    if data is None or not data.startswith(prefix):
        return None

    raw_id, _, raw_category = data.removeprefix(prefix).partition(":")
    if not raw_id.isdigit():
        return None
    try:
        return int(raw_id), PlaceCategory(raw_category)
    except ValueError:
        return None


def _parse_border_group(data: str | None) -> int | None:
    """The place id out of a border-group tap, or None for anything else."""
    prefix = "my_place:set_category:"
    if data is None or not data.startswith(prefix):
        return None

    raw_id, _, tail = data.removeprefix(prefix).partition(":")
    if tail == BORDER_GROUP_VALUE and raw_id.isdigit():
        return int(raw_id)
    return None
