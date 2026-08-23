import re
from urllib.parse import parse_qs, unquote, urlsplit

from app.domain.value_objects.coordinates import Coordinates

_DECIMAL_COORDINATE_RE = re.compile(
    r"(?<!\d)([-+]?\d{1,2}(?:\.\d+)?)\s*,\s*([-+]?\d{1,3}(?:\.\d+)?)(?!\d)"
)
_URL_RE = re.compile(r"https?://\S+")


def parse_coordinates_from_text(text: str) -> Coordinates | None:
    for url in _URL_RE.findall(text):
        coordinates = _parse_coordinates_from_url(url)
        if coordinates is not None:
            return coordinates

    return _parse_lat_lon_pair(unquote(text))


def _parse_coordinates_from_url(url: str) -> Coordinates | None:
    parsed = urlsplit(url)
    query = parse_qs(parsed.query)

    for key in ("q", "query"):
        for value in query.get(key, []):
            coordinates = _parse_lat_lon_pair(value)
            if coordinates is not None:
                return coordinates

    for value in query.get("ll", []):
        coordinates = _parse_lon_lat_pair(value)
        if coordinates is not None:
            return coordinates

    return _parse_lat_lon_pair(unquote(parsed.path))


def _parse_lat_lon_pair(value: str) -> Coordinates | None:
    match = _DECIMAL_COORDINATE_RE.search(value)
    if match is None:
        return None

    return _build_coordinates(latitude=match.group(1), longitude=match.group(2))


def _parse_lon_lat_pair(value: str) -> Coordinates | None:
    match = _DECIMAL_COORDINATE_RE.search(value)
    if match is None:
        return None

    return _build_coordinates(latitude=match.group(2), longitude=match.group(1))


def _build_coordinates(latitude: str, longitude: str) -> Coordinates | None:
    parsed_latitude = float(latitude)
    parsed_longitude = float(longitude)
    if not -90 <= parsed_latitude <= 90:
        return None
    if not -180 <= parsed_longitude <= 180:
        return None
    return Coordinates(latitude=parsed_latitude, longitude=parsed_longitude)
