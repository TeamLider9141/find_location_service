from aiogram import Bot, Dispatcher

from app.application.use_cases.admin import (
    AdminPlacesByCategoryUseCase,
    DeletePlaceAsAdminUseCase,
    GetAdminOverviewUseCase,
    GetUserDetailUseCase,
    ListBroadcastRecipientsUseCase,
    ListDeletionsUseCase,
    ListUsersPageUseCase,
    RecordSearchUseCase,
    RecordUserVisitUseCase,
    TopSearchesUseCase,
)
from app.application.use_cases.places import (
    AddPlaceUseCase,
    CountPlacesByCategoryUseCase,
    DeletePlaceUseCase,
    FindPlacesUseCase,
    GetPlaceUseCase,
    ListMyPlacesUseCase,
    NearbyPlacesUseCase,
    UpdatePlaceUseCase,
)
from app.application.use_cases.access import (
    DecideAddAccessUseCase,
    RequestAddAccessUseCase,
    RevokeAddAccessUseCase,
)
from app.config.settings import Settings
from app.domain.interfaces.add_access import AddAccessRepository
from app.domain.interfaces.deletions import DeletionLog
from app.domain.interfaces.places import PlaceRepository
from app.domain.interfaces.routing import RoadRouter
from app.domain.interfaces.users import UserRepository
from app.domain.interfaces.maps import OverviewMapRenderer
from app.infrastructure.location_links import HttpLinkResolver
from app.infrastructure.maps.google_static import GoogleStaticMapRenderer
from app.infrastructure.routing.chain import FirstAnsweringRouter
from app.infrastructure.routing.google_routes import GoogleRoutesRouter
from app.infrastructure.routing.osrm import OsrmRouter
from app.infrastructure.database.sqlite_add_access import SQLiteAddAccessRepository
from app.infrastructure.database.sqlite_deletions import SQLiteDeletionLog
from app.infrastructure.database.sqlite_places import SQLitePlaceRepository
from app.infrastructure.database.sqlite_user_settings import SQLiteUserSettingsStore
from app.infrastructure.database.sqlite_users import SQLiteUserRepository
from app.presentation.telegram.handlers import add_place, admin, find_place, my_places, start
from app.presentation.telegram.handlers import settings as settings_handlers
from app.presentation.telegram.handlers.settings import UserSettingsStore
from app.presentation.telegram.middlewares.throttling import ThrottleMiddleware
from app.presentation.telegram.middlewares.user_tracking import UserTrackingMiddleware


def create_dispatcher(
    repository: PlaceRepository,
    users: UserRepository,
    user_settings: UserSettingsStore,
    throttle: ThrottleMiddleware,
    add_access: AddAccessRepository,
    deletions: DeletionLog,
    admin_ids: tuple[int, ...] = (),
    super_admin_ids: tuple[int, ...] = (),
    road_router: RoadRouter | None = None,
    overview_map: OverviewMapRenderer | None = None,
) -> Dispatcher:
    # Supers are admins too: one variable answers "may they open the panel",
    # the other answers "may they delete and broadcast".
    all_admins = tuple(dict.fromkeys((*admin_ids, *super_admin_ids)))
    dispatcher = Dispatcher(
        add_place=AddPlaceUseCase(repository),
        find_places=FindPlacesUseCase(repository),
        nearby_places=NearbyPlacesUseCase(repository),
        get_place=GetPlaceUseCase(repository),
        list_my_places=ListMyPlacesUseCase(repository),
        update_place=UpdatePlaceUseCase(repository),
        delete_place=DeletePlaceUseCase(repository, deletions),
        user_settings=user_settings,
        record_search=RecordSearchUseCase(users),
        admin_overview=GetAdminOverviewUseCase(repository, users),
        list_users_page=ListUsersPageUseCase(users, repository, add_access),
        user_detail=GetUserDetailUseCase(users, repository),
        top_searches=TopSearchesUseCase(users),
        delete_place_as_admin=DeletePlaceAsAdminUseCase(repository, deletions),
        list_deletions=ListDeletionsUseCase(deletions, users),
        broadcast_recipients=ListBroadcastRecipientsUseCase(users),
        count_places_by_category=CountPlacesByCategoryUseCase(repository),
        admin_places_by_category=AdminPlacesByCategoryUseCase(repository, users),
        request_add_access=RequestAddAccessUseCase(add_access),
        decide_add_access=DecideAddAccessUseCase(add_access),
        revoke_add_access=RevokeAddAccessUseCase(add_access),
        admin_ids=all_admins,
        super_admin_ids=super_admin_ids,
        road_router=road_router,
        link_resolver=HttpLinkResolver(),
        overview_map=overview_map,
    )

    # Throttling goes on first, so a flood is dropped before it reaches the
    # database at all — including the tracking write below it.
    dispatcher.message.outer_middleware(throttle)

    # Outer middleware, on both update types: a driver who only taps buttons
    # still has to show up in the admin panel.
    tracking = UserTrackingMiddleware(RecordUserVisitUseCase(users), admin_ids=all_admins)
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


def create_add_access_repository(settings: Settings) -> AddAccessRepository:
    # Same file again: a permission granted before a deploy must survive it.
    return SQLiteAddAccessRepository(settings.database_path)


def create_road_router(settings: Settings) -> RoadRouter | None:
    # Preference order: Google's map first when a key is configured, OSRM
    # after it. None — not a dead router — when both are switched off, so the
    # nearby handler shows no wait notice for a call that will never be made.
    routers: list[RoadRouter] = []
    if settings.google_maps_api_key:
        routers.append(GoogleRoutesRouter(settings.google_maps_api_key))
    if settings.osrm_base_url:
        routers.append(OsrmRouter(settings.osrm_base_url))

    if not routers:
        return None
    if len(routers) == 1:
        return routers[0]
    return FirstAnsweringRouter(tuple(routers))


def create_overview_map(settings: Settings) -> OverviewMapRenderer | None:
    # The sketch needs the Maps Static API enabled on the same key; when the
    # key is absent the prompt simply goes out without a picture.
    if not settings.google_maps_api_key:
        return None
    return GoogleStaticMapRenderer(settings.google_maps_api_key)


def create_deletion_log(settings: Settings) -> DeletionLog:
    # Same file again: the journal answers "who deleted what" long after the
    # fact, so it has to outlive every restart.
    return SQLiteDeletionLog(settings.database_path)


def create_throttle_middleware(settings: Settings) -> ThrottleMiddleware:
    return ThrottleMiddleware(
        burst=settings.throttle_burst,
        refill_per_second=settings.throttle_refill_per_second,
        warning_seconds=settings.throttle_warning_seconds,
        idle_seconds=settings.throttle_idle_seconds,
        prune_interval_seconds=settings.throttle_prune_interval_seconds,
    )


def create_user_settings_store(settings: Settings) -> UserSettingsStore:
    # Same file again. A driver who widened their radius expects it to still be
    # wide after a deploy, not back at the default nobody chose.
    return SQLiteUserSettingsStore(settings.database_path)


def create_user_repository(settings: Settings) -> UserRepository:
    # Same file as the places: one database to back up, one to copy to a server.
    return SQLiteUserRepository(settings.database_path)
