import html

from app.domain.entities.place import Place
from app.domain.value_objects.category import PlaceCategory
from app.domain.value_objects.coordinates import Coordinates
from app.domain.value_objects.user_settings import UserSettings
from app.presentation.telegram.keyboards.categories import (
    categories_label,
    category_label,
)


def format_start_message() -> str:
    return (
        "Salom. Bu bot haydovchilar birga to'plagan manzillar bazasi.\n\n"
        "🔎 Manzillar — nom yoki kategoriya bo'yicha topish.\n"
        "🗂 Manzildagi hujjatlar — manzillarga biriktirilgan hujjatlar.\n"
        "📍 Yaqin atrofda — lokatsiya tashlang, yaqin joylarni ko'rsataman.\n"
        "➕ Joy qo'shish — o'zingiz bilgan joyni bazaga qo'shing.\n"
        "📁 Mening ma'lumotlarim — o'zingiz qo'shgan joylar va hujjatlar.\n"
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


def yandex_route_link(place: Place) -> str:
    """A ready-to-drive route in the navigator with the best local map.

    ``rtext=~lat,lon`` reads as "from wherever I am, to here"; ``rtt=auto``
    asks for a driving route.
    """
    latitude = place.coordinates.latitude
    longitude = place.coordinates.longitude
    return f"https://yandex.com/maps/?rtext=~{latitude},{longitude}&rtt=auto"


def google_route_link(place: Place) -> str:
    """The same ready-to-drive route, in Google's navigator.

    Both route links are plain URLs: they cost nothing, meter nothing, and
    have no relation to the API quota — that only touches the server-side
    distance lookups.
    """
    latitude = place.coordinates.latitude
    longitude = place.coordinates.longitude
    return (
        "https://www.google.com/maps/dir/?api=1"
        f"&destination={latitude},{longitude}&travelmode=driving"
    )


def format_place_card(place: Place) -> str:
    return format_place_preview(
        name=place.name,
        categories=place.categories,
        coordinates=place.coordinates,
        note=place.note,
    )


def format_place_preview(
    name: str,
    categories: tuple[PlaceCategory, ...],
    coordinates: Coordinates,
    note: str,
) -> str:
    """The card as everyone will see it — used both for the saved place and
    for the preview shown before anything is written."""
    note_line = f"📝 {note}\n" if note else ""
    link = (
        "https://www.google.com/maps/search/?api=1"
        f"&query={coordinates.latitude},{coordinates.longitude}"
    )

    return (
        f"📍 {name}\n"
        f"{categories_label(categories)}\n"
        f"{note_line}"
        f"\n{coordinates.latitude}, {coordinates.longitude}\n"
        f"{link}"
    )


# Both are approximations and say so: the router snaps pins to the nearest
# mapped road and works from OpenStreetMap, so a few kilometres of drift
# against a navigator is normal. The exact route lives behind the map link.
ROAD_DISTANCE_NOTE = "yo'l bo'yicha, taxminan"
STRAIGHT_DISTANCE_NOTE = "to'g'ri chiziq bo'yicha"


def format_place_results(
    places: list[Place],
    distances_meters: list[float] | None = None,
    distance_note: str | None = None,
) -> str:
    if not places:
        return NO_RESULTS_MESSAGE

    # The list goes out with parse_mode="HTML", so everything a driver typed —
    # names, notes — is escaped: one "<" in a name would otherwise make
    # Telegram refuse the whole message.
    lines: list[str] = []
    for index, place in enumerate(places, start=1):
        # The name is the link: tapping the line the driver is already reading
        # beats hunting a raw URL under it.
        name = html.escape(place.name)
        lines.append(f'{index}. <a href="{place_map_link(place)}">{name}</a>')
        lines.append(f"   {categories_label(place.categories)}")
        # nearby() supplies one distance per place; search() supplies none. A
        # short list is still safe to render — the places past its end simply
        # have no distance line.
        if distances_meters is not None and index <= len(distances_meters):
            # The note says what kind of distance this is: a road distance and
            # a straight line can differ by a river's worth of kilometres.
            distance = _format_distance(distances_meters[index - 1])
            suffix = f" · {distance_note}" if distance_note else ""
            lines.append(f"   {distance}{suffix}")
        if place.note:
            lines.append(f"   📝 {html.escape(place.note)}")
        # Our number is an estimate; these links are the navigators' own
        # routes. Both offered — drivers keep the one they already use.
        lines.append(
            f'   🧭 Marshrut: <a href="{google_route_link(place)}">Google</a>'
            f' · <a href="{yandex_route_link(place)}">Yandex</a>'
        )
        lines.append("")

    return "\n".join(lines).rstrip()


def _format_distance(meters: float) -> str:
    # Under a kilometre a driver wants metres: "0.1 km" is not a direction.
    if meters < 1000:
        return f"{round(meters)} m"
    return f"{meters / 1000:.1f} km"


def format_duplicate_warning(duplicates: list[Place]) -> str:
    names = "\n".join(
        f"• {place.name} — {categories_label(place.categories)}" for place in duplicates
    )
    return (
        "⚠️ Yaqin atrofda shunga o'xshash joy bor:\n\n"
        f"{names}\n\n"
        "Baribir qo'shaymi?"
    )
