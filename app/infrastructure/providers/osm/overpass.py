from collections.abc import Sequence
from math import asin, cos, radians, sin, sqrt
from typing import Any

import httpx

from app.domain.entities.place import Place
from app.domain.value_objects.category import PlaceCategory
from app.domain.value_objects.coordinates import Coordinates

_CATEGORY_TAGS: dict[PlaceCategory, list[tuple[str, str]]] = {
    PlaceCategory.RESTAURANT: [("amenity", "restaurant")],
    PlaceCategory.CAFE: [("amenity", "cafe")],
    PlaceCategory.FUEL: [("amenity", "fuel")],
    PlaceCategory.HOTEL: [
        ("tourism", "hotel"),
        ("tourism", "motel"),
        ("tourism", "guest_house"),
        ("tourism", "hostel"),
        ("tourism", "apartment"),
        ("tourism", "chalet"),
    ],
    PlaceCategory.PARKING: [("amenity", "parking")],
    PlaceCategory.CAR_SERVICE: [("shop", "car_repair"), ("amenity", "car_repair")],
}

# Many Russian roadside hotels are tagged only by name, without a tourism=* tag.
_CATEGORY_NAME_PATTERNS: dict[PlaceCategory, str] = {
    PlaceCategory.HOTEL: "Гостиница|гостиница|Gostinitsa|gostinitsa",
}

_NAME_TAG_KEYS = ("name", "name:ru")
_ELEMENT_TYPES = ("node", "way", "relation")


class OverpassPlacesProvider:
    def __init__(
        self,
        *,
        base_url: str = "https://overpass-api.de/api",
        user_agent: str = "find-location-bot/0.1",
        client: httpx.AsyncClient | None = None,
        timeout_seconds: float = 20.0,
    ) -> None:
        self._client = client or httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=timeout_seconds,
        )
        self._owns_client = client is None
        self._user_agent = user_agent

    async def search_nearby(
        self,
        coordinates: Coordinates,
        category: PlaceCategory,
        radius_meters: int = 3000,
        limit: int = 10,
    ) -> list[Place]:
        response = await self._client.get(
            "/interpreter",
            params={
                "data": _build_overpass_query(
                    coordinates=coordinates,
                    category=category,
                    radius_meters=radius_meters,
                )
            },
            headers={"User-Agent": self._user_agent},
        )
        response.raise_for_status()
        elements = _expect_elements(response.json())
        places: dict[tuple[str, float, float], Place] = {}
        for element in elements:
            place = _map_overpass_element(
                element=element,
                category=category,
                origin=coordinates,
            )
            if place is not None:
                places.setdefault(_dedup_key(place), place)
        return sorted(
            places.values(),
            key=lambda item: (
                item.distance_meters
                if item.distance_meters is not None
                else float("inf")
            ),
        )[:limit]

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()


def _build_overpass_query(
    coordinates: Coordinates,
    category: PlaceCategory,
    radius_meters: int,
) -> str:
    around = (
        f"(around:{radius_meters},"
        f"{coordinates.latitude},"
        f"{coordinates.longitude})"
    )
    selectors = [
        f"{element_type}{tag_filter}{around};"
        for tag_filter in _category_filters(category)
        for element_type in _ELEMENT_TYPES
    ]

    return "[out:json][timeout:20];(" + "".join(selectors) + ");out center tags;"


def _category_filters(category: PlaceCategory) -> list[str]:
    filters = [f'["{key}"="{value}"]' for key, value in _CATEGORY_TAGS.get(category, [])]

    pattern = _CATEGORY_NAME_PATTERNS.get(category)
    if pattern is not None:
        filters.extend(f'["{key}"~"{pattern}","i"]' for key in _NAME_TAG_KEYS)

    return filters


def _dedup_key(place: Place) -> tuple[str, float, float]:
    """OSM often holds one POI as a node, a way and a relation at once."""
    return (
        place.name,
        round(place.coordinates.latitude, 5),
        round(place.coordinates.longitude, 5),
    )


def _expect_elements(value: Any) -> Sequence[dict[str, Any]]:
    if not isinstance(value, dict) or not isinstance(value.get("elements"), list):
        raise ValueError("Overpass response must contain elements list")
    return value["elements"]


def _map_overpass_element(
    element: dict[str, Any],
    category: PlaceCategory,
    origin: Coordinates,
) -> Place | None:
    coordinates = _coordinates_from_element(element)
    if coordinates is None:
        return None

    tags = element.get("tags")
    if not isinstance(tags, dict):
        tags = {}

    raw_id = element.get("id")
    raw_type = element.get("type", "element")
    name = str(tags.get("name") or tags.get("brand") or "Nomsiz joy")
    address = _address_from_tags(tags)
    phone = tags.get("phone") or tags.get("contact:phone")

    return Place(
        id=f"osm:{raw_type}:{raw_id}",
        name=name,
        category=category,
        coordinates=coordinates,
        address=address,
        phone=str(phone) if phone else None,
        distance_meters=_distance_meters(origin, coordinates),
        source="osm",
        source_id=f"{raw_type}:{raw_id}",
    )


def _coordinates_from_element(element: dict[str, Any]) -> Coordinates | None:
    if "lat" in element and "lon" in element:
        return Coordinates(latitude=float(element["lat"]), longitude=float(element["lon"]))

    center = element.get("center")
    if isinstance(center, dict) and "lat" in center and "lon" in center:
        return Coordinates(latitude=float(center["lat"]), longitude=float(center["lon"]))

    return None


def _address_from_tags(tags: dict[str, Any]) -> str | None:
    if tags.get("addr:full"):
        return str(tags["addr:full"])

    parts = [
        tags.get("addr:street"),
        tags.get("addr:housenumber"),
        tags.get("addr:city"),
    ]
    address = ", ".join(str(part) for part in parts if part)
    return address or None


def _distance_meters(start: Coordinates, end: Coordinates) -> float:
    earth_radius_meters = 6_371_000
    start_latitude = radians(start.latitude)
    end_latitude = radians(end.latitude)
    delta_latitude = radians(end.latitude - start.latitude)
    delta_longitude = radians(end.longitude - start.longitude)

    a = (
        sin(delta_latitude / 2) ** 2
        + cos(start_latitude) * cos(end_latitude) * sin(delta_longitude / 2) ** 2
    )
    return round(earth_radius_meters * 2 * asin(sqrt(a)), 1)
