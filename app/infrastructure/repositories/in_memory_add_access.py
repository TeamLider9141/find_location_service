from app.domain.value_objects.add_access import AddAccessStatus


class InMemoryAddAccessRepository:
    def __init__(self) -> None:
        self._statuses: dict[int, AddAccessStatus] = {}

    def status(self, user_id: int) -> AddAccessStatus | None:
        return self._statuses.get(user_id)

    def set_status(self, user_id: int, status: AddAccessStatus) -> None:
        self._statuses[user_id] = status

    def clear(self, user_id: int) -> None:
        self._statuses.pop(user_id, None)

    def allowed_ids(self) -> set[int]:
        return {
            user_id
            for user_id, status in self._statuses.items()
            if status == AddAccessStatus.APPROVED
        }
