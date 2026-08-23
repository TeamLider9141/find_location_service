from app.infrastructure.providers.osm.mapper import map_nominatim_location


def test_maps_nominatim_response_to_provider_agnostic_location() -> None:
    raw = {
        "osm_type": "way",
        "osm_id": 123456,
        "name": "Международный аэропорт Домодедово",
        "display_name": "Международный аэропорт Домодедово, Московская область, Россия",
        "lat": "55.4146",
        "lon": "37.8995",
    }

    location = map_nominatim_location(raw)

    assert location.id == "osm:way:123456"
    assert location.name == "Международный аэропорт Домодедово"
    assert location.address == "Международный аэропорт Домодедово, Московская область, Россия"
    assert location.coordinates.latitude == 55.4146
    assert location.coordinates.longitude == 37.8995
    assert location.source == "osm"
    assert location.source_id == "way:123456"


def test_uses_display_name_prefix_when_nominatim_name_is_missing() -> None:
    raw = {
        "osm_type": "relation",
        "osm_id": 987,
        "display_name": "Домодедово, городской округ, Московская область, Россия",
        "lat": "55.4364",
        "lon": "37.7666",
    }

    location = map_nominatim_location(raw)

    assert location.name == "Домодедово"
    assert location.source_id == "relation:987"
