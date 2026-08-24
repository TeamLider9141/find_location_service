from dataclasses import dataclass
from os import environ
from pathlib import Path
from typing import Mapping


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str | None = None
    database_path: str = "data/find_location.sqlite3"
    admin_ids: tuple[int, ...] = ()

    @classmethod
    def from_env(cls, env: Mapping[str, str] = environ) -> "Settings":
        return cls.from_sources(env=env, dotenv_path=None)

    @classmethod
    def from_sources(
        cls,
        env: Mapping[str, str] = environ,
        dotenv_path: Path | str | None = Path(".env"),
    ) -> "Settings":
        dotenv_values = _read_dotenv(dotenv_path)
        values = {**dotenv_values, **env}

        return cls(
            telegram_bot_token=values.get("TELEGRAM_BOT_TOKEN") or None,
            database_path=values.get("DATABASE_PATH", cls.database_path),
            admin_ids=_read_admin_ids(values.get("ADMIN_IDS", "")),
        )


def _read_admin_ids(value: str) -> tuple[int, ...]:
    """Parse ``ADMIN_IDS`` — a comma separated list of Telegram user ids.

    An entry that is not a number is dropped rather than raising: a typo in
    .env must not lock out the ids that are valid, and cannot widen access.
    """
    admin_ids: list[int] = []
    for entry in value.split(","):
        cleaned = entry.strip()
        if cleaned.lstrip("-").isdigit():
            admin_ids.append(int(cleaned))

    return tuple(admin_ids)


def _read_dotenv(path: Path | str | None) -> dict[str, str]:
    if path is None:
        return {}

    env_path = Path(path)
    if not env_path.exists():
        return {}

    values: dict[str, str] = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue

        key, value = stripped.split("=", maxsplit=1)
        key = key.removeprefix("export ").strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]

        values[key] = value

    return values


def get_settings(
    env: Mapping[str, str] = environ,
    dotenv_path: Path | str | None = Path(".env"),
) -> Settings:
    return Settings.from_sources(env=env, dotenv_path=dotenv_path)
