from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.application.use_cases.access import HasAddAccessUseCase
from app.presentation.telegram.access import is_admin
from app.presentation.telegram.errors import user_id_of
from app.presentation.telegram.formatters import format_start_message
from app.presentation.telegram.keyboards.menu import build_main_menu_keyboard

router = Router(name="start")


@router.message(CommandStart())
async def handle_start(
    message: Message,
    state: FSMContext,
    admin_ids: tuple[int, ...],
    has_add_access: HasAddAccessUseCase,
) -> None:
    await state.clear()
    await message.answer(
        format_start_message(),
        reply_markup=_menu(message, admin_ids, has_add_access),
    )


# The only /cancel handler. This router is included first and the filter carries
# no state, so it answers whatever flow the driver is in; a per-flow handler
# would sit behind both this one and its own flow's step handlers.
@router.message(Command("cancel"))
async def handle_cancel(
    message: Message,
    state: FSMContext,
    admin_ids: tuple[int, ...],
    has_add_access: HasAddAccessUseCase,
) -> None:
    await state.clear()
    await message.answer(
        "Jarayon bekor qilindi. Boshlang'ich menyuga qaytdingiz.",
        reply_markup=_menu(message, admin_ids, has_add_access),
    )


def _menu(
    message: Message,
    admin_ids: tuple[int, ...],
    has_add_access: HasAddAccessUseCase,
):
    """The menu as this driver gets to see it: the document button is drawn
    only for admins and the approved."""
    admin = is_admin(message, admin_ids)
    user_id = user_id_of(message)
    can_add = user_id is not None and has_add_access.execute(user_id)
    return build_main_menu_keyboard(is_admin=admin, can_add_documents=can_add)
