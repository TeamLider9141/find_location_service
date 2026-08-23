from typing import Protocol

from aiogram import F, Router
import httpx
from aiogram.types import CallbackQuery, Message

from app.application.use_cases.saved_places import (
    AddSavedPlaceUseCase,
    DeleteSavedPlaceUseCase,
    ListSavedPlacesUseCase,
    UpdateSavedPlaceCategoryUseCase,
)
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
from app.presentation.telegram.formatters import format_nearby_places, format_saved_place
from app.presentation.telegram.keyboards.categories import (
    build_add_category_keyboard,
    build_delete_confirmation_keyboard,
    build_save_confirmation_keyboard,
    build_saved_place_actions_keyboard,
    build_update_category_keyboard,
    category_label,
)
from app.presentation.telegram.keyboards.menu import SAVED_LOCATIONS_BUTTON
from app.presentation.telegram.keyboards.saved_places import build_saved_places_keyboard
from app.presentation.telegram.keyboards.saved_places import build_saved_place_categories_keyboard

router = Router(name="saved_places")

INVALID_SELECTION_MESSAGE = "Tanlov eskirgan. Qayta qidirib ko'ring."


class LocationSelectionStore(Protocol):
    def save(self, user_id: int, locations: list[Location]) -> None:
        """Persist current selectable locations for a Telegram user."""

    def get(self, user_id: int, index: int) -> Location | None:
        """Return a previously selected location."""


class AddLocationFlowStore(Protocol):
    def stop(self, user_id: int) -> None:
        """Stop add-location flow for a user."""

    def is_waiting(self, user_id: int) -> bool:
        """Return whether incoming location/venue belongs to add-location flow."""

    def is_add_mode(self, user_id: int) -> bool:
        """Return whether incoming location/venue can be added directly."""

    def is_realtime_nearby_mode(self, user_id: int) -> bool:
        """Return whether incoming location belongs to realtime nearby flow."""

    def get_realtime_nearby_category(self, user_id: int) -> PlaceCategory | None:
        """Return selected realtime nearby category."""


class NearbyPlacesUseCase(Protocol):
    async def execute(
        self,
        coordinates: Coordinates,
        category: PlaceCategory,
        radius_meters: int = 3000,
        limit: int = 10,
    ) -> list[Place]:
        """Return nearby places for coordinates and category."""


class UserSettingsStore(Protocol):
    def get(self, user_id: int) -> UserSettings:
        """Return current settings for a Telegram user."""


@router.message(F.venue)
async def handle_venue_message(
    message: Message,
    selection_store: LocationSelectionStore,
    add_location_flow: AddLocationFlowStore,
) -> None:
    user_id = user_id_of(message)
    if user_id is None:
        return

    if not add_location_flow.is_add_mode(user_id):
        await message.answer(
            "Lokatsiya qo'shish uchun avval Manzil qo'shish knopkasini bosing."
        )
        return

    venue = message.venue
    location = Location(
        id=f"telegram:venue:{user_id}",
        name=venue.title,
        address=venue.address,
        coordinates=Coordinates(
            latitude=venue.location.latitude,
            longitude=venue.location.longitude,
        ),
        source="telegram",
        source_id=venue.foursquare_id or venue.google_place_id or f"venue:{user_id}",
    )
    add_location_flow.stop(user_id)
    selection_store.save(user_id, [location])
    await message.answer(
        f"{location.name}\n\nKategoriya tanlang:",
        reply_markup=build_add_category_keyboard(location_index=0),
    )


@router.message(F.location)
async def handle_location_message(
    message: Message,
    selection_store: LocationSelectionStore,
    add_location_flow: AddLocationFlowStore,
    nearby_places: NearbyPlacesUseCase | None = None,
    user_settings: UserSettingsStore | None = None,
) -> None:
    user_id = user_id_of(message)
    if user_id is None:
        return

    if add_location_flow.is_realtime_nearby_mode(user_id):
        category = add_location_flow.get_realtime_nearby_category(user_id)
        if category is None or nearby_places is None or user_settings is None:
            await message.answer("Tanlov eskirgan. Qayta urinib ko'ring.")
            add_location_flow.stop(user_id)
            return

        shared_location = message.location
        coordinates = Coordinates(
            latitude=shared_location.latitude,
            longitude=shared_location.longitude,
        )
        settings = user_settings.get(user_id)
        add_location_flow.stop(user_id)
        try:
            places = await nearby_places.execute(
                coordinates,
                category,
                radius_meters=settings.nearby_radius_meters,
                limit=settings.result_limit,
            )
        except httpx.HTTPError as error:
            report_service_error(error, "realtime nearby places search")
            await message.answer(SERVICE_UNAVAILABLE_MESSAGE)
            return

        await message.answer(format_nearby_places(category, places))
        return

    if not add_location_flow.is_add_mode(user_id):
        await message.answer(
            "Lokatsiya qo'shish uchun avval Manzil qo'shish knopkasini bosing."
        )
        return

    shared_location = message.location
    location = Location(
        id=f"telegram:location:{user_id}",
        name="Telegram lokatsiya",
        address="Telegramdan yuborilgan lokatsiya",
        coordinates=Coordinates(
            latitude=shared_location.latitude,
            longitude=shared_location.longitude,
        ),
        source="telegram",
        source_id=f"location:{user_id}:{shared_location.latitude},{shared_location.longitude}",
    )
    add_location_flow.stop(user_id)
    selection_store.save(user_id, [location])
    await message.answer(
        f"{location.name}\n\nKategoriya tanlang:",
        reply_markup=build_add_category_keyboard(location_index=0),
    )


