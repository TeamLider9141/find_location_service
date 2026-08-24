from datetime import datetime

from app.application.use_cases.admin import UserRow, UsersPage
from app.domain.entities.bot_user import BotUser
from app.domain.entities.place import Place
from app.domain.value_objects.category import PlaceCategory
from app.domain.value_objects.coordinates import Coordinates
from app.presentation.telegram.keyboards.admin import (
    build_admin_menu_keyboard,
    build_broadcast_confirmation_keyboard,
    build_user_detail_keyboard,
    build_users_page_keyboard,
)


def make_user(user_id: int = 1, full_name: str = "Ali") -> BotUser:
    stamp = datetime(2026, 1, 1)
    return BotUser(
        id=user_id,
        full_name=full_name,
        username=None,
        first_seen_at=stamp,
        last_seen_at=stamp,
    )


def make_place(place_id: int = 1, name: str = "Газпром") -> Place:
    return Place(
        id=place_id,
        added_by_user_id=1,
        name=name,
        category=PlaceCategory.FUEL,
        coordinates=Coordinates(latitude=55.75, longitude=37.61),
        note="",
        created_at=datetime(2026, 1, 1),
    )


def page(rows: list[UserRow], total: int, number: int = 0, size: int = 5) -> UsersPage:
    return UsersPage(total=total, page=number, page_size=size, rows=rows)


def callbacks(keyboard) -> list[str]:
    return [button.callback_data for row in keyboard.inline_keyboard for button in row]


def test_the_menu_offers_every_section() -> None:
    data = callbacks(build_admin_menu_keyboard())

    assert "admin:stats" in data
    assert "admin:users:0" in data
    assert "admin:searches" in data
    assert "admin:broadcast" in data


def test_each_user_gets_a_button_carrying_their_id() -> None:
    rows = [UserRow(user=make_user(7), places=2)]

    data = callbacks(build_users_page_keyboard(page(rows, total=1)))

    assert "admin:user:7" in data


def test_the_first_page_has_no_back_arrow() -> None:
    rows = [UserRow(user=make_user(), places=0)]

    data = callbacks(build_users_page_keyboard(page(rows, total=1)))

    assert not any(item.startswith("admin:users:-") for item in data)
    assert "admin:users:0" not in data


def test_a_middle_page_offers_both_arrows() -> None:
    rows = [UserRow(user=make_user(user_id=i), places=0) for i in range(5)]

    data = callbacks(build_users_page_keyboard(page(rows, total=20, number=1)))

    assert "admin:users:0" in data
    assert "admin:users:2" in data


def test_the_last_page_has_no_forward_arrow() -> None:
    # 12 users at 5 per page: page 2 is the last one. A forward arrow there
    # would open an empty list.
    rows = [UserRow(user=make_user(user_id=i), places=0) for i in range(2)]

    data = callbacks(build_users_page_keyboard(page(rows, total=12, number=2)))

    assert "admin:users:3" not in data
    assert "admin:users:1" in data


def test_a_user_detail_offers_a_delete_button_per_place() -> None:
    data = callbacks(
        build_user_detail_keyboard([make_place(3), make_place(4, "Лукойл")], user_id=7)
    )

    assert "admin:place_delete:3" in data
    assert "admin:place_delete:4" in data


def test_a_user_detail_returns_to_the_list() -> None:
    data = callbacks(build_user_detail_keyboard([], user_id=7, page=2))

    assert "admin:users:2" in data


def test_a_user_detail_offers_to_revoke_add_access() -> None:
    # Present even for a user who never asked: revoking them is a harmless
    # no-op, and the admin should not have to check first.
    data = callbacks(build_user_detail_keyboard([], user_id=7))

    assert "admin:revoke_add:7" in data


def test_broadcast_confirmation_offers_send_and_cancel() -> None:
    data = callbacks(build_broadcast_confirmation_keyboard())

    assert "admin:broadcast:send" in data
    assert "admin:broadcast:cancel" in data
