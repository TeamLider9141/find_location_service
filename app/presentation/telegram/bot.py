from aiogram import Bot, Dispatcher

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
from app.infrastructure.database.sqlite_places import SQLitePlaceRepository
from app.presentation.telegram.handlers import add_place, find_place, my_places, start
from app.presentation.telegram.handlers import settings as settings_handlers
from app.presentation.telegram.selection_store import InMemoryUserSettingsStore


def create_dispatcher(repository: PlaceRepository) -> Dispatcher:
    dispatcher = Dispatcher(
        add_place=AddPlaceUseCase(repository),
        find_places=FindPlacesUseCase(repository),
        nearby_places=NearbyPlacesUseCase(repository),
        get_place=GetPlaceUseCase(repository),
        list_my_places=ListMyPlacesUseCase(repository),
        update_place=UpdatePlaceUseCase(repository),
        delete_place=DeletePlaceUseCase(repository),
        user_settings=InMemoryUserSettingsStore(),
    )
    dispatcher.include_router(start.router)
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
