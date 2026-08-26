import html
from datetime import datetime, timedelta, timezone

from app.application.use_cases.admin import (
    AdminOverview,
    AuthorPlaces,
    DeletionRow,
    UserDetail,
    UserRow,
    UsersPage,
)
from app.domain.entities.bot_user import BotUser
from app.domain.value_objects.category import PlaceCategory
from app.presentation.telegram.formatters import place_map_link
from app.presentation.telegram.keyboards.categories import (
    categories_label,
    category_label,
)

EMPTY_DATABASE_MESSAGE = "Hali hech kim joy qo'shmagan."
NO_USERS_MESSAGE = "Foydalanuvchilar yo'q."
# The right to add places, and a request still waiting on an answer — the two
# things about a user the list could not show, and the order it now ranks by.
ADD_ACCESS_MARK = "📍"
AWAITING_ACCESS_MARK = "👁‍🗨"
NO_SEARCHES_MESSAGE = "Hali qidiruv yo'q."
NO_PLACES_IN_CATEGORY_MESSAGE = "Bu kategoriyada hali joy yo'q."
NO_DELETIONS_MESSAGE = "Jurnal bo'sh — hali hech narsa o'chirilmagan."

DELETION_SOURCE_LABELS = {
    "owner": "egasi o'chirdi",
    "admin": "admin panel orqali",
}

# Telegram cuts a message at 4096 characters; a place entry with its link runs
# about a hundred. The cap keeps the reply well inside the limit.
PLACES_PREVIEW_LIMIT = 30


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
            f"{index}) {_standing_mark(row)}{_user_label(row.user)} — {row.places} ta joy"
            f" | oxirgi faollik: {_format_stamp(row.user.last_seen_at)}"
        )

    return "\n".join(lines)


def _standing_mark(row: UserRow) -> str:
    if row.may_add:
        return f"{ADD_ACCESS_MARK} "
    if row.awaiting:
        return f"{AWAITING_ACCESS_MARK} "
    return ""


def format_user_detail(detail: UserDetail) -> str:
    # Sent with parse_mode="HTML" so the place names can carry their map links.
    # Names — the user's and the places' — are input, so they are escaped: one
    # "<" would make Telegram refuse the whole message.
    user = detail.user
    lines = [
        f"👤 {html.escape(_user_label(user))}",
        f"ID: {user.id}",
        f"Birinchi marta: {_format_stamp(user.first_seen_at)}",
        f"Oxirgi faollik: {_format_stamp(user.last_seen_at)}",
        f"Qidiruvlari: {detail.searches} ta",
        f"Qo'shgan joylari: {len(detail.places)} ta",
    ]

    if detail.places:
        lines.append("")
        for index, place in enumerate(detail.places, start=1):
            # The name is the link: the admin opens a suspicious entry on the
            # map by tapping the line they are already reading.
            name = html.escape(place.name)
            lines.append(
                f'{index}) <a href="{place_map_link(place)}">{name}</a>'
                f" ({categories_label(place.categories)})"
            )
            # Names arrive with their own newlines inside; without a separator
            # the entries read as one solid block.
            lines.append("")

    return "\n".join(lines).rstrip()


def format_admin_places(category: PlaceCategory, groups: list[AuthorPlaces]) -> str:
    """One category's places, numbered by author, each name carrying its link.

    Sent with parse_mode="HTML"; author and place names are input, so both are
    escaped on the way in.
    """
    total = sum(len(group.places) for group in groups)
    if total == 0:
        return NO_PLACES_IN_CATEGORY_MESSAGE

    lines = [f"🗺 {category_label(category)} — {total} ta", ""]
    shown = 0
    for index, group in enumerate(groups, start=1):
        if shown >= PLACES_PREVIEW_LIMIT:
            break
        user = group.user
        author = _author_label(
            user.full_name if user else None,
            user.username if user else None,
            group.author_id,
        )
        lines.append(f"{index}) {html.escape(author)} — {len(group.places)} ta")
        for place in group.places:
            if shown >= PLACES_PREVIEW_LIMIT:
                break
            name = html.escape(place.name)
            lines.append(f'   📍 <a href="{place_map_link(place)}">{name}</a>')
            # Multi-line names would otherwise weld neighbouring entries
            # into one block.
            lines.append("")
            shown += 1

    remaining = total - shown
    if remaining > 0:
        lines.append(f"…va yana {remaining} ta joy.")

    return "\n".join(lines).strip()


def format_deletion_log(rows: list[DeletionRow]) -> str:
    """The tombstones, newest first: what went, who removed it, from where.

    Sent with parse_mode="HTML"; names are input, so they are escaped.
    """
    if not rows:
        return NO_DELETIONS_MESSAGE

    lines = [f"🧾 O'chirishlar jurnali — oxirgi {len(rows)} ta", ""]
    for index, row in enumerate(rows, start=1):
        record = row.record
        link = (
            "https://www.google.com/maps/search/?api=1"
            f"&query={record.latitude},{record.longitude}"
        )
        source = DELETION_SOURCE_LABELS.get(record.source, record.source)
        name = html.escape(record.place_name)
        deleter = _label_or_id(row.deleted_by, record.deleted_by_user_id)
        author = _label_or_id(row.added_by, record.added_by_user_id)
        lines.append(f"{index}) {_format_stamp(record.deleted_at)} — {source}")
        lines.append(
            f'   📍 <a href="{link}">{name}</a> ({categories_label(record.categories)})'
        )
        lines.append(f"   O'chirgan: {html.escape(deleter)}")
        lines.append(f"   Qo'shgan edi: {html.escape(author)}")
        lines.append("")

    return "\n".join(lines).rstrip()


def _label_or_id(user: BotUser | None, user_id: int) -> str:
    return _user_label(user) if user else str(user_id)


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


# Uzbekistan keeps no daylight saving, so a fixed offset is exact year-round.
TASHKENT = timezone(timedelta(hours=5))


def _format_stamp(value: datetime) -> str:
    # Stored in UTC — SQLite's CURRENT_TIMESTAMP and the in-memory clock alike —
    # and shown as Tashkent wall-clock time, which is what the admin's watch says.
    aware = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
    return aware.astimezone(TASHKENT).strftime("%Y-%m-%d %H:%M")
