from dataclasses import dataclass

from app.domain.entities.bot_user import BotUser
from app.domain.entities.place import Place
from app.domain.interfaces.places import PlaceRepository
from app.domain.interfaces.users import UserRepository
from app.domain.value_objects.category import PlaceCategory

TOP_AUTHOR_LIMIT = 10
WEEK_DAYS = 7


@dataclass(frozen=True)
class AuthorRanking:
    user_id: int
    full_name: str | None
    username: str | None
    places: int


@dataclass(frozen=True)
class AdminOverview:
    total_places: int
    places_today: int
    places_this_week: int
    total_users: int
    total_searches: int
    categories: list[tuple[PlaceCategory, int]]
    top_authors: list[AuthorRanking]


@dataclass(frozen=True)
class UserRow:
    user: BotUser
    places: int


@dataclass(frozen=True)
class UsersPage:
    total: int
    page: int
    page_size: int
    rows: list[UserRow]


@dataclass(frozen=True)
class UserDetail:
    user: BotUser
    places: list[Place]
    searches: int


class GetAdminOverviewUseCase:
    def __init__(self, places: PlaceRepository, users: UserRepository) -> None:
        self._places = places
        self._users = users

    def execute(self) -> AdminOverview:
        categories = sorted(
            self._places.count_by_category().items(),
            key=lambda item: (-item[1], item[0].value),
        )

        return AdminOverview(
            total_places=self._places.count(),
            places_today=self._places.count_added_since(days=0),
            places_this_week=self._places.count_added_since(days=WEEK_DAYS),
            total_users=self._users.count(),
            total_searches=self._users.total_searches(),
            categories=categories,
            top_authors=self._rank_authors(),
        )

    def _rank_authors(self) -> list[AuthorRanking]:
        rankings: list[AuthorRanking] = []
        for user_id, places in self._places.top_authors(limit=TOP_AUTHOR_LIMIT):
            # A place can outlive the moment its author was recorded — rows added
            # before user tracking existed have no user row at all — so a missing
            # user is a name we cannot show, not a contributor to drop.
            user = self._users.get(user_id)
            rankings.append(
                AuthorRanking(
                    user_id=user_id,
                    full_name=user.full_name if user is not None else None,
                    username=user.username if user is not None else None,
                    places=places,
                )
            )

        return rankings


class ListUsersPageUseCase:
    def __init__(self, users: UserRepository, places: PlaceRepository) -> None:
        self._users = users
        self._places = places

    def execute(self, page: int, page_size: int) -> UsersPage:
        safe_page = max(page, 0)
        safe_size = max(page_size, 1)
        total, users = self._users.list_page(offset=safe_page * safe_size, limit=safe_size)

        return UsersPage(
            total=total,
            page=safe_page,
            page_size=safe_size,
            rows=[
                UserRow(user=user, places=len(self._places.list_by_author(user.id)))
                for user in users
            ],
        )


class GetUserDetailUseCase:
    def __init__(self, users: UserRepository, places: PlaceRepository) -> None:
        self._users = users
        self._places = places

    def execute(self, user_id: int) -> UserDetail | None:
        user = self._users.get(user_id)
        if user is None:
            return None

        return UserDetail(
            user=user,
            places=self._places.list_by_author(user_id),
            searches=self._users.search_count(user_id),
        )


class TopSearchesUseCase:
    def __init__(self, users: UserRepository) -> None:
        self._users = users

    def execute(self, limit: int = 10) -> list[tuple[str, int]]:
        return self._users.top_searches(limit=limit)


class RecordUserVisitUseCase:
    def __init__(self, users: UserRepository) -> None:
        self._users = users

    def execute(self, user_id: int, full_name: str, username: str | None) -> None:
        # Telegram accepts accounts whose visible name is blank. The id is the
        # one label that always exists, so the panel falls back to it.
        cleaned_name = full_name.strip() or str(user_id)
        self._users.record_seen(user_id, full_name=cleaned_name, username=username)


class DeletePlaceAsAdminUseCase:
    def __init__(self, places: PlaceRepository) -> None:
        self._places = places

    def execute(self, place_id: int) -> bool:
        return self._places.delete_any(place_id)


class ListBroadcastRecipientsUseCase:
    def __init__(self, users: UserRepository) -> None:
        self._users = users

    def execute(self) -> list[int]:
        return self._users.all_ids()
