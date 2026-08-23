import pytest
from aiogram import Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from app.config.settings import Settings
from app.infrastructure.repositories.in_memory_places import InMemoryPlaceRepository
from app.presentation.telegram.bot import create_bot, create_dispatcher

# The handler routers are module-level singletons, and aiogram refuses to attach
# one to a second dispatcher. So the whole file shares one dispatcher — which is
# also how the bot runs: built once at startup.
REPOSITORY = InMemoryPlaceRepository()


@pytest.fixture(scope="module")
def dispatcher() -> Dispatcher:
    return create_dispatcher(REPOSITORY)


def test_create_bot_requires_telegram_token() -> None:
    with pytest.raises(ValueError, match="TELEGRAM_BOT_TOKEN"):
        create_bot(Settings(telegram_bot_token=None))


def test_dispatcher_injects_every_place_dependency(dispatcher: Dispatcher) -> None:
    for key in (
        "add_place",
        "find_places",
        "nearby_places",
        "get_place",
        "list_my_places",
        "update_place",
        "delete_place",
        "user_settings",
    ):
        assert key in dispatcher.workflow_data


def test_every_use_case_reads_the_repository_it_was_given(
    dispatcher: Dispatcher,
) -> None:
    # One repository behind all of them: a place added through the bot has to be
    # findable through the same bot, which fails silently if two use cases end
    # up holding different repositories.
    for key in (
        "add_place",
        "find_places",
        "nearby_places",
        "get_place",
        "list_my_places",
        "update_place",
        "delete_place",
    ):
        assert dispatcher.workflow_data[key]._repository is REPOSITORY


def test_find_place_router_is_registered_last(dispatcher: Dispatcher) -> None:
    names = [router.name for router in dispatcher.sub_routers]

    assert names[-1] == "find_place"
    assert names == ["start", "settings", "add_place", "my_places", "find_place"]


def test_dispatcher_keeps_state_for_the_add_place_wizard(
    dispatcher: Dispatcher,
) -> None:
    # The add-place flow spans five messages, so a dispatcher without storage
    # would lose the name before the coordinates ever arrived.
    assert isinstance(dispatcher.storage, MemoryStorage)
