import sqlite3

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.application.use_cases.access import RequestAddAccessUseCase
from app.application.use_cases.places import AddPlaceUseCase
from app.domain.value_objects.add_access import AddAccessStatus
from app.domain.value_objects.category import PlaceCategory
from app.domain.value_objects.coordinates import Coordinates
from app.presentation.telegram.access import is_admin
from app.presentation.telegram.errors import (
    EXPIRED_MESSAGE,
    answerable_message,
    report_service_error,
    user_id_of,
)
from app.presentation.telegram.formatters import (
    format_duplicate_warning,
    format_place_card,
    format_place_preview,
)
from aiogram.exceptions import TelegramAPIError
from app.presentation.telegram.keyboards.menu import (
    ADD_PLACE_BUTTON,
    build_main_menu_keyboard,
)
from app.domain.interfaces.links import LinkResolver
from app.presentation.telegram.location_resolution import coordinates_from_message
from app.presentation.telegram.keyboards.places import (
    BORDER_CATEGORIES,
    BORDER_GROUP_VALUE,
    CHOOSE_AT_LEAST_ONE_MESSAGE,
    CHOOSE_BORDER_MESSAGE,
    DONE_VALUE,
    build_border_toggle_keyboard,
    build_category_toggle_keyboard,
    build_duplicate_confirmation_keyboard,
    build_preview_keyboard,
)
from app.presentation.telegram.notifications import announce_add_request
from app.presentation.telegram.prompts import with_cancel_hint
from app.presentation.telegram.states import AddPlace

router = Router(name="add_place")

# The flow, in the order the driver walks it: location first — it is the one
# thing they have to be standing at — then category, name, note, and a preview
# to look at before anything is written. Every prompt that waits for input
# names the way out: a driver who tapped the wrong button mid-flow is stuck
# behind a question they cannot answer otherwise.
ASK_LOCATION_MESSAGE = with_cancel_hint(
    "Joy lokatsiyasini yuboring.\n\n"
    "📎 → Lokatsiya, yoki xarita linkini, yoki koordinatani yozing: 55.75, 37.61"
)
ASK_LOCATION_AGAIN_MESSAGE = with_cancel_hint(
    "Buni lokatsiya sifatida o'qiy olmadim. "
    "Telegram lokatsiyasini yuboring yoki koordinatani yozing: 55.75, 37.61"
)
ASK_CATEGORY_MESSAGE = with_cancel_hint(
    "Kategoriyalarni tanlang — bir nechtasini belgilash mumkin.\n"
    "Bo'lgach ➡️ Davom etish tugmasini bosing."
)
ASK_NAME_MESSAGE = with_cancel_hint(
    "Joy nomini yozing. Masalan: Газпром yoki Кафе У Дороги."
)
BLANK_NAME_MESSAGE = with_cancel_hint("Nom bo'sh bo'lmasligi kerak. Joy nomini yozing.")
ASK_NOTE_MESSAGE = with_cancel_hint(
    "Izoh qo'shasizmi? Masalan: M5, 120-km, kechasi ochiq.\n"
    "Kerak bo'lmasa /skip yuboring."
)
PREVIEW_MESSAGE = "Ko'rib chiqing — saqlansa sizga va boshqa haydovchilarga shunday ko'rinadi:"
INVALID_CATEGORY_MESSAGE = "Bunday kategoriya yo'q. Ro'yxatdan tanlang."
CANCELLED_MESSAGE = "Bekor qilindi. Boshlang'ich menyuga qaytdingiz."
SAVE_FAILED_MESSAGE = "Saqlab bo'lmadi. Qaytadan urinib ko'ring."
DATABASE_ERROR_MESSAGE = "Baza bilan muammo. Birozdan so'ng urinib ko'ring."
GATE_REQUESTED_MESSAGE = (
    "Joy qo'shish uchun admin ruxsati kerak.\n"
    "So'rovingiz adminga yuborildi — javob kelishi bilan xabar beraman."
)
GATE_PENDING_MESSAGE = "So'rovingiz adminda ko'rilmoqda. Javobini kuting."


@router.message(F.text == ADD_PLACE_BUTTON)
async def handle_add_place_start(
    message: Message,
    state: FSMContext,
    request_add_access: RequestAddAccessUseCase,
    admin_ids: tuple[int, ...],
    bot: Bot | None = None,
) -> None:
    # Anyone may search; writing to the shared database needs the admin's nod.
    # Admins skip their own gate.
    if not is_admin(message, admin_ids):
        allowed = await _pass_the_gate(message, request_add_access, admin_ids, bot)
        if not allowed:
            return

    # Clear before setting the state: an abandoned flow leaves its coordinates
    # in storage, and carrying them into a fresh attempt would file the new
    # place at the old location.
    await state.set_data({})
    await state.set_state(AddPlace.location)
    await message.answer(ASK_LOCATION_MESSAGE)


