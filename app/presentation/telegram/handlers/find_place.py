import sqlite3
from typing import Protocol

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.application.use_cases.admin import RecordSearchUseCase
from app.application.use_cases.documents import DocumentsForPlacesUseCase
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

from aiogram.types import BufferedInputFile

from app.domain.interfaces.links import LinkResolver
from app.domain.interfaces.maps import OverviewMapRenderer
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
    CATEGORY_PAGE_PREFIX,
    CHOOSE_BORDER_MESSAGE,
    build_border_choice_keyboard,
    build_category_choice_keyboard,
    build_category_results_keyboard,
    build_place_results_keyboard,
)
from app.presentation.telegram.prompts import with_cancel_hint
from app.presentation.telegram.states import NearbyPlace

router = Router(name="find_place")

ASK_QUERY_MESSAGE = (
    "Joy nomini yozing yoki kategoriyani tanlang.\n"
    "Masalan: Газпром, Кафе У Дороги."
)
# Both carry the driver's own radius: the search is only as wide as the
# setting they may never have opened.
NEARBY_PROMPT_TEMPLATE = with_cancel_hint(
    "Lokatsiyangizni yuboring — {radius_km} km radiusdagi qo'shilgan "
    "joylarni ko'rsataman."
)
OVERVIEW_CAPTION = (
    "🗺 Homaki xarita — bazadagi barcha joylar. Shular orasidan qidiriladi."
)

# What each dot on the sketch means. Mirrors the marker styles in the Google
# renderer — a test asserts the two stay in step, the same way the throttle
# defaults are checked against their middleware.
CATEGORY_BADGES: dict[PlaceCategory, str] = {
    PlaceCategory.RESTAURANT: "🟠 R",
    PlaceCategory.CAFE: "🟤 C",
    PlaceCategory.FUEL: "🔴 F",
    PlaceCategory.HOTEL: "🔵 H",
    PlaceCategory.PARKING: "⚪ P",
    PlaceCategory.CAR_SERVICE: "⚫ S",
    PlaceCategory.MOSQUE: "🟢 M",
    PlaceCategory.BORDER_KZ: "🟡 K",
    PlaceCategory.BORDER_RU: "🟡 U",
    PlaceCategory.OTHER: "⚪ O",
}
MULTI_BADGE_LINE = "🟣 — bir nechta kategoriyali joy"


def overview_legend(places: list) -> str:
    """Name only the dots the picture actually shows — a full table of eleven
    styles would bury the four that matter."""
    from app.presentation.telegram.keyboards.categories import category_label

    lines = []
    for category in PlaceCategory:
        drawn = any(
            len(place.categories) == 1 and place.category is category
            for place in places
        )
        if drawn:
            lines.append(f"{CATEGORY_BADGES[category]} — {category_label(category)}")

    if any(len(place.categories) > 1 for place in places):
        lines.append(MULTI_BADGE_LINE)

    return "\n".join(lines)
