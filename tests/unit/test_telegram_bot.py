import pytest

from app.config.settings import Settings
from app.presentation.telegram.bot import create_bot, create_dispatcher


class DummySearchLocationUseCase:
    pass


class DummyNearbyPlacesUseCase:
    pass


def test_create_bot_requires_telegram_token() -> None:
    with pytest.raises(ValueError, match="TELEGRAM_BOT_TOKEN"):
        create_bot(Settings(telegram_bot_token=None))


def test_create_dispatcher_wires_search_use_case_dependency() -> None:
    search_location = DummySearchLocationUseCase()
    nearby_places = DummyNearbyPlacesUseCase()

    dispatcher = create_dispatcher(search_location, nearby_places=nearby_places)

    assert dispatcher.workflow_data["search_location"] is search_location
    assert dispatcher.workflow_data["nearby_places"] is nearby_places
    assert "selection_store" in dispatcher.workflow_data
    assert "user_settings" in dispatcher.workflow_data
