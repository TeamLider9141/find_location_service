from app.domain.value_objects.category import PlaceCategory

CATEGORY_LABELS: dict[PlaceCategory, str] = {
    PlaceCategory.RESTAURANT: "🍽 Oshxona",
    PlaceCategory.CAFE: "☕ Kafe",
    PlaceCategory.FUEL: "⛽ Gas quyish shaxobchasi",
    PlaceCategory.HOTEL: "🏨 Mehmonxona",
    PlaceCategory.PARKING: "🅿️ Parking",
    PlaceCategory.CAR_SERVICE: "🔧 Usta / servis",
}


def category_label(category: PlaceCategory) -> str:
    return CATEGORY_LABELS.get(category, category.value)
