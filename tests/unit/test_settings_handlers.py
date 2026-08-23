from app.presentation.telegram.handlers.settings import (
    handle_settings,
    handle_settings_update,
)
from app.presentation.telegram.selection_store import InMemoryUserSettingsStore


class FakeUser:
    def __init__(self, user_id: int) -> None:
        self.id = user_id


class FakeMessage:
    def __init__(self, user_id: int = 42) -> None:
        self.from_user = FakeUser(user_id)
        self.answers: list[dict[str, object]] = []

    async def answer(self, text: str, **kwargs: object) -> None:
        self.answers.append({"text": text, **kwargs})


class FakeCallbackQuery:
    def __init__(self, data: str, user_id: int = 42) -> None:
        self.data = data
        self.from_user = FakeUser(user_id)
        self.message = FakeMessage(user_id=user_id)
        self.alerts: list[str | None] = []

    async def answer(self, text: str | None = None, **_: object) -> None:
        self.alerts.append(text)


async def test_settings_command_shows_default_radius_and_result_limit() -> None:
    store = InMemoryUserSettingsStore()
    message = FakeMessage()

    await handle_settings(message, user_settings=store)

    answer = message.answers[0]
    assert "10 km" in str(answer["text"])
    assert "10 ta" in str(answer["text"])
    callback_data = [row[0].callback_data for row in answer["reply_markup"].inline_keyboard]
    assert "settings:radius:inc" in callback_data
    assert "settings:limit:dec" in callback_data


async def test_settings_update_changes_radius_and_result_limit() -> None:
    store = InMemoryUserSettingsStore()

    await handle_settings_update(
        FakeCallbackQuery("settings:radius:inc"),
        user_settings=store,
    )
    callback = FakeCallbackQuery("settings:limit:dec")
    await handle_settings_update(callback, user_settings=store)

    settings = store.get(user_id=42)
    assert settings.nearby_radius_meters == 15_000
    assert settings.result_limit == 9
    assert "15 km" in str(callback.message.answers[0]["text"])
    assert "9 ta" in str(callback.message.answers[0]["text"])
    assert callback.alerts == [None]
