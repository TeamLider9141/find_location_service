"""One answer to "where is this message pointing", for every flow that asks.

Three shapes arrive: a Telegram location, a shared venue, and text — bare
coordinates, a full map link, or a short link that only a network round trip
can open. The cheap readings run first; the resolver is asked only when the
text holds a link that said nothing by itself.
"""

from aiogram.types import Message

from app.domain.interfaces.links import LinkResolver
from app.domain.value_objects.coordinates import Coordinates
from app.presentation.telegram.location_input import (
    first_url,
    parse_coordinates_from_text,
)


async def coordinates_from_message(
    message: Message, link_resolver: LinkResolver | None = None
) -> Coordinates | None:
    direct = _without_network(message)
    if direct is not None:
        return direct

    text = getattr(message, "text", None)
    if not text or link_resolver is None:
        return None

    url = first_url(text)
    if url is None:
        return None

    final = await link_resolver.resolve(url)
    if final is None:
        return None

    return parse_coordinates_from_text(final)


def _without_network(message: Message) -> Coordinates | None:
    location = getattr(message, "location", None)
    if location is not None:
        return Coordinates(latitude=location.latitude, longitude=location.longitude)

    venue = getattr(message, "venue", None)
    if venue is not None and getattr(venue, "location", None) is not None:
        return Coordinates(
            latitude=venue.location.latitude,
            longitude=venue.location.longitude,
        )

    text = getattr(message, "text", None)
    if text:
        return parse_coordinates_from_text(text)

    return None
