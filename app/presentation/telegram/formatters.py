from app.domain.entities.community_place import Place as CommunityPlace
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


NO_RESULTS_MESSAGE = (
    "Hech narsa topilmadi.\n\n"
    "Bazada faqat haydovchilar qo'shgan joylar bor. "
    "Bu joyni bilsangiz — ➕ Joy qo'shish orqali qo'shing."
)


def format_place_card(place: CommunityPlace) -> str:
    latitude = place.coordinates.latitude
    longitude = place.coordinates.longitude
    note_line = f"📝 {place.note}\n" if place.note else ""

    return (
        f"📍 {place.name}\n"
        f"{category_label(place.category)}\n"
        f"{note_line}"
        f"\n{latitude}, {longitude}\n"
        f"https://www.google.com/maps/search/?api=1&query={latitude},{longitude}"
    )


def format_place_results(
    places: list[CommunityPlace],
    distances_meters: list[float] | None = None,
) -> str:
    if not places:
        return NO_RESULTS_MESSAGE

    lines: list[str] = []
    for index, place in enumerate(places, start=1):
        lines.append(f"{index}. {place.name}")
        lines.append(f"   {category_label(place.category)}")
        # nearby() supplies one distance per place; search() supplies none. A
        # short list is still safe to render — the places past its end simply
        # have no distance line.
        if distances_meters is not None and index <= len(distances_meters):
            lines.append(f"   {_format_distance(distances_meters[index - 1])}")
        if place.note:
            lines.append(f"   📝 {place.note}")
        lines.append("")

    return "\n".join(lines).rstrip()


def _format_distance(meters: float) -> str:
    # Under a kilometre a driver wants metres: "0.1 km" is not a direction.
    if meters < 1000:
        return f"{round(meters)} m"
    return f"{meters / 1000:.1f} km"


def format_duplicate_warning(duplicates: list[CommunityPlace]) -> str:
    names = "\n".join(
        f"• {place.name} — {category_label(place.category)}" for place in duplicates
    )
    return (
        "⚠️ Yaqin atrofda shunga o'xshash joy bor:\n\n"
        f"{names}\n\n"
        "Baribir qo'shaymi?"
    )
