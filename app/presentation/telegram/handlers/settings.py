from typing import Callable, Protocol

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from app.domain.value_objects.user_settings import UserSettings
from app.presentation.telegram.errors import EXPIRED_MESSAGE, answerable_message, user_id_of
from app.presentation.telegram.formatters import format_user_settings
from app.presentation.telegram.keyboards.menu import SETTINGS_BUTTON
from app.presentation.telegram.keyboards.settings import build_settings_keyboard

router = Router(name="settings")

INVALID_SELECTION_MESSAGE = "Tanlov eskirgan. Qayta urinib ko'ring."


class UserSettingsStore(Protocol):
    def get(self, user_id: int) -> UserSettings:
        """Return current settings for a Telegram user."""

    def increase_radius(self, user_id: int) -> UserSettings:
        """Widen the nearby search radius by one step."""

    def decrease_radius(self, user_id: int) -> UserSettings:
        """Narrow the nearby search radius by one step."""

    def increase_result_limit(self, user_id: int) -> UserSettings:
        """Show one more result."""

    def decrease_result_limit(self, user_id: int) -> UserSettings:
        """Show one less result."""


_UPDATES: dict[str, Callable[[UserSettingsStore, int], UserSettings]] = {
    "radius:inc": lambda store, user_id: store.increase_radius(user_id),
    "radius:dec": lambda store, user_id: store.decrease_radius(user_id),
    "limit:inc": lambda store, user_id: store.increase_result_limit(user_id),
    "limit:dec": lambda store, user_id: store.decrease_result_limit(user_id),
}


@router.message(Command("settings"))
@router.message(F.text == SETTINGS_BUTTON)
async def handle_settings(message: Message, user_settings: UserSettingsStore) -> None:
    user_id = user_id_of(message)
    if user_id is None:
        return

    await message.answer(
        format_user_settings(user_settings.get(user_id)),
        reply_markup=build_settings_keyboard(),
    )


@router.callback_query(F.data.startswith("settings:"))
async def handle_settings_update(
    callback_query: CallbackQuery,
    user_settings: UserSettingsStore,
) -> None:
    update = _parse_update(callback_query.data)
    user_id = user_id_of(callback_query)
    if update is None or user_id is None:
        await callback_query.answer(INVALID_SELECTION_MESSAGE)
        return

    message = answerable_message(callback_query)
    if message is None:
        await callback_query.answer(EXPIRED_MESSAGE)
        return

    settings = update(user_settings, user_id)
    await message.answer(
        format_user_settings(settings),
        reply_markup=build_settings_keyboard(),
    )
    await callback_query.answer()


def _parse_update(
    data: str | None,
) -> Callable[[UserSettingsStore, int], UserSettings] | None:
    if data is None or not data.startswith("settings:"):
        return None
    return _UPDATES.get(data.removeprefix("settings:"))
