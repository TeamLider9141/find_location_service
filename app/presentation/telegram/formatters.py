from app.domain.entities.place import Place
from app.domain.value_objects.user_settings import UserSettings
from app.presentation.telegram.keyboards.categories import category_label


def format_start_message() -> str:
    return (
        "Salom. Bu bot haydovchilar birga to'plagan manzillar bazasi.\n\n"
        "🔎 Qidirish — nom yoki kategoriya bo'yicha topish.\n"
        "📍 Yaqin atrofda — lokatsiya tashlang, yaqin joylarni ko'rsataman.\n"
        "➕ Joy qo'shish — o'zingiz bilgan joyni bazaga qo'shing.\n"
        "📒 Mening joylarim — o'zingiz qo'shgan joylar.\n"
        "⚙️ Sozlamalar — radius va natijalar soni.\n\n"
        "Shunchaki nom yozsangiz ham qidiraman. Masalan: Домодедово аэропорт."
    )


def format_user_settings(settings: UserSettings) -> str:
    return (
        "⚙️ Sozlamalar\n\n"
        f"Qidiruv radiusi: {settings.nearby_radius_meters // 1000} km\n"
        f"Natijalar soni: {settings.result_limit} ta"
    )


NO_RESULTS_MESSAGE = (
    "Hech narsa topilmadi.\n\n"
    "Bazada faqat haydovchilar qo'shgan joylar bor. "
    "Bu joyni bilsangiz — ➕ Joy qo'shish orqali qo'shing."
)


def place_map_link(place: Place) -> str:
    latitude = place.coordinates.latitude
    longitude = place.coordinates.longitude
    return f"https://www.google.com/maps/search/?api=1&query={latitude},{longitude}"


def format_place_card(place: Place) -> str:
    latitude = place.coordinates.latitude
    longitude = place.coordinates.longitude
    note_line = f"📝 {place.note}\n" if place.note else ""

    return (
        f"📍 {place.name}\n"
        f"{category_label(place.category)}\n"
        f"{note_line}"
        f"\n{latitude}, {longitude}\n"
        f"{place_map_link(place)}"
    )


def format_place_results(
    places: list[Place],
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


def format_duplicate_warning(duplicates: list[Place]) -> str:
    names = "\n".join(
        f"• {place.name} — {category_label(place.category)}" for place in duplicates
    )
    return (
        "⚠️ Yaqin atrofda shunga o'xshash joy bor:\n\n"
        f"{names}\n\n"
        "Baribir qo'shaymi?"
    )
