from enum import Enum


def join_categories(categories: "tuple[PlaceCategory, ...]") -> str:
    """Serialize for the single TEXT column the places table already has.

    Old rows hold one bare value; new rows hold a comma list. Both parse back
    through :func:`split_categories`, so no migration is needed.
    """
    return ",".join(category.value for category in categories)


def split_categories(raw: str) -> "tuple[PlaceCategory, ...]":
    parsed = []
    for piece in raw.split(","):
        cleaned = piece.strip()
        if not cleaned:
            continue
        try:
            parsed.append(PlaceCategory(cleaned))
        except ValueError:
            # A value written by a future version is skipped, not fatal.
            continue
    return tuple(parsed)


class PlaceCategory(str, Enum):
    RESTAURANT = "restaurant"
    CAFE = "cafe"
    FUEL = "fuel"
    HOTEL = "hotel"
    PARKING = "parking"
    CAR_SERVICE = "car_service"
    MOSQUE = "mosque"
    # The two borders fold under one "Chegara hududlari" button on the
    # keyboards; storage stays flat, so search and counts treat them as
    # ordinary categories.
    BORDER_KZ = "border_kz"
    BORDER_RU = "border_ru"
    # Last on purpose: it is the fallback, and the keyboards draw the categories
    # in declaration order. Offered first it would invite a driver to skip
    # reading the real ones.
    OTHER = "other"