@router.message(F.text == SAVED_LOCATIONS_BUTTON)
async def handle_list_saved_places(
    message: Message,
    list_saved_places: ListSavedPlacesUseCase,
) -> None:
    user_id = user_id_of(message)
    if user_id is None:
        return

    saved_places = list_saved_places.execute(user_id=user_id)

    await message.answer(
        "Kategoriya tanlang:",
        reply_markup=build_saved_place_categories_keyboard(saved_places),
    )


@router.callback_query(F.data.startswith("saved_filter:"))
async def handle_filter_saved_places_by_category(
    callback_query: CallbackQuery,
    list_saved_places: ListSavedPlacesUseCase,
) -> None:
    category = _parse_category_after_prefix(callback_query.data, "saved_filter:")
    user_id = user_id_of(callback_query)
    if category is None or user_id is None:
        await callback_query.answer(INVALID_SELECTION_MESSAGE)
        return

    message = answerable_message(callback_query)
    if message is None:
        await callback_query.answer(EXPIRED_MESSAGE)
        return

    saved_places = [
        saved_place
        for saved_place in list_saved_places.execute(user_id=user_id)
        if saved_place.category == category
    ]
    if not saved_places:
        await message.answer(f"{category_label(category)} kategoriyasi bo'sh.")
        await callback_query.answer()
        return

    await message.answer(
        f"{category_label(category)}:",
        reply_markup=build_saved_places_keyboard(saved_places),
    )
    await callback_query.answer()


@router.callback_query(F.data.startswith("saved_view:"))
async def handle_view_saved_place(
    callback_query: CallbackQuery,
    list_saved_places: ListSavedPlacesUseCase,
) -> None:
    saved_place_id = _parse_int_after_prefix(callback_query.data, "saved_view:")
    user_id = user_id_of(callback_query)
    if saved_place_id is None or user_id is None:
        await callback_query.answer(INVALID_SELECTION_MESSAGE)
        return

    saved_place = next(
        (
            place
            for place in list_saved_places.execute(user_id=user_id)
            if place.id == saved_place_id
        ),
        None,
    )
    if saved_place is None:
        await callback_query.answer(INVALID_SELECTION_MESSAGE)
        return

    message = answerable_message(callback_query)
    if message is None:
        await callback_query.answer(EXPIRED_MESSAGE)
        return

    await message.answer(
        format_saved_place(saved_place),
        reply_markup=build_saved_place_actions_keyboard(saved_place.id),
    )
    await callback_query.answer()


@router.callback_query(F.data.startswith("add_location:"))
async def handle_add_location_request(
    callback_query: CallbackQuery,
    selection_store: LocationSelectionStore,
) -> None:
    index = _parse_int_after_prefix(callback_query.data, "add_location:")
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
        f"{location.name}\n\nKategoriya tanlang:",
        reply_markup=build_add_category_keyboard(index),
    )
    await callback_query.answer()


@router.callback_query(F.data.startswith("add_category:"))
async def handle_add_category_selection(
    callback_query: CallbackQuery,
    selection_store: LocationSelectionStore,
) -> None:
    parsed = _parse_index_and_category(callback_query.data, "add_category:")
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

    await message.answer(
        (
            f"{location.name}\n"
            f"Kategoriya: {category_label(category)}\n\n"
            "Shu kategoriyaga saqlashni tasdiqlaysizmi?"
        ),
        reply_markup=build_save_confirmation_keyboard(index, category),
    )
    await callback_query.answer()


