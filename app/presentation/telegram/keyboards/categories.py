from app.domain.value_objects.category import PlaceCategory

CATEGORY_LABELS: dict[PlaceCategory, str] = {
    PlaceCategory.RESTAURANT: "🍽 Oshxona",
    PlaceCategory.CAFE: "☕ Kafe/restoran qimmatlaridan",
    PlaceCategory.FUEL: "⛽ Gas quyish shaxobchasi",
    PlaceCategory.HOTEL: "🏨 Mehmonxona",
    PlaceCategory.PARKING: "🅿️ Parking",
    PlaceCategory.CAR_SERVICE: "🔧 Usta / servis",
    PlaceCategory.MOSQUE: "🕌 Masjid",
    PlaceCategory.BORDER_KZ: "🇰🇿 Qozog'iston chegara hududi",
    PlaceCategory.BORDER_RU: "🇷🇺 Rossiya chegara hududi",
    PlaceCategory.OTHER: "📌 Boshqa kategoriya",
}


def category_label(category: PlaceCategory) -> str:
    return CATEGORY_LABELS.get(category, category.value)


def categories_label(categories: tuple[PlaceCategory, ...]) -> str:
    """Every hat the place wears, on one line."""
    return " · ".join(category_label(category) for category in categories)
