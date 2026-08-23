import pytest

from app.application.use_cases.search_location import SearchLocationUseCase
from app.domain.entities.location import Location
from app.domain.value_objects.coordinates import Coordinates


class RecordingGeocoder:
    def __init__(self, results_by_query: dict[str, list[Location]] | None = None) -> None:
        self.calls: list[tuple[str, int]] = []
        self.results_by_query = results_by_query

    async def search(self, query: str, limit: int = 5) -> list[Location]:
        self.calls.append((query, limit))
        if self.results_by_query is not None:
            return self.results_by_query.get(query, [])

        return [
            Location(
                id="osm:node:1",
                name="Домодедово",
                address="Домодедово, Московская область, Россия",
                coordinates=Coordinates(latitude=55.4364, longitude=37.7666),
                source="osm",
                source_id="node:1",
            )
        ]


@pytest.mark.asyncio
async def test_search_location_trims_query_and_delegates_to_geocoding_provider() -> None:
    geocoder = RecordingGeocoder()
    use_case = SearchLocationUseCase(geocoder)

    locations = await use_case.execute("  Домодедово аэропорт  ", limit=3)

    assert geocoder.calls == [("Домодедово аэропорт", 3)]
    assert locations[0].name == "Домодедово"


@pytest.mark.asyncio
async def test_search_location_falls_back_to_cyrillic_for_latin_russian_query() -> None:
    expected_location = Location(
        id="osm:node:2",
        name="Язинец",
        address="деревня Язинец",
        coordinates=Coordinates(latitude=58.1, longitude=31.2),
        source="osm",
        source_id="node:2",
    )
    geocoder = RecordingGeocoder(results_by_query={"деревня язинец": [expected_location]})
    use_case = SearchLocationUseCase(geocoder)

    locations = await use_case.execute("**derevnya Yazinets", limit=5)

    assert geocoder.calls == [
        ("derevnya Yazinets", 5),
        ("деревня язинец", 5),
    ]
    assert locations == [expected_location]


@pytest.mark.asyncio
async def test_search_location_rejects_empty_query_before_calling_provider() -> None:
    geocoder = RecordingGeocoder()
    use_case = SearchLocationUseCase(geocoder)

    with pytest.raises(ValueError, match="query"):
        await use_case.execute("   ")

    assert geocoder.calls == []
