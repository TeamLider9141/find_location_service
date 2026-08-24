import pytest

from app.domain.value_objects.user_settings import (
    MAX_RADIUS_METERS,
    MIN_RESULT_LIMIT,
    UserSettings,
)
from app.infrastructure.database.sqlite_user_settings import SQLiteUserSettingsStore
from app.presentation.telegram.selection_store import InMemoryUserSettingsStore

# Both stores answer the same protocol, and the handlers cannot tell them
# apart. One suite over both is what keeps them from drifting.
@pytest.fixture(params=["memory", "sqlite"])
def store(request, tmp_path):
    if request.param == "memory":
        return InMemoryUserSettingsStore()
    return SQLiteUserSettingsStore(tmp_path / "settings.sqlite3")


def test_a_driver_who_never_touched_settings_gets_the_defaults(store) -> None:
    assert store.get(42) == UserSettings()


def test_widening_a_narrowed_radius_is_remembered(store) -> None:
    store.decrease_radius(42)
    store.decrease_radius(42)

    store.increase_radius(42)

    assert store.get(42).nearby_radius_meters == 45_000


def test_narrowing_the_radius_is_remembered(store) -> None:
    store.decrease_radius(42)

    assert store.get(42).nearby_radius_meters == 45_000


def test_the_result_limit_moves_one_step_at_a_time(store) -> None:
    store.increase_result_limit(42)
    store.increase_result_limit(42)

    assert store.get(42).result_limit == 17


def test_the_bounds_hold_however_often_the_button_is_pressed(store) -> None:
    for _ in range(20):
        store.increase_radius(42)
        store.decrease_result_limit(42)

    settings = store.get(42)
    assert settings.nearby_radius_meters == MAX_RADIUS_METERS
    assert settings.result_limit == MIN_RESULT_LIMIT


def test_one_driver_does_not_change_another_driver_settings(store) -> None:
    store.increase_radius(1)

    assert store.get(2) == UserSettings()


def test_an_update_returns_what_it_stored(store) -> None:
    returned = store.increase_result_limit(42)

    assert returned == store.get(42)


def test_changing_one_setting_leaves_the_other_alone(store) -> None:
    store.increase_result_limit(42)
    store.increase_radius(42)

    settings = store.get(42)
    assert settings.result_limit == 16
    assert settings.nearby_radius_meters == MAX_RADIUS_METERS


def test_settings_outlive_the_process_that_stored_them(tmp_path) -> None:
    # The whole point of the SQLite store: a restart used to reset every driver
    # back to the defaults without telling them.
    database = tmp_path / "settings.sqlite3"
    SQLiteUserSettingsStore(database).decrease_radius(42)

    assert SQLiteUserSettingsStore(database).get(42).nearby_radius_meters == 45_000
