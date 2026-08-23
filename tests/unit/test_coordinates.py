import pytest

from app.domain.value_objects.coordinates import Coordinates


def test_rejects_latitude_outside_world_bounds() -> None:
    with pytest.raises(ValueError, match="latitude"):
        Coordinates(latitude=91.0, longitude=37.6)


def test_rejects_longitude_outside_world_bounds() -> None:
    with pytest.raises(ValueError, match="longitude"):
        Coordinates(latitude=55.7, longitude=181.0)


def test_calculates_distance_between_two_coordinates_in_meters() -> None:
    moscow_center = Coordinates(latitude=55.7558, longitude=37.6173)
    domodedovo_airport = Coordinates(latitude=55.4088, longitude=37.9063)

    distance = moscow_center.distance_to(domodedovo_airport)

    assert 42000 <= distance <= 44000
