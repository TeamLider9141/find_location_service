from app.domain.entities.location import Location
from app.domain.entities.place import Place
from app.domain.entities.saved_place import SavedPlace
from app.presentation.telegram.keyboards.categories import category_label
from app.domain.value_objects.category import PlaceCategory
from app.domain.value_objects.user_settings import UserSettings


def format_start_message() -> str:
    return (
        "Salom. Quyidagi knopkalardan birini tanlang.\n\n"
        "Manzil qidirish uchun manzil nomini yuboring.\n"
        "Manzil qo'shish uchun manzil nomi, lokatsiya yoki xarita linkini yuboring.\n"
        "Bekor qilish uchun /cancel bosing.\n"
        "Qidiruv radiusi va natijalar sonini /settings orqali o'zgartiring.\n"
        "Masalan: "
        "Домодедово аэропорт\n"
        "yoki Москва, Домодедовская 10"
    )


def format_search_results(locations: list[Location]) -> str:
    lines = ["🔎 Найдено несколько вариантов:"]
    for index, location in enumerate(locations, start=1):
        lines.extend(
            [
                "",
                f"{index}. {location.name}",
                f"   📍 {location.address}",
            ]
        )
    return "\n".join(lines)


def format_selected_location(location: Location, result_number: int | None = None) -> str:
    latitude = location.coordinates.latitude
    longitude = location.coordinates.longitude
    result_line = f"Natija: {result_number}\n" if result_number is not None else ""
    return (
        result_line
        + f"📍 {location.name}\n"
        f"{location.address}\n\n"
        f"{latitude}, {longitude}\n"
        f"https://www.google.com/maps/search/?api=1&query={latitude},{longitude}"
    )


def format_nearby_places(category: PlaceCategory, places: list[Place]) -> str:
    if not places:
        return f"{category_label(category)} bo'yicha yaqin joylar topilmadi."

    lines = [f"{category_label(category)} - yaqin joylar:"]
    for index, place in enumerate(places, start=1):
        lines.append("")
        lines.append(f"{index}. {place.name}")
        if place.distance_meters is not None:
            lines.append(f"   {round(place.distance_meters)} m")
        if place.address:
            lines.append(f"   {place.address}")
        lines.append(
            "   "
            f"https://www.google.com/maps/search/?api=1&query="
            f"{place.coordinates.latitude},{place.coordinates.longitude}"
        )
    return "\n".join(lines)


def format_user_settings(settings: UserSettings) -> str:
    return (
        "⚙️ Sozlamalar\n\n"
        f"Qidiruv radiusi: {settings.nearby_radius_meters // 1000} km\n"
        f"Natijalar soni: {settings.result_limit} ta"
    )


def format_saved_place(saved_place: SavedPlace) -> str:
    latitude = saved_place.coordinates.latitude
    longitude = saved_place.coordinates.longitude
    return (
        f"📍 {saved_place.name}\n"
        f"Kategoriya: {category_label(saved_place.category)}\n"
        f"{saved_place.address}\n\n"
        f"{latitude}, {longitude}\n"
        f"https://www.google.com/maps/search/?api=1&query={latitude},{longitude}"
    )
