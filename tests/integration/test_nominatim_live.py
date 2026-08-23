import os

import pytest

from app.infrastructure.providers.osm.nominatim import NominatimGeocodingProvider


pytestmark = pytest.mark.integration


@pytest.mark.skipif(
    os.getenv("RUN_REAL_OSM") != "1",
    reason="set RUN_REAL_OSM=1 to call the live Nominatim API",
)
@pytest.mark.asyncio
async def test_live_nominatim_finds_domodedovo_airport() -> None:
    provider = NominatimGeocodingProvider(user_agent="find-location-tests/0.1")
    try:
        locations = await provider.search("Домодедово аэропорт", limit=5)
    finally:
        await provider.close()

    assert locations
    assert any("Домодедово" in location.name or "Домодедово" in location.address for location in locations)
