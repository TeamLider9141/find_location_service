import httpx
import pytest

from app.infrastructure.providers.osm.nominatim import NominatimGeocodingProvider


@pytest.mark.asyncio
async def test_nominatim_provider_sends_search_request_and_maps_results() -> None:
    seen_request: httpx.Request | None = None

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal seen_request
        seen_request = request
        return httpx.Response(
            200,
            json=[
                {
                    "osm_type": "way",
                    "osm_id": 123456,
                    "name": "Международный аэропорт Домодедово",
                    "display_name": "Международный аэропорт Домодедово, Московская область, Россия",
                    "lat": "55.4146",
                    "lon": "37.8995",
                }
            ],
        )

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://nominatim.openstreetmap.org",
    )
    provider = NominatimGeocodingProvider(
        client=client,
        user_agent="find-location-tests/0.1",
    )

    locations = await provider.search("Домодедово аэропорт", limit=1)

    assert seen_request is not None
    assert seen_request.url.path == "/search"
    assert seen_request.url.params["q"] == "Домодедово аэропорт"
    assert seen_request.url.params["format"] == "jsonv2"
    assert seen_request.url.params["limit"] == "1"
    assert seen_request.headers["User-Agent"] == "find-location-tests/0.1"
    assert locations[0].name == "Международный аэропорт Домодедово"
