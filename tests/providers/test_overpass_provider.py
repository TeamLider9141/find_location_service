import httpx
import pytest

from app.domain.value_objects.category import PlaceCategory
from app.domain.value_objects.coordinates import Coordinates
from app.infrastructure.providers.osm.overpass import OverpassPlacesProvider


@pytest.mark.asyncio
async def test_overpass_provider_searches_nearby_places_and_maps_results() -> None:
    seen_request: httpx.Request | None = None

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal seen_request
        seen_request = request
        return httpx.Response(
            200,
            json={
                "elements": [
                    {
                        "type": "node",
                        "id": 123,
                        "lat": 55.752,
                        "lon": 37.62,
                        "tags": {
                            "name": "Gazprom",
                            "amenity": "fuel",
                            "addr:full": "Moscow",
                            "phone": "+7 999",
                        },
                    }
                ]
            },
        )

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://overpass-api.de/api",
    )
    provider = OverpassPlacesProvider(client=client, user_agent="find-location-tests/0.1")

    places = await provider.search_nearby(
        Coordinates(latitude=55.7512, longitude=37.6184),
        category=PlaceCategory.FUEL,
        radius_meters=1000,
        limit=3,
    )

    assert seen_request is not None
    assert seen_request.url.path == "/api/interpreter"
    assert seen_request.headers["User-Agent"] == "find-location-tests/0.1"
    assert "amenity" in seen_request.url.params["data"]
    assert "fuel" in seen_request.url.params["data"]
    assert places[0].name == "Gazprom"
    assert places[0].category == PlaceCategory.FUEL
    assert places[0].address == "Moscow"
    assert places[0].phone == "+7 999"
    assert places[0].distance_meters is not None
    assert places[0].distance_meters > 0


@pytest.mark.asyncio
async def test_overpass_provider_uses_broad_accommodation_tags_for_hotels() -> None:
    seen_request: httpx.Request | None = None

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal seen_request
        seen_request = request
        return httpx.Response(200, json={"elements": []})

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://overpass-api.de/api",
    )
    provider = OverpassPlacesProvider(client=client, user_agent="find-location-tests/0.1")

    await provider.search_nearby(
        Coordinates(latitude=61.0, longitude=46.0),
        category=PlaceCategory.HOTEL,
        radius_meters=5000,
        limit=10,
    )

    assert seen_request is not None
    query = seen_request.url.params["data"]
    assert '["tourism"="hotel"]' in query
    assert '["tourism"="motel"]' in query
    assert '["tourism"="guest_house"]' in query
    assert '["tourism"="hostel"]' in query
    assert '["tourism"="apartment"]' in query
    assert '["tourism"="chalet"]' in query
    assert '["name"~"Гостиница|гостиница|Gostinitsa|gostinitsa","i"]' in query
    assert '["name:ru"~"Гостиница|гостиница|Gostinitsa|gostinitsa","i"]' in query
    assert "(around:5000,61.0,46.0)" in query


@pytest.mark.asyncio
async def test_overpass_provider_collapses_the_same_poi_returned_as_node_and_way() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "elements": [
                    {
                        "type": "node",
                        "id": 1,
                        "lat": 55.752,
                        "lon": 37.62,
                        "tags": {"name": "Gazprom", "amenity": "fuel"},
                    },
                    {
                        "type": "way",
                        "id": 2,
                        "center": {"lat": 55.752, "lon": 37.62},
                        "tags": {"name": "Gazprom", "amenity": "fuel"},
                    },
                    {
                        "type": "node",
                        "id": 3,
                        "lat": 55.760,
                        "lon": 37.63,
                        "tags": {"name": "Lukoil", "amenity": "fuel"},
                    },
                ]
            },
        )

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://overpass-api.de/api",
    )
    provider = OverpassPlacesProvider(client=client, user_agent="find-location-tests/0.1")

    places = await provider.search_nearby(
        Coordinates(latitude=55.7512, longitude=37.6184),
        category=PlaceCategory.FUEL,
        radius_meters=1000,
        limit=10,
    )

    assert [place.name for place in places] == ["Gazprom", "Lukoil"]
    assert places[0].source_id == "node:1"
