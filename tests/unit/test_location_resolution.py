from app.domain.value_objects.coordinates import Coordinates
from app.infrastructure.location_links import _unwrap_consent
from app.presentation.telegram.location_input import (
    first_url,
    parse_coordinates_from_text,
)
from app.presentation.telegram.location_resolution import coordinates_from_message


class FakeMessage:
    def __init__(self, text=None, location=None) -> None:
        self.text = text
        self.location = location
        self.venue = None


class FakeLocation:
    def __init__(self, latitude: float, longitude: float) -> None:
        self.latitude = latitude
        self.longitude = longitude


class FakeResolver:
    def __init__(self, final: str | None) -> None:
        self._final = final
        self.asked: list[str] = []

    async def resolve(self, url: str) -> str | None:
        self.asked.append(url)
        return self._final


def test_the_google_pin_outranks_the_viewport() -> None:
    # @lat,lon is only where the map was centred; !3d!4d is the shared place.
    url = "https://www.google.com/maps/place/X/@41.0,69.0,17z/data=!3d41.326!4d69.228"

    parsed = parse_coordinates_from_text(url)

    assert (parsed.latitude, parsed.longitude) == (41.326, 69.228)


def test_first_url_finds_the_link_in_surrounding_text() -> None:
    assert first_url("mana: https://maps.app.goo.gl/abc123 shu yer") == (
        "https://maps.app.goo.gl/abc123"
    )
    assert first_url("hech qanday link yo'q") is None


async def test_a_telegram_location_never_asks_the_resolver() -> None:
    resolver = FakeResolver("https://example.com")
    message = FakeMessage(location=FakeLocation(41.3, 69.2))

    parsed = await coordinates_from_message(message, resolver)

    assert (parsed.latitude, parsed.longitude) == (41.3, 69.2)
    assert resolver.asked == []


async def test_a_short_link_is_chased_to_its_coordinates() -> None:
    resolver = FakeResolver(
        "https://www.google.com/maps/place/G/@41.0,69.0,17z/data=!3d41.326!4d69.228"
    )
    message = FakeMessage(text="https://maps.app.goo.gl/CtkXwh38Y2wVdGhe6")

    parsed = await coordinates_from_message(message, resolver)

    assert (parsed.latitude, parsed.longitude) == (41.326, 69.228)
    assert resolver.asked == ["https://maps.app.goo.gl/CtkXwh38Y2wVdGhe6"]


async def test_a_dead_link_is_unreadable_not_an_error() -> None:
    message = FakeMessage(text="https://maps.app.goo.gl/xyz")

    assert await coordinates_from_message(message, FakeResolver(None)) is None


async def test_without_a_resolver_a_short_link_stays_unreadable() -> None:
    message = FakeMessage(text="https://maps.app.goo.gl/xyz")

    assert await coordinates_from_message(message, None) is None


async def test_plain_text_never_asks_the_resolver() -> None:
    resolver = FakeResolver("https://example.com")

    assert await coordinates_from_message(FakeMessage(text="salom"), resolver) is None
    assert resolver.asked == []


def test_the_consent_wall_gives_up_its_destination() -> None:
    wrapped = (
        "https://consent.google.com/m?continue="
        "https%3A%2F%2Fwww.google.com%2Fmaps%2F%4041.3%2C69.2%2C17z"
    )

    assert _unwrap_consent(wrapped) == "https://www.google.com/maps/@41.3,69.2,17z"


def test_an_ordinary_url_passes_the_consent_check_untouched() -> None:
    assert _unwrap_consent("https://maps.google.com/x") == "https://maps.google.com/x"