async def _pass_the_gate(
    message: Message,
    request_add_access: RequestAddAccessUseCase,
    admin_ids: tuple[int, ...],
    bot: Bot | None,
) -> bool:
    """Let an approved driver through; turn a request into news for the admins.

    A pending driver is reminded to wait rather than re-announced — tapping the
    button ten times must not page the admins ten times.
    """
    user_id = user_id_of(message)
    if user_id is None:
        return False

    try:
        previous = request_add_access.execute(user_id)
    except sqlite3.Error as error:
        report_service_error(error, "add access request")
        await message.answer(DATABASE_ERROR_MESSAGE)
        return False

    if previous == AddAccessStatus.APPROVED:
        return True

    if previous == AddAccessStatus.PENDING:
        await message.answer(GATE_PENDING_MESSAGE)
        return False

    await message.answer(GATE_REQUESTED_MESSAGE)
    if bot is not None:
        sender = message.from_user
        await announce_add_request(
            bot,
            admin_ids,
            full_name=sender.full_name or "",
            username=sender.username,
            user_id=user_id,
        )
    return False


@router.message(AddPlace.location)
async def handle_location(
    message: Message,
    state: FSMContext,
    link_resolver: LinkResolver | None = None,
) -> None:
    coordinates = await coordinates_from_message(message, link_resolver)
    if coordinates is None:
        await message.answer(ASK_LOCATION_AGAIN_MESSAGE)
        return

    await state.update_data(
        latitude=coordinates.latitude,
        longitude=coordinates.longitude,
        categories=[],
    )
    await state.set_state(AddPlace.category)
    await message.answer(
        ASK_CATEGORY_MESSAGE,
        reply_markup=build_category_toggle_keyboard("add_place:category", ()),
    )


@router.callback_query(AddPlace.category, F.data.startswith("add_place:category:"))
async def handle_category(callback_query: CallbackQuery, state: FSMContext) -> None:
    """The multi-select step: taps toggle, "Davom etish" moves the flow on."""
    message = answerable_message(callback_query)
    if message is None:
        await callback_query.answer(EXPIRED_MESSAGE)
        return

    data = await state.get_data()
    selected = _selected_categories(data)

    # The borders hide behind one button; tapping it opens them and the state
    # stays right here, waiting for the real choices.
    if callback_query.data == f"add_place:category:{BORDER_GROUP_VALUE}":
        await message.answer(
            CHOOSE_BORDER_MESSAGE,
            reply_markup=build_border_toggle_keyboard("add_place:category", selected),
        )
        await callback_query.answer()
        return

    if callback_query.data == f"add_place:category:{DONE_VALUE}":
        if not selected:
            await callback_query.answer(CHOOSE_AT_LEAST_ONE_MESSAGE, show_alert=True)
            return

        # Two roads lead here: the flow's own category step, and the preview's
        # "change category" button. The second returns to the preview — the
        # driver was already done writing.
        if data.get("editing_category"):
            await state.update_data(editing_category=False)
            await _show_preview(message, state)
        else:
            await state.set_state(AddPlace.name)
            await message.answer(ASK_NAME_MESSAGE)
        await callback_query.answer()
        return

    category = _parse_category(callback_query.data)
    if category is None:
        await callback_query.answer(INVALID_CATEGORY_MESSAGE)
        return

    # Toggle, keeping the order the driver picked in.
    if category in selected:
        selected = tuple(c for c in selected if c is not category)
    else:
        selected = (*selected, category)
    await state.update_data(categories=[c.value for c in selected])

    # Redraw in place: fifty toggle taps must not leave fifty keyboards behind.
    rebuild = (
        build_border_toggle_keyboard
        if category in BORDER_CATEGORIES
        else build_category_toggle_keyboard
    )
    try:
        await message.edit_reply_markup(
            reply_markup=rebuild("add_place:category", selected)
        )
    except TelegramAPIError as error:
        report_service_error(error, "category toggle redraw")

    await callback_query.answer()


def _selected_categories(data: dict) -> tuple[PlaceCategory, ...]:
    selected = []
    for raw in data.get("categories", []):
        try:
            selected.append(PlaceCategory(str(raw)))
        except ValueError:
            continue
    return tuple(selected)


@router.message(AddPlace.name, F.text)
async def handle_name(message: Message, state: FSMContext) -> None:
    name = (message.text or "").strip()
    if not name:
        await message.answer(BLANK_NAME_MESSAGE)
        return

    await state.update_data(name=name)
    await state.set_state(AddPlace.note)
    await message.answer(ASK_NOTE_MESSAGE)


@router.message(AddPlace.note, Command("skip"))
async def handle_skip_note(message: Message, state: FSMContext) -> None:
    await state.update_data(note="")
    await _show_preview(message, state)


@router.message(AddPlace.note, F.text)
async def handle_note(message: Message, state: FSMContext) -> None:
    await state.update_data(note=message.text or "")
    await _show_preview(message, state)


