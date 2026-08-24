from app.domain.value_objects.user_settings import (
    MAX_RADIUS_METERS,
    MAX_RESULT_LIMIT,
    MIN_RADIUS_METERS,
    MIN_RESULT_LIMIT,
    RADIUS_STEP_METERS,
    UserSettings,
)


def test_a_step_widens_the_radius_by_one_notch() -> None:
    assert UserSettings().stepped_radius(1).nearby_radius_meters == 15_000


def test_a_negative_step_narrows_it() -> None:
    assert UserSettings().stepped_radius(-1).nearby_radius_meters == 5_000


def test_the_radius_stops_at_the_bounds() -> None:
    # The buttons repeat, so the clamp is what a driver hits, not an edge case.
    widest = UserSettings(nearby_radius_meters=MAX_RADIUS_METERS)
    narrowest = UserSettings(nearby_radius_meters=MIN_RADIUS_METERS)

    assert widest.stepped_radius(1).nearby_radius_meters == MAX_RADIUS_METERS
    assert narrowest.stepped_radius(-1).nearby_radius_meters == MIN_RADIUS_METERS


def test_a_step_changes_the_result_limit_by_one() -> None:
    assert UserSettings().stepped_result_limit(1).result_limit == 11
    assert UserSettings().stepped_result_limit(-1).result_limit == 9


def test_the_result_limit_stops_at_the_bounds() -> None:
    most = UserSettings(result_limit=MAX_RESULT_LIMIT)
    least = UserSettings(result_limit=MIN_RESULT_LIMIT)

    assert most.stepped_result_limit(1).result_limit == MAX_RESULT_LIMIT
    assert least.stepped_result_limit(-1).result_limit == MIN_RESULT_LIMIT


def test_stepping_leaves_the_other_setting_alone() -> None:
    stepped = UserSettings(result_limit=3).stepped_radius(1)

    assert stepped.result_limit == 3
    assert stepped.nearby_radius_meters == 10_000 + RADIUS_STEP_METERS