@router.callback_query(F.data.startswith("confirm_save:"))
async def handle_confirm_save_place(
    callback_query: CallbackQuery,
    selection_store: LocationSelectionStore,
    add_saved_place: AddSavedPlaceUseCase,
) -> None:
    parsed = _parse_index_and_category(callback_query.data, "confirm_save:")
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

    saved_place = add_saved_place.execute(
        user_id=user_id,
        location=location,
        category=category,
    )
    await message.answer(
        f"Saqlandi: {saved_place.name}\nKategoriya: {category_label(saved_place.category)}",
        reply_markup=build_saved_place_actions_keyboard(saved_place.id),
    )
    await callback_query.answer()


@router.callback_query(F.data.startswith("saved_category:"))
async def handle_saved_place_category_request(callback_query: CallbackQuery) -> None:
    saved_place_id = _parse_int_after_prefix(callback_query.data, "saved_category:")
    if saved_place_id is None:
        await callback_query.answer(INVALID_SELECTION_MESSAGE)
        return

    message = answerable_message(callback_query)
    if message is None:
        await callback_query.answer(EXPIRED_MESSAGE)
        return

    await message.answer(
        "Yangi kategoriya tanlang:",
        reply_markup=build_update_category_keyboard(saved_place_id),
    )
    await callback_query.answer()


@router.callback_query(F.data.startswith("update_category:"))
async def handle_update_category_selection(
    callback_query: CallbackQuery,
    update_saved_place_category: UpdateSavedPlaceCategoryUseCase,
) -> None:
    parsed = _parse_index_and_category(callback_query.data, "update_category:")
    user_id = user_id_of(callback_query)
    if parsed is None or user_id is None:
        await callback_query.answer(INVALID_SELECTION_MESSAGE)
        return

    message = answerable_message(callback_query)
    if message is None:
        await callback_query.answer(EXPIRED_MESSAGE)
        return

    saved_place_id, category = parsed
    saved_place = update_saved_place_category.execute(
        user_id=user_id,
        saved_place_id=saved_place_id,
        category=category,
    )
    if saved_place is None:
        await callback_query.answer(INVALID_SELECTION_MESSAGE)
        return

    await message.answer(
        f"Kategoriya o'zgartirildi: {category_label(saved_place.category)}",
        reply_markup=build_saved_place_actions_keyboard(saved_place.id),
    )
    await callback_query.answer()


@router.callback_query(F.data.startswith("saved_delete:"))
async def handle_saved_place_delete_request(callback_query: CallbackQuery) -> None:
    saved_place_id = _parse_int_after_prefix(callback_query.data, "saved_delete:")
    if saved_place_id is None:
        await callback_query.answer(INVALID_SELECTION_MESSAGE)
        return

    message = answerable_message(callback_query)
    if message is None:
        await callback_query.answer(EXPIRED_MESSAGE)
        return

    await message.answer(
        "Bu manzilni o'chirishni tasdiqlaysizmi?",
        reply_markup=build_delete_confirmation_keyboard(saved_place_id),
    )
    await callback_query.answer()


@router.callback_query(F.data.startswith("confirm_delete:"))
async def handle_confirm_delete_saved_place(
    callback_query: CallbackQuery,
    delete_saved_place: DeleteSavedPlaceUseCase,
) -> None:
    saved_place_id = _parse_int_after_prefix(callback_query.data, "confirm_delete:")
    user_id = user_id_of(callback_query)
    if saved_place_id is None or user_id is None:
        await callback_query.answer(INVALID_SELECTION_MESSAGE)
        return

    message = answerable_message(callback_query)
    if message is None:
        await callback_query.answer(EXPIRED_MESSAGE)
        return

    deleted = delete_saved_place.execute(
        user_id=user_id,
        saved_place_id=saved_place_id,
    )
    if not deleted:
        await callback_query.answer(INVALID_SELECTION_MESSAGE)
        return

    await message.answer("Manzil o'chirildi.")
    await callback_query.answer()


@router.callback_query(F.data == "cancel_save")
async def handle_cancel_save(callback_query: CallbackQuery) -> None:
    await _answer_cancelled(callback_query, "Saqlash bekor qilindi.")


@router.callback_query(F.data == "cancel_delete")
async def handle_cancel_delete(callback_query: CallbackQuery) -> None:
    await _answer_cancelled(callback_query, "O'chirish bekor qilindi.")


async def _answer_cancelled(callback_query: CallbackQuery, text: str) -> None:
    message = answerable_message(callback_query)
    if message is not None:
        await message.answer(text)
    await callback_query.answer()


def _parse_int_after_prefix(data: str | None, prefix: str) -> int | None:
    if data is None or not data.startswith(prefix):
        return None
    raw_value = data.removeprefix(prefix)
    if not raw_value.isdigit():
        return None
    return int(raw_value)


def _parse_index_and_category(data: str | None, prefix: str) -> tuple[int, PlaceCategory] | None:
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