async def _show_preview(message: Message, state: FSMContext) -> None:
    """Show the place exactly as everyone will see it, before it is written."""
    data = await state.get_data()
    try:
        categories = _selected_categories(data)
        if not categories:
            raise ValueError("no categories selected")
        preview = format_place_preview(
            name=str(data["name"]),
            categories=categories,
            coordinates=Coordinates(
                latitude=float(data["latitude"]),
                longitude=float(data["longitude"]),
            ),
            note=str(data.get("note", "")),
        )
    # A flow that lost a step leaves the state short of a key; better to start
    # over than to preview a place that cannot be saved.
    except (KeyError, ValueError) as error:
        report_service_error(error, "place preview")
        await state.clear()
        await message.answer(SAVE_FAILED_MESSAGE)
        return

    await state.set_state(AddPlace.preview)
    await message.answer(
        f"{PREVIEW_MESSAGE}\n\n{preview}",
        reply_markup=build_preview_keyboard(),
    )


@router.callback_query(AddPlace.preview, F.data == "add_place:preview:category")
async def handle_preview_change_category(
    callback_query: CallbackQuery, state: FSMContext
) -> None:
    message = answerable_message(callback_query)
    if message is None:
        await state.clear()
        await callback_query.answer(EXPIRED_MESSAGE)
        return

    await state.update_data(editing_category=True)
    await state.set_state(AddPlace.category)
    data = await state.get_data()
    await message.answer(
        ASK_CATEGORY_MESSAGE,
        reply_markup=build_category_toggle_keyboard(
            "add_place:category", _selected_categories(data)
        ),
    )
    await callback_query.answer()


@router.callback_query(AddPlace.preview, F.data == "add_place:preview:save")
async def handle_preview_save(
    callback_query: CallbackQuery,
    state: FSMContext,
    add_place: AddPlaceUseCase,
    admin_ids: tuple[int, ...],
) -> None:
    message = answerable_message(callback_query)
    if message is None:
        await state.clear()
        await callback_query.answer(EXPIRED_MESSAGE)
        return

    data = await state.get_data()
    # The duplicate check runs at the moment of decision: earlier the name did
    # not exist yet, later the copy would already be written.
    try:
        duplicates = add_place.find_duplicates(
            name=str(data.get("name", "")),
            coordinates=Coordinates(
                latitude=float(data.get("latitude", 0.0)),
                longitude=float(data.get("longitude", 0.0)),
            ),
        )
    except sqlite3.Error as error:
        report_service_error(error, "duplicate check")
        await message.answer(DATABASE_ERROR_MESSAGE)
        await callback_query.answer()
        return

    if duplicates:
        await state.set_state(AddPlace.duplicate)
        await message.answer(
            format_duplicate_warning(duplicates),
            reply_markup=build_duplicate_confirmation_keyboard(),
        )
        await callback_query.answer()
        return

    await _save(message, state, add_place, admin_ids, actor=callback_query)
    await callback_query.answer()


@router.callback_query(AddPlace.duplicate, F.data.startswith("add_place:duplicate:"))
async def handle_duplicate_answer(
    callback_query: CallbackQuery,
    state: FSMContext,
    add_place: AddPlaceUseCase,
    admin_ids: tuple[int, ...],
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
        await _save(message, state, add_place, admin_ids, actor=callback_query)
    else:
        await state.clear()
        await message.answer(
            CANCELLED_MESSAGE,
            # Whoever reaches this flow passed the add gate, and the document
            # button rides on the same right.
            reply_markup=build_main_menu_keyboard(
                is_admin=is_admin(callback_query, admin_ids), can_add_documents=True
            ),
        )

    await callback_query.answer()


async def _save(
    message: Message,
    state: FSMContext,
    add_place: AddPlaceUseCase,
    admin_ids: tuple[int, ...],
    actor: object,
) -> None:
    """Write the place the preview promised. ``actor`` is whoever tapped —
    the message under a callback belongs to the bot, not the driver."""
    # Whoever reaches this flow passed the add gate, and the document button
    # rides on the same right.
    menu = build_main_menu_keyboard(
        is_admin=is_admin(actor, admin_ids), can_add_documents=True
    )
    data = await state.get_data()
    user_id = user_id_of(actor)
    if user_id is None:
        await state.clear()
        return

    try:
        place = add_place.execute(
            user_id=user_id,
            name=str(data["name"]),
            categories=_selected_categories(data),
            coordinates=Coordinates(
                latitude=float(data["latitude"]),
                longitude=float(data["longitude"]),
            ),
            note=str(data.get("note", "")),
        )
    # A flow that lost a step leaves the state short of a key, and a place
    # written without it would land at the wrong coordinates rather than fail.
    except (KeyError, ValueError) as error:
        report_service_error(error, "add place")
        await state.clear()
        await message.answer(SAVE_FAILED_MESSAGE, reply_markup=menu)
        return
    except sqlite3.Error as error:
        report_service_error(error, "add place")
        await state.clear()
        await message.answer(DATABASE_ERROR_MESSAGE, reply_markup=menu)
        return

    await state.clear()
    await message.answer(
        f"✅ Saqlandi.\n\n{format_place_card(place)}",
        reply_markup=menu,
    )


def _parse_category(data: str | None) -> PlaceCategory | None:
    prefix = "add_place:category:"
    if data is None or not data.startswith(prefix):
        return None
    try:
        return PlaceCategory(data.removeprefix(prefix))
    except ValueError:
        return None