NEARBY_EMPTY_TEMPLATE = (
    "{radius_km} km ichida joy topilmadi — ⚙️ Sozlamalardan radiusni oshiring."
)
NOT_A_LOCATION_MESSAGE = with_cancel_hint(
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
    documents_for_places: DocumentsForPlacesUseCase | None = None,
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

    await _send_category_page(
        callback_query,
        message,
        category,
        page=0,
        find_places=find_places,
        user_settings=user_settings,
        count_places_by_category=count_places_by_category,
        documents_for_places=documents_for_places,
    )


@router.callback_query(F.data.startswith(f"{CATEGORY_PAGE_PREFIX}:"))
async def handle_category_page(
    callback_query: CallbackQuery,
    find_places: FindPlacesUseCase,
    user_settings: UserSettingsStore,
    count_places_by_category: CountPlacesByCategoryUseCase,
    documents_for_places: DocumentsForPlacesUseCase | None = None,
) -> None:
    """One page further into a category, drawn over the page it replaces."""
    message = answerable_message(callback_query)
    if message is None:
        await callback_query.answer(EXPIRED_MESSAGE)
        return

    parsed = _parse_category_page(callback_query.data)
    if parsed is None:
        await callback_query.answer(INVALID_SELECTION_MESSAGE)
        return

    category, page = parsed
    await _send_category_page(
        callback_query,
        message,
        category,
        page=page,
        find_places=find_places,
        user_settings=user_settings,
        count_places_by_category=count_places_by_category,
        documents_for_places=documents_for_places,
        edit=True,
    )


async def _send_category_page(
    callback_query: CallbackQuery,
    message,
    category: PlaceCategory,
    page: int,
    find_places: FindPlacesUseCase,
    user_settings: UserSettingsStore,
    count_places_by_category: CountPlacesByCategoryUseCase,
    documents_for_places: DocumentsForPlacesUseCase | None,
    edit: bool = False,
) -> None:
    user_id = user_id_of(callback_query)
    if user_id is None:
        await callback_query.answer(INVALID_SELECTION_MESSAGE)
        return

    # The driver's own result count is the page size, so the setting they
    # already understand decides how much arrives at once.
    page_size = user_settings.get(user_id).result_limit
    try:
        places = find_places.execute(
            category=category, limit=page_size, offset=page * page_size
        )
    except sqlite3.Error as error:
        report_service_error(error, "category browse")
        await message.answer(DATABASE_ERROR_MESSAGE)
        await callback_query.answer()
        return

    # The same count the category button advertises, so the arrows agree with
    # the number the driver tapped. Without it there is simply no next page.
    total = (_counts_or_none(count_places_by_category) or {}).get(category, len(places))
    keyboard = build_category_results_keyboard(
        [place.id for place in places],
        category=category,
        page=page,
        total=total,
        page_size=page_size,
    )
    await _send_results(
        message,
        places,
        documents_for_places=documents_for_places,
        keyboard=keyboard,
        start_number=page * page_size + 1,
        edit=edit,
    )
    await callback_query.answer()


@router.message(F.text == NEARBY_BUTTON)
async def handle_nearby_start(
    message: Message,
    state: FSMContext,
    user_settings: UserSettingsStore,
    find_places: FindPlacesUseCase | None = None,
    overview_map: OverviewMapRenderer | None = None,
) -> None:
    await state.set_state(NearbyPlace.location)
    prompt = NEARBY_PROMPT_TEMPLATE.format(radius_km=_radius_km(message, user_settings))

    # A sketch of everything the database holds, bounds fitted to the dots:
    # the driver sees what there even is before sharing where they are. Any
    # failure along the way quietly falls back to the plain prompt.
    sketch, sketched_places = await _overview_sketch(find_places, overview_map)
    if sketch is not None:
        legend = overview_legend(sketched_places)
        try:
            await message.answer_photo(
                BufferedInputFile(sketch, filename="joylar_xaritasi.png"),
                caption=f"{OVERVIEW_CAPTION}\n\n{legend}\n\n{prompt}",
            )
            return
        except TelegramAPIError as error:
            report_service_error(error, "overview sketch")

    await message.answer(prompt)


async def _overview_sketch(
    find_places: FindPlacesUseCase | None,
    overview_map: OverviewMapRenderer | None,
) -> tuple[bytes | None, list]:
    if find_places is None or overview_map is None:
        return None, []

    try:
        places = find_places.execute(limit=-1)
    except sqlite3.Error as error:
        report_service_error(error, "overview places")
        return None, []

    if not places:
        return None, []

    return await overview_map.render(places), places


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
    documents_for_places: DocumentsForPlacesUseCase | None = None,
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
    await _send_results(
        message,
        places[:limit],
        distances[:limit],
        note,
        documents_for_places=documents_for_places,
    )


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
    documents_for_places: DocumentsForPlacesUseCase | None = None,
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

    await _send_results(message, places, documents_for_places=documents_for_places)


async def _send_results(
    message,
    places,
    distances=None,
    distance_note=None,
    documents_for_places=None,
    keyboard=None,
    start_number: int = 1,
    edit: bool = False,
) -> None:
    if not places:
        await message.answer(format_place_results([]))
        return

    # The papers pinned to these places ride along under each entry. Losing
    # them to a database hiccup is not worth losing the results themselves.
    documents_by_place = None
    if documents_for_places is not None:
        try:
            documents_by_place = documents_for_places.execute(
                tuple(place.id for place in places)
            )
        except sqlite3.Error as error:
            report_service_error(error, "documents for results")

    text = format_place_results(
        places,
        distances,
        distance_note,
        documents_by_place=documents_by_place,
        start_number=start_number,
    )
    markup = keyboard or build_place_results_keyboard(
        [place.id for place in places], start_number=start_number
    )
    # A page turn redraws the list in place: a fresh message per page would
    # bury the list under its own history.
    send = message.edit_text if edit else message.answer
    await send(
        text,
        reply_markup=markup,
        parse_mode="HTML",
        # Every result carries its own link already; ten link previews under
        # one list would bury the list itself.
        disable_web_page_preview=True,
    )


def _parse_category_page(data: str | None) -> tuple[PlaceCategory, int] | None:
    """Read ``find:cat_page:<category>:<page>`` back into its two halves."""
    prefix = f"{CATEGORY_PAGE_PREFIX}:"
    if data is None or not data.startswith(prefix):
        return None

    value, _, page = data.removeprefix(prefix).rpartition(":")
    if not page.isdigit():
        return None
    try:
        return PlaceCategory(value), int(page)
    except ValueError:
        return None


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

