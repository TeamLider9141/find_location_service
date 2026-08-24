import sqlite3
from typing import Protocol

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.application.use_cases.admin import RecordSearchUseCase
from app.application.use_cases.places import (
    CountPlacesByCategoryUseCase,
    FindPlacesUseCase,
    GetPlaceUseCase,
    NearbyPlacesUseCase,
)
from app.domain.value_objects.category import PlaceCategory
from app.domain.value_objects.coordinates import Coordinates
from app.domain.value_objects.user_settings import UserSettings
from app.presentation.telegram.errors import (
    EXPIRED_MESSAGE,
    answerable_message,
    report_service_error,
    user_id_of,
)
from app.presentation.telegram.formatters import (
    format_place_card,
    format_place_results,
)
from app.presentation.telegram.keyboards.menu import NEARBY_BUTTON, SEARCH_BUTTON
from app.presentation.telegram.keyboards.places import (
    build_category_choice_keyboard,
    build_place_results_keyboard,
)
from app.presentation.telegram.states import NearbyPlace

router = Router(name="find_place")

ASK_QUERY_MESSAGE = (
    "Joy nomini yozing yoki kategoriyani tanlang.\n"
    "Masalan: Газпром, Кафе У Дороги."
)
ASK_NEARBY_LOCATION_MESSAGE = (
    "Hozirgi lokatsiyangizni yuboring — yaqin atrofdagi joylarni ko'rsataman."
)
NOT_A_LOCATION_MESSAGE = (
    "Buni lokatsiya sifatida o'qiy olmadim. Telegram lokatsiyasini yuboring."
)
INVALID_SELECTION_MESSAGE = "Tanlov eskirgan. Qayta qidirib ko'ring."
PLACE_GONE_MESSAGE = "Bu joy o'chirilgan."
DATABASE_ERROR_MESSAGE = "Baza bilan muammo. Birozdan so'ng urinib ko'ring."


class UserSettingsStore(Protocol):
    def get(self, user_id: int) -> UserSettings:
        """Return current settings for a Telegram user."""


@router.message(F.text == SEARCH_BUTTON)
async def handle_find_start(
    message: Message, count_places_by_category: CountPlacesByCategoryUseCase
) -> None:
    try:
        counts = count_places_by_category.execute()
    except sqlite3.Error as error:
        # The keyboard still works without the numbers; failing the whole
        # search over a decoration would be backwards.
        report_service_error(error, "category counts")
        counts = None

    await message.answer(
        ASK_QUERY_MESSAGE,
        reply_markup=build_category_choice_keyboard("find:category", counts),
    )


@router.callback_query(F.data.startswith("find:category:"))
async def handle_category_browse(
    callback_query: CallbackQuery,
    find_places: FindPlacesUseCase,
    user_settings: UserSettingsStore,
) -> None:
    category = _parse_category(callback_query.data, "find:category:")
    user_id = user_id_of(callback_query)
    if category is None or user_id is None:
        await callback_query.answer(INVALID_SELECTION_MESSAGE)
        return

    message = answerable_message(callback_query)
    if message is None:
        await callback_query.answer(EXPIRED_MESSAGE)
        return

    limit = user_settings.get(user_id).result_limit
    try:
        places = find_places.execute(category=category, limit=limit)
    except sqlite3.Error as error:
        report_service_error(error, "category browse")
        await message.answer(DATABASE_ERROR_MESSAGE)
        await callback_query.answer()
        return

    await _send_results(message, places)
    await callback_query.answer()


@router.message(F.text == NEARBY_BUTTON)
async def handle_nearby_start(message: Message, state: FSMContext) -> None:
    await state.set_state(NearbyPlace.location)
    await message.answer(ASK_NEARBY_LOCATION_MESSAGE)


@router.message(NearbyPlace.location)
async def handle_nearby_location(
    message: Message,
    state: FSMContext,
    nearby_places: NearbyPlacesUseCase,
    user_settings: UserSettingsStore,
) -> None:
    coordinates = _coordinates_from_message(message)
    user_id = user_id_of(message)
    if coordinates is None or user_id is None:
        await message.answer(NOT_A_LOCATION_MESSAGE)
        return

    settings = user_settings.get(user_id)
    try:
        places = nearby_places.execute(
            coordinates,
            radius_meters=settings.nearby_radius_meters,
            limit=settings.result_limit,
        )
    except sqlite3.Error as error:
        report_service_error(error, "nearby search")
        await state.clear()
        await message.answer(DATABASE_ERROR_MESSAGE)
        return

    await state.clear()
    distances = [coordinates.distance_to(place.coordinates) for place in places]
    await _send_results(message, places, distances)


@router.callback_query(F.data.startswith("place:"))
async def handle_place_card(
    callback_query: CallbackQuery,
    get_place: GetPlaceUseCase,
) -> None:
    place_id = _parse_place_id(callback_query.data)
    if place_id is None:
        await callback_query.answer(INVALID_SELECTION_MESSAGE)
        return

    message = answerable_message(callback_query)
    if message is None:
        await callback_query.answer(EXPIRED_MESSAGE)
        return

    place = get_place.execute(place_id)
    if place is None:
        await callback_query.answer(PLACE_GONE_MESSAGE)
        return

    await message.answer(format_place_card(place))
    await callback_query.answer()


# Registered last inside this router: a bare text message is a name search.
@router.message(F.text)
async def handle_text_query(
    message: Message,
    find_places: FindPlacesUseCase,
    user_settings: UserSettingsStore,
    record_search: RecordSearchUseCase,
) -> None:
    query = (message.text or "").strip()
    user_id = user_id_of(message)
    # An empty name matches every place in the database, so a stray blank
    # message would answer with the whole table rather than nothing.
    if not query or user_id is None:
        return

    # Logged before the search runs: what drivers look for is worth knowing
    # even when the database has no answer for them.
    try:
        record_search.execute(user_id, query)
    except sqlite3.Error as error:
        report_service_error(error, "record search")

    limit = user_settings.get(user_id).result_limit
    try:
        places = find_places.execute(name=query, limit=limit)
    except sqlite3.Error as error:
        report_service_error(error, "name search")
        await message.answer(DATABASE_ERROR_MESSAGE)
        return

    await _send_results(message, places)


async def _send_results(message, places, distances=None) -> None:
    if not places:
        await message.answer(format_place_results([]))
        return

    await message.answer(
        format_place_results(places, distances),
        reply_markup=build_place_results_keyboard([place.id for place in places]),
    )


def _parse_category(data: str | None, prefix: str) -> PlaceCategory | None:
    if data is None or not data.startswith(prefix):
        return None
    try:
        return PlaceCategory(data.removeprefix(prefix))
    except ValueError:
        return None


def _parse_place_id(data: str | None) -> int | None:
    prefix = "place:"
    if data is None or not data.startswith(prefix):
        return None
    raw = data.removeprefix(prefix)
    # isdigit rather than a try/except: a non-numeric payload has to end as a
    # closed spinner, not an exception aiogram logs and the driver never sees.
    return int(raw) if raw.isdigit() else None


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

    return None
