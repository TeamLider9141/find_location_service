from typing import Protocol

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from app.presentation.telegram.formatters import format_start_message
from app.presentation.telegram.keyboards.menu import build_main_menu_keyboard

router = Router(name="start")


class LocationSelectionStore(Protocol):
    def clear(self, user_id: int) -> None:
        """Clear pending selectable locations for a Telegram user."""


class AddLocationFlowStore(Protocol):
    def stop(self, user_id: int) -> None:
        """Stop add-location flow for a Telegram user."""


@router.message(CommandStart())
async def handle_start(message: Message) -> None:
    await message.answer(format_start_message(), reply_markup=build_main_menu_keyboard())


@router.message(Command("cancel"))
async def handle_cancel(
    message: Message,
    selection_store: LocationSelectionStore,
    add_location_flow: AddLocationFlowStore,
) -> None:
    add_location_flow.stop(message.from_user.id)
    selection_store.clear(message.from_user.id)
    await message.answer(
        "Jarayon bekor qilindi. Boshlang'ich menyuga qaytdingiz.",
        reply_markup=build_main_menu_keyboard(),
    )
