from datetime import datetime

from app.application.use_cases.admin import AdminOverview, UserDetail, UsersPage
from app.domain.entities.bot_user import BotUser
from app.presentation.telegram.formatters import place_map_link
from app.presentation.telegram.keyboards.categories import category_label

EMPTY_DATABASE_MESSAGE = "Hali hech kim joy qo'shmagan."
NO_USERS_MESSAGE = "Foydalanuvchilar yo'q."
NO_SEARCHES_MESSAGE = "Hali qidiruv yo'q."


def format_admin_overview(overview: AdminOverview) -> str:
    lines = [
        "📊 Admin statistika",
        "",
        f"Joylar: {overview.total_places} ta",
        f"Bugun qo'shilgan: {overview.places_today} ta",
        f"Oxirgi 7 kunda: {overview.places_this_week} ta",
        f"Foydalanuvchilar: {overview.total_users} ta",
        f"Qidiruvlar: {overview.total_searches} ta",
        "",
        "Kategoriyalar:",
    ]

    if overview.categories:
        lines.extend(
            f"- {category_label(category)}: {count} ta" for category, count in overview.categories
        )
    else:
        lines.append(f"- {EMPTY_DATABASE_MESSAGE}")

    lines.extend(["", "Eng ko'p qo'shganlar:"])
    if overview.top_authors:
        lines.extend(
            f"{index}) {_author_label(author.full_name, author.username, author.user_id)}"
            f" — {author.places} ta"
            for index, author in enumerate(overview.top_authors, start=1)
        )
    else:
        lines.append(f"- {EMPTY_DATABASE_MESSAGE}")

    return "\n".join(lines)


def format_users_page(page: UsersPage) -> str:
    if not page.rows:
        return NO_USERS_MESSAGE

    total_pages = max(1, -(-page.total // page.page_size))
    lines = [
        f"👥 Foydalanuvchilar — {page.total} ta",
        f"Sahifa {page.page + 1}/{total_pages}",
        "",
    ]
    # Numbering continues across pages: "1)" on page two would read as a second
    # first user.
    first_number = page.page * page.page_size + 1
    for index, row in enumerate(page.rows, start=first_number):
        lines.append(
            f"{index}) {_user_label(row.user)} — {row.places} ta joy"
            f" | oxirgi faollik: {_format_stamp(row.user.last_seen_at)}"
        )

    return "\n".join(lines)


def format_user_detail(detail: UserDetail) -> str:
    user = detail.user
    lines = [
        f"👤 {_user_label(user)}",
        f"ID: {user.id}",
        f"Birinchi marta: {_format_stamp(user.first_seen_at)}",
        f"Oxirgi faollik: {_format_stamp(user.last_seen_at)}",
        f"Qidiruvlari: {detail.searches} ta",
        f"Qo'shgan joylari: {len(detail.places)} ta",
    ]

    if detail.places:
        lines.append("")
        for index, place in enumerate(detail.places, start=1):
            # The link lets the admin open a suspicious entry on the map
            # without leaving the panel.
            lines.append(f"{index}) {place.name} ({category_label(place.category)})")
            lines.append(f"   {place_map_link(place)}")

    return "\n".join(lines)


def format_top_searches(rows: list[tuple[str, int]]) -> str:
    if not rows:
        return NO_SEARCHES_MESSAGE

    lines = ["🔎 Eng ko'p qidirilganlar", ""]
    lines.extend(
        f"{index}) {query} — {times} marta" for index, (query, times) in enumerate(rows, start=1)
    )
    return "\n".join(lines)


def format_broadcast_preview(message_text: str, recipients: int) -> str:
    return (
        "📢 Yuboriladigan xabar:\n\n"
        f"{message_text}\n\n"
        f"Qabul qiluvchilar: {recipients} ta\n"
        "Tasdiqlaysizmi?"
    )


def format_broadcast_result(sent: int, failed: int) -> str:
    # Blocked bots are routine, so the split is part of the normal report.
    return f"📢 Yuborildi: {sent} ta\nYetib bormadi: {failed} ta"


def _user_label(user: BotUser) -> str:
    return _author_label(user.full_name, user.username, user.id)


def _author_label(full_name: str | None, username: str | None, user_id: int) -> str:
    name = full_name or str(user_id)
    return f"{name} (@{username})" if username else name


def _format_stamp(value: datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M")
