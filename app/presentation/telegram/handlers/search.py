from typing import Protocol

import httpx
from aiogram import F, Router
from aiogram.types import Message

from app.application.use_cases.search_location import SearchLocationUseCase
from app.domain.entities.location import Location
from app.domain.value_objects.user_settings import UserSettings
from app.presentation.telegram.errors import (
    SERVICE_UNAVAILABLE_MESSAGE,
    report_service_error,
    user_id_of,
)
from app.presentation.telegram.formatters import format_search_results
from app.presentation.telegram.keyboards.categories import build_add_category_keyboard
from app.presentation.telegram.keyboards.menu import ADD_LOCATION_BUTTON, SEARCH_LOCATION_BUTTON
from app.presentation.telegram.keyboards.locations import build_locations_keyboard
from app.presentation.telegram.location_input import parse_coordinates_from_text

router = Router(name="search")


class LocationSelectionStore(Protocol):
    def save(self, user_id: int, locations: list[Location]) -> None:
        """Persist the last search results for a Telegram user."""


class AddLocationFlowStore(Protocol):
    def start(self, user_id: int) -> None:
        """Start add-location flow for a user."""

    def start_search(self, user_id: int) -> None:
        """Start search-only flow for a user."""

    def stop(self, user_id: int) -> None:
        """Stop add-location flow for a user."""

    def is_waiting(self, user_id: int) -> bool:
        """Return whether next user text should be handled as a location input."""

    def is_add_mode(self, user_id: int) -> bool:
        """Return whether next input belongs to add-location flow."""


class UserSettingsStore(Protocol):
    def get(self, user_id: int) -> UserSettings:
        """Return current settings for a Telegram user."""


@router.message(F.text == SEARCH_LOCATION_BUTTON)
async def handle_search_location_menu(
    message: Message,
    add_location_flow: AddLocationFlowStore,
) -> None:
    user_id = user_id_of(message)
    if user_id is None:
        return

    add_location_flow.start_search(user_id)
    await message.answer(
        "Qidiriladigan manzil nomini yuboring.\n"
        "Bekor qilish uchun /cancel bosing.\n"
        "Masalan: Домодедово аэропорт"
    )


@router.message(F.text == ADD_LOCATION_BUTTON)
async def handle_add_location_menu(
    message: Message,
    add_location_flow: AddLocationFlowStore,
) -> None:
    user_id = user_id_of(message)
    if user_id is None:
        return

    add_location_flow.start(user_id)
    await message.answer(
        "Manzil nomi, xarita linki yoki Telegram location/venue yuboring.\n"
        "Bekor qilish uchun /cancel bosing.\n"
        "Masalan: Домодедово аэропорт"
    )


@router.message(F.text)
async def handle_location_query(
    message: Message,
    search_location: SearchLocationUseCase,
    selection_store: LocationSelectionStore,
    add_location_flow: AddLocationFlowStore,
    user_settings: UserSettingsStore,
) -> None:
    user_id = user_id_of(message)
    if user_id is None:
        return

    query = (message.text or "").strip()
    if not query:
        await message.answer("Manzil yoki joy nomini yuboring.")
        return

    if not add_location_flow.is_waiting(user_id):
        await message.answer("Manzil qidirish uchun avval knopka bosing.")
        return

    coordinates = (
        parse_coordinates_from_text(query) if add_location_flow.is_add_mode(user_id) else None
    )
    if coordinates is not None:
        location = Location(
            id=f"link:{user_id}",
            name="Linkdan yuborilgan lokatsiya",
            address=query,
            coordinates=coordinates,
            source="link",
            source_id=query[:128],
        )
        add_location_flow.stop(user_id)
        selection_store.save(user_id, [location])
        await message.answer(
            f"{location.name}\n\nKategoriya tanlang:",
            reply_markup=build_add_category_keyboard(location_index=0),
        )
        return

    try:
        locations = await search_location.execute(
            query,
            limit=user_settings.get(user_id).result_limit,
        )
    except (httpx.HTTPError, ValueError) as error:
        report_service_error(error, "location search")
        await message.answer(SERVICE_UNAVAILABLE_MESSAGE)
        return

    if not locations:
        await message.answer("Hech narsa topilmadi. Boshqa manzil bilan urinib ko'ring.")
        return

    add_location_flow.stop(user_id)
    selection_store.save(user_id, locations)
    await message.answer(
        format_search_results(locations),
        reply_markup=build_locations_keyboard(locations),
    )
