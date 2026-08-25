import pytest
from aiogram import Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from app.config.settings import Settings
from app.infrastructure.repositories.in_memory_add_access import InMemoryAddAccessRepository
from app.infrastructure.repositories.in_memory_deletions import InMemoryDeletionLog
from app.infrastructure.repositories.in_memory_places import InMemoryPlaceRepository
from app.infrastructure.repositories.in_memory_users import InMemoryUserRepository
from app.presentation.telegram.bot import create_bot, create_dispatcher
from app.presentation.telegram.middlewares.throttling import ThrottleMiddleware
from app.presentation.telegram.selection_store import InMemoryUserSettingsStore

# The handler routers are module-level singletons, and aiogram refuses to attach
# one to a second dispatcher. So the whole file shares one dispatcher — which is
# also how the bot runs: built once at startup.
REPOSITORY = InMemoryPlaceRepository()
USERS = InMemoryUserRepository()
SETTINGS = InMemoryUserSettingsStore()
ACCESS = InMemoryAddAccessRepository()
DELETIONS = InMemoryDeletionLog()
ADMIN_IDS = (99,)
SUPER_ADMIN_IDS = (98,)


@pytest.fixture(scope="module")
def dispatcher() -> Dispatcher:
    return create_dispatcher(
        REPOSITORY,
        users=USERS,
        user_settings=SETTINGS,
        throttle=ThrottleMiddleware(),
        add_access=ACCESS,
        deletions=DELETIONS,
        admin_ids=ADMIN_IDS,
        super_admin_ids=SUPER_ADMIN_IDS,
    )


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
        "record_search",
        "admin_overview",
        "list_users_page",
        "user_detail",
        "top_searches",
        "delete_place_as_admin",
        "broadcast_recipients",
        "request_add_access",
        "decide_add_access",
        "revoke_add_access",
        "list_deletions",
        "link_resolver",
        "admin_ids",
        "super_admin_ids",
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
    assert names == ["start", "admin", "settings", "add_place", "my_places", "find_place"]


def test_dispatcher_keeps_state_for_the_add_place_wizard(
    dispatcher: Dispatcher,
) -> None:
    # The add-place flow spans five messages, so a dispatcher without storage
    # would lose the name before the coordinates ever arrived.
    assert isinstance(dispatcher.storage, MemoryStorage)


def test_admin_ids_reach_the_handlers_that_guard_on_them(
    dispatcher: Dispatcher,
) -> None:
    # Supers are admins too: the panel check reads one combined tuple, the
    # super-only check reads its own.
    assert dispatcher.workflow_data["admin_ids"] == ADMIN_IDS + SUPER_ADMIN_IDS
    assert dispatcher.workflow_data["super_admin_ids"] == SUPER_ADMIN_IDS


def test_every_visitor_is_recorded_before_a_handler_runs(
    dispatcher: Dispatcher,
) -> None:
    # Tracking has to sit on both update types: a driver who only ever taps
    # buttons would otherwise never appear in the admin panel.
    for observer in (dispatcher.message, dispatcher.callback_query):
        names = [type(middleware).__name__ for middleware in observer.outer_middleware]
        assert "UserTrackingMiddleware" in names


def test_a_flood_is_stopped_before_it_reaches_the_database(dispatcher: Dispatcher) -> None:
    # Order is the point: throttling has to run before the tracking write, or a
    # dropped message still costs a database round trip.
    names = [type(middleware).__name__ for middleware in dispatcher.message.outer_middleware]

    assert names.index("ThrottleMiddleware") < names.index("UserTrackingMiddleware")


def test_the_settings_store_survives_a_restart(dispatcher: Dispatcher) -> None:
    # Handed in rather than built inside: an in-memory store would silently
    # reset every driver's radius on each deploy.
    assert dispatcher.workflow_data["user_settings"] is SETTINGS


def test_the_routing_chain_matches_what_is_configured() -> None:
    from app.infrastructure.routing.chain import FirstAnsweringRouter
    from app.infrastructure.routing.google_routes import GoogleRoutesRouter
    from app.infrastructure.routing.osrm import OsrmRouter
    from app.presentation.telegram.bot import create_road_router

    nothing = Settings(osrm_base_url="", google_maps_api_key="")
    osrm_only = Settings(osrm_base_url="https://osrm.example", google_maps_api_key="")
    both = Settings(osrm_base_url="https://osrm.example", google_maps_api_key="key")

    assert create_road_router(nothing) is None
    assert isinstance(create_road_router(osrm_only), OsrmRouter)
    assert isinstance(create_road_router(both), FirstAnsweringRouter)
    # Preference order: the better map first, the free fallback after it.
    chained = create_road_router(both)
    assert isinstance(chained._routers[0], GoogleRoutesRouter)
    assert isinstance(chained._routers[1], OsrmRouter)
