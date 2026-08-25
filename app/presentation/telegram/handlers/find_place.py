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
from aiogram.exceptions import TelegramAPIError

from app.domain.interfaces.links import LinkResolver
from app.domain.interfaces.routing import RoadRouter
from app.presentation.telegram.location_resolution import coordinates_from_message
from app.presentation.telegram.formatters import (
    ROAD_DISTANCE_NOTE,
    STRAIGHT_DISTANCE_NOTE,
    format_place_card,
    format_place_results,
)
from app.presentation.telegram.keyboards.menu import NEARBY_BUTTON, SEARCH_BUTTON
from app.presentation.telegram.keyboards.places import (
    BORDER_GROUP_VALUE,
    CHOOSE_BORDER_MESSAGE,
    build_border_choice_keyboard,
    build_category_choice_keyboard,
    build_place_results_keyboard,
)
from app.presentation.telegram.states import NearbyPlace

router = Router(name="find_place")

ASK_QUERY_MESSAGE = (
    "Joy nomini yozing yoki kategoriyani tanlang.\n"
    "Masalan: Газпром, Кафе У Дороги."
)
# Both carry the driver's own radius: the search is only as wide as the
# setting they may never have opened.
NEARBY_PROMPT_TEMPLATE = (
    "Lokatsiyangizni yuboring — {radius_km} km radiusdagi qo'shilgan "
    "joylarni ko'rsataman."
)
NEARBY_EMPTY_TEMPLATE = (
    "{radius_km} km ichida joy topilmadi — ⚙️ Sozlamalardan radiusni oshiring."
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
    await message.answer(
        ASK_QUERY_MESSAGE,
        reply_markup=build_category_choice_keyboard(
            "find:category", _counts_or_none(count_places_by_category)
        ),
    )


def _counts_or_none(
    count_places_by_category: CountPlacesByCategoryUseCase,
) -> dict[PlaceCategory, int] | None:
    """The keyboard still works without the numbers; failing the whole search
    over a decoration would be backwards."""
    try:
        return count_places_by_category.execute()
    except sqlite3.Error as error:
        report_service_error(error, "category counts")
        return None


@router.callback_query(F.data.startswith("find:category:"))
async def handle_category_browse(
    callback_query: CallbackQuery,
    find_places: FindPlacesUseCase,
    user_settings: UserSettingsStore,
    count_places_by_category: CountPlacesByCategoryUseCase,
) -> None:
    message = answerable_message(callback_query)
    if message is None:
        await callback_query.answer(EXPIRED_MESSAGE)
        return

    if callback_query.data == f"find:category:{BORDER_GROUP_VALUE}":
        await message.answer(
            CHOOSE_BORDER_MESSAGE,
            reply_markup=build_border_choice_keyboard(
                "find:category", _counts_or_none(count_places_by_category)
            ),
        )
        await callback_query.answer()
        return

    category = _parse_category(callback_query.data, "find:category:")
    user_id = user_id_of(callback_query)
    if category is None or user_id is None:
        await callback_query.answer(INVALID_SELECTION_MESSAGE)
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
async def handle_nearby_start(
    message: Message, state: FSMContext, user_settings: UserSettingsStore
) -> None:
    await state.set_state(NearbyPlace.location)
    await message.answer(
        NEARBY_PROMPT_TEMPLATE.format(radius_km=_radius_km(message, user_settings))
    )


def _radius_km(message: Message, user_settings: UserSettingsStore) -> int:
    user_id = user_id_of(message)
    settings = user_settings.get(user_id) if user_id is not None else UserSettings()
    return settings.nearby_radius_meters // 1000


@router.message(NearbyPlace.location)
async def handle_nearby_location(
    message: Message,
    state: FSMContext,
    nearby_places: NearbyPlacesUseCase,
    user_settings: UserSettingsStore,
    road_router: RoadRouter | None = None,
    link_resolver: LinkResolver | None = None,
) -> None:
    coordinates = await coordinates_from_message(message, link_resolver)
    user_id = user_id_of(message)
    if coordinates is None or user_id is None:
        await message.answer(NOT_A_LOCATION_MESSAGE)
        return

    settings = user_settings.get(user_id)
    try:
        # More candidates than the driver will see: the nearest by road is not
        # always the nearest by air, so the re-sort needs room to promote.
        places = nearby_places.execute(
            coordinates,
            radius_meters=settings.nearby_radius_meters,
            limit=max(settings.result_limit, ROAD_CANDIDATES),
        )
    except sqlite3.Error as error:
        report_service_error(error, "nearby search")
        await state.clear()
        await message.answer(DATABASE_ERROR_MESSAGE)
        return

    await state.clear()

    if not places:
        # The generic "nothing found" invites adding a place; here the likelier
        # fix is one tap away in the settings.
        await message.answer(
            NEARBY_EMPTY_TEMPLATE.format(radius_km=settings.nearby_radius_meters // 1000)
        )
        return

    places, distances, note = await _by_road_or_by_air(
        message, road_router, coordinates, places
    )
    limit = settings.result_limit
    await _send_results(message, places[:limit], distances[:limit], note)


# Enough for the re-sort to matter, few enough for one routing request.
ROAD_CANDIDATES = 15
SEARCHING_MESSAGE = "⏳ Iltimos kuting — eng yaqin manzillarni qidiryapmiz..."


async def _by_road_or_by_air(
    message: Message,
    road_router: RoadRouter | None,
    origin: Coordinates,
    places: list,
) -> tuple[list, list[float], str]:
    """Sort by road distance when the router answers, by air when it cannot.

    The fallback is silent by design: a slow routing service is the routing
    service's problem, not the driver's.
    """
    straight = [origin.distance_to(place.coordinates) for place in places]

    if road_router is None:
        return places, straight, STRAIGHT_DISTANCE_NOTE

    waiting = await message.answer(SEARCHING_MESSAGE)
    by_road = await road_router.road_distances(
        origin, [place.coordinates for place in places]
    )
    # The wait notice has served its purpose; the results speak next. A double
    # that returns nothing from answer() simply keeps its notice.
    try:
        await waiting.delete()
    except (AttributeError, TelegramAPIError):
        pass

    if by_road is None:
        return places, straight, STRAIGHT_DISTANCE_NOTE

    paired = sorted(zip(by_road, places), key=lambda item: item[0])
    return (
        [place for _, place in paired],
        [distance for distance, _ in paired],
        ROAD_DISTANCE_NOTE,
    )


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


async def _send_results(message, places, distances=None, distance_note=None) -> None:
    if not places:
        await message.answer(format_place_results([]))
        return

    await message.answer(
        format_place_results(places, distances, distance_note),
        reply_markup=build_place_results_keyboard([place.id for place in places]),
        parse_mode="HTML",
        # Every result carries its own link already; ten link previews under
        # one list would bury the list itself.
        disable_web_page_preview=True,
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

