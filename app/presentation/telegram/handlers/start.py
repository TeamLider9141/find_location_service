from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.presentation.telegram.access import is_admin
from app.presentation.telegram.formatters import format_start_message
from app.presentation.telegram.keyboards.menu import build_main_menu_keyboard

router = Router(name="start")


@router.message(CommandStart())
async def handle_start(
    message: Message,
    state: FSMContext,
    admin_ids: tuple[int, ...],
) -> None:
    await state.clear()
    await message.answer(
        format_start_message(),
        reply_markup=build_main_menu_keyboard(is_admin=is_admin(message, admin_ids)),
    )


# The only /cancel handler. This router is included first and the filter carries
# no state, so it answers whatever flow the driver is in; a per-flow handler
# would sit behind both this one and its own flow's step handlers.
@router.message(Command("cancel"))
async def handle_cancel(
    message: Message,
    state: FSMContext,
    admin_ids: tuple[int, ...],
) -> None:
    await state.clear()
    await message.answer(
        "Jarayon bekor qilindi. Boshlang'ich menyuga qaytdingiz.",
        reply_markup=build_main_menu_keyboard(is_admin=is_admin(message, admin_ids)),
    )
