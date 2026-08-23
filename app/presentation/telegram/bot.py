from aiogram import Bot, Dispatcher

from app.application.use_cases.saved_places import (
    AddSavedPlaceUseCase,
    DeleteSavedPlaceUseCase,
    ListSavedPlacesUseCase,
    UpdateSavedPlaceCategoryUseCase,
)
from app.application.use_cases.nearby_places import NearbyPlacesUseCase
from app.application.use_cases.search_location import SearchLocationUseCase
from app.config.settings import Settings
from app.domain.interfaces.saved_places import SavedPlaceRepository
from app.infrastructure.database.sqlite_saved_places import SQLiteSavedPlaceRepository
from app.infrastructure.providers.osm.nominatim import NominatimGeocodingProvider
from app.infrastructure.providers.osm.overpass import OverpassPlacesProvider
from app.presentation.telegram.handlers import location, saved_places, search, start
from app.presentation.telegram.handlers import settings as settings_handlers
from app.presentation.telegram.selection_store import (
    InMemoryAddLocationFlowStore,
    InMemoryLocationSelectionStore,
    InMemoryUserSettingsStore,
)


def create_dispatcher(
    search_location: SearchLocationUseCase,
    nearby_places: NearbyPlacesUseCase | None = None,
    saved_places_repository: SavedPlaceRepository | None = None,
) -> Dispatcher:
    repository = saved_places_repository or SQLiteSavedPlaceRepository("data/find_location.sqlite3")
    nearby_places_use_case = nearby_places or NearbyPlacesUseCase(OverpassPlacesProvider())
    dispatcher = Dispatcher(
        search_location=search_location,
        nearby_places=nearby_places_use_case,
        selection_store=InMemoryLocationSelectionStore(),
        add_location_flow=InMemoryAddLocationFlowStore(),
        user_settings=InMemoryUserSettingsStore(),
        add_saved_place=AddSavedPlaceUseCase(repository),
        list_saved_places=ListSavedPlacesUseCase(repository),
        update_saved_place_category=UpdateSavedPlaceCategoryUseCase(repository),
        delete_saved_place=DeleteSavedPlaceUseCase(repository),
    )
    dispatcher.include_router(start.router)
    dispatcher.include_router(settings_handlers.router)
    dispatcher.include_router(saved_places.router)
    dispatcher.include_router(location.router)
    # search last: it owns the catch-all F.text handler
    dispatcher.include_router(search.router)
    return dispatcher


def create_bot(settings: Settings) -> Bot:
    if not settings.telegram_bot_token:
        raise ValueError("TELEGRAM_BOT_TOKEN is required")
    return Bot(token=settings.telegram_bot_token)


def create_geocoding_provider(settings: Settings) -> NominatimGeocodingProvider:
    return NominatimGeocodingProvider(
        base_url=settings.nominatim_base_url,
        user_agent=settings.nominatim_user_agent,
    )


def create_places_provider(settings: Settings) -> OverpassPlacesProvider:
    return OverpassPlacesProvider(
        base_url=settings.overpass_base_url,
        user_agent=settings.nominatim_user_agent,
    )


def create_saved_place_repository(settings: Settings) -> SavedPlaceRepository:
    return SQLiteSavedPlaceRepository(settings.database_path)
