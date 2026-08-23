from typing import Protocol

import httpx
from aiogram import F, Router
from aiogram.types import CallbackQuery

from app.domain.entities.location import Location
from app.domain.entities.place import Place
from app.domain.value_objects.category import PlaceCategory
from app.domain.value_objects.coordinates import Coordinates
from app.domain.value_objects.user_settings import UserSettings
from app.presentation.telegram.errors import (
    EXPIRED_MESSAGE,
    SERVICE_UNAVAILABLE_MESSAGE,
    answerable_message,
    report_service_error,
    user_id_of,
)
from app.presentation.telegram.formatters import format_nearby_places, format_selected_location
from app.presentation.telegram.keyboards.locations import (
    build_realtime_nearby_categories_keyboard,
    build_selected_location_actions_keyboard,
)

router = Router(name="location")

INVALID_SELECTION_MESSAGE = "Tanlov eskirgan. Qayta qidirib ko'ring."


class LocationSelectionStore(Protocol):
    def get(self, user_id: int, index: int) -> Location | None:
        """Return a previously stored location for a Telegram user."""


class NearbyPlacesUseCase(Protocol):
    async def execute(
        self,
        coordinates: Coordinates,
        category: PlaceCategory,
        radius_meters: int = 3000,
        limit: int = 10,
    ) -> list[Place]:
        """Return nearby places for coordinates and category."""


class AddLocationFlowStore(Protocol):
    def start_realtime_nearby(self, user_id: int, category: PlaceCategory) -> None:
        """Start a realtime nearby flow for the selected category."""


class UserSettingsStore(Protocol):
    def get(self, user_id: int) -> UserSettings:
        """Return current settings for a Telegram user."""


@router.callback_query(F.data.startswith("location:"))
async def handle_location_selection(
    callback_query: CallbackQuery,
    selection_store: LocationSelectionStore,
) -> None:
    index = _parse_location_index(callback_query.data)
    user_id = user_id_of(callback_query)
    if index is None or user_id is None:
        await callback_query.answer(INVALID_SELECTION_MESSAGE)
        return

    location = selection_store.get(user_id, index)
    if location is None:
        await callback_query.answer(INVALID_SELECTION_MESSAGE)
        return

    message = answerable_message(callback_query)
    if message is None:
        await callback_query.answer(EXPIRED_MESSAGE)
        return

    await message.answer(
        format_selected_location(location, result_number=index + 1),
        reply_markup=build_selected_location_actions_keyboard(index),
    )
    await callback_query.answer()


@router.callback_query(F.data.startswith("nearby:"))
async def handle_nearby_category_selection(
    callback_query: CallbackQuery,
    selection_store: LocationSelectionStore,
    nearby_places: NearbyPlacesUseCase,
    user_settings: UserSettingsStore,
) -> None:
    parsed = _parse_location_index_and_category(callback_query.data, "nearby:")
    user_id = user_id_of(callback_query)
    if parsed is None or user_id is None:
        await callback_query.answer(INVALID_SELECTION_MESSAGE)
        return

    index, category = parsed
    location = selection_store.get(user_id, index)
    if location is None:
        await callback_query.answer(INVALID_SELECTION_MESSAGE)
        return

    message = answerable_message(callback_query)
    if message is None:
        await callback_query.answer(EXPIRED_MESSAGE)
        return

    settings = user_settings.get(user_id)
    try:
        places = await nearby_places.execute(
            location.coordinates,
            category,
            radius_meters=settings.nearby_radius_meters,
            limit=settings.result_limit,
        )
    except httpx.HTTPError as error:
        report_service_error(error, "nearby places search")
        await message.answer(SERVICE_UNAVAILABLE_MESSAGE)
        await callback_query.answer()
        return

    await message.answer(format_nearby_places(category, places))
    await callback_query.answer()


@router.callback_query(F.data == "nearby_realtime:start")
async def handle_realtime_nearby_start(callback_query: CallbackQuery) -> None:
    message = answerable_message(callback_query)
    if message is None:
        await callback_query.answer(EXPIRED_MESSAGE)
        return

    await message.answer(
        "Qaysi kategoriya bo'yicha eng yaqin joylarni topay?",
        reply_markup=build_realtime_nearby_categories_keyboard(),
    )
    await callback_query.answer()


@router.callback_query(F.data.startswith("nearby_realtime:"))
async def handle_realtime_nearby_category_selection(
    callback_query: CallbackQuery,
    add_location_flow: AddLocationFlowStore,
) -> None:
    category = _parse_category_after_prefix(callback_query.data, "nearby_realtime:")
    user_id = user_id_of(callback_query)
    if category is None or user_id is None:
        await callback_query.answer(INVALID_SELECTION_MESSAGE)
        return

    message = answerable_message(callback_query)
    if message is None:
        await callback_query.answer(EXPIRED_MESSAGE)
        return

    add_location_flow.start_realtime_nearby(user_id, category)
    await message.answer(
        "Hozirgi lokatsiyangizni yuboring. "
        "Men kategoriya bo'yicha eng yaqin joylarni topib beraman."
    )
    await callback_query.answer()


def _parse_location_index(data: str | None) -> int | None:
    if data is None or not data.startswith("location:"):
        return None
    raw_index = data.removeprefix("location:")
    if not raw_index.isdigit():
        return None
    return int(raw_index)


def _parse_location_index_and_category(
    data: str | None,
    prefix: str,
) -> tuple[int, PlaceCategory] | None:
    if data is None or not data.startswith(prefix):
        return None

    raw_index, separator, raw_category = data.removeprefix(prefix).partition(":")
    if not separator or not raw_index.isdigit():
        return None

    try:
        category = PlaceCategory(raw_category)
    except ValueError:
        return None

    return int(raw_index), category


def _parse_category_after_prefix(data: str | None, prefix: str) -> PlaceCategory | None:
    if data is None or not data.startswith(prefix):
        return None

    try:
        return PlaceCategory(data.removeprefix(prefix))
    except ValueError:
        return None
