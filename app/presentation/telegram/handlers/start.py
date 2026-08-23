from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.presentation.telegram.formatters import format_start_message
from app.presentation.telegram.keyboards.menu import build_main_menu_keyboard

router = Router(name="start")


@router.message(CommandStart())
async def handle_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(format_start_message(), reply_markup=build_main_menu_keyboard())


# This router is included first, so /cancel is answered here whatever flow the
# driver is in — the per-flow cancel handlers never see it.
@router.message(Command("cancel"))
async def handle_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "Jarayon bekor qilindi. Boshlang'ich menyuga qaytdingiz.",
        reply_markup=build_main_menu_keyboard(),
    )
