from aiogram import Bot, Dispatcher

from app.application.use_cases.admin import (
    DeletePlaceAsAdminUseCase,
    GetAdminOverviewUseCase,
    GetUserDetailUseCase,
    ListBroadcastRecipientsUseCase,
    ListUsersPageUseCase,
    RecordSearchUseCase,
    RecordUserVisitUseCase,
    TopSearchesUseCase,
)
from app.application.use_cases.places import (
    AddPlaceUseCase,
    DeletePlaceUseCase,
    FindPlacesUseCase,
    GetPlaceUseCase,
    ListMyPlacesUseCase,
    NearbyPlacesUseCase,
    UpdatePlaceUseCase,
)
from app.config.settings import Settings
from app.domain.interfaces.places import PlaceRepository
from app.domain.interfaces.users import UserRepository
from app.infrastructure.database.sqlite_places import SQLitePlaceRepository
from app.infrastructure.database.sqlite_users import SQLiteUserRepository
from app.presentation.telegram.handlers import add_place, admin, find_place, my_places, start
from app.presentation.telegram.handlers import settings as settings_handlers
from app.presentation.telegram.middlewares.user_tracking import UserTrackingMiddleware
from app.presentation.telegram.selection_store import InMemoryUserSettingsStore


def create_dispatcher(
    repository: PlaceRepository,
    users: UserRepository,
    admin_ids: tuple[int, ...] = (),
) -> Dispatcher:
    dispatcher = Dispatcher(
        add_place=AddPlaceUseCase(repository),
        find_places=FindPlacesUseCase(repository),
        nearby_places=NearbyPlacesUseCase(repository),
        get_place=GetPlaceUseCase(repository),
        list_my_places=ListMyPlacesUseCase(repository),
        update_place=UpdatePlaceUseCase(repository),
        delete_place=DeletePlaceUseCase(repository),
        user_settings=InMemoryUserSettingsStore(),
        record_search=RecordSearchUseCase(users),
        admin_overview=GetAdminOverviewUseCase(repository, users),
        list_users_page=ListUsersPageUseCase(users, repository),
        user_detail=GetUserDetailUseCase(users, repository),
        top_searches=TopSearchesUseCase(users),
        delete_place_as_admin=DeletePlaceAsAdminUseCase(repository),
        broadcast_recipients=ListBroadcastRecipientsUseCase(users),
        admin_ids=admin_ids,
    )

    # Outer middleware, on both update types: a driver who only taps buttons
    # still has to show up in the admin panel.
    tracking = UserTrackingMiddleware(RecordUserVisitUseCase(users))
    dispatcher.message.outer_middleware(tracking)
    dispatcher.callback_query.outer_middleware(tracking)

    dispatcher.include_router(start.router)
    dispatcher.include_router(admin.router)
    dispatcher.include_router(settings_handlers.router)
    dispatcher.include_router(add_place.router)
    dispatcher.include_router(my_places.router)
    # find_place last: it owns the bare-text catch-all handler.
    dispatcher.include_router(find_place.router)
    return dispatcher


def create_bot(settings: Settings) -> Bot:
    if not settings.telegram_bot_token:
        raise ValueError("TELEGRAM_BOT_TOKEN is required")
    return Bot(token=settings.telegram_bot_token)


def create_place_repository(settings: Settings) -> PlaceRepository:
    return SQLitePlaceRepository(settings.database_path)


def create_user_repository(settings: Settings) -> UserRepository:
    # Same file as the places: one database to back up, one to copy to a server.
    return SQLiteUserRepository(settings.database_path)
