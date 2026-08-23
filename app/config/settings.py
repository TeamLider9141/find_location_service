from dataclasses import dataclass
from os import environ
from pathlib import Path
from typing import Mapping


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str | None = None
    nominatim_base_url: str = "https://nominatim.openstreetmap.org"
    overpass_base_url: str = "https://overpass-api.de/api"
    nominatim_user_agent: str = "find-location-bot/0.1"
    database_path: str = "data/find_location.sqlite3"

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
            nominatim_base_url=values.get(
                "NOMINATIM_BASE_URL",
                cls.nominatim_base_url,
            ),
            overpass_base_url=values.get(
                "OVERPASS_BASE_URL",
                cls.overpass_base_url,
            ),
            nominatim_user_agent=values.get(
                "NOMINATIM_USER_AGENT",
                cls.nominatim_user_agent,
            ),
            database_path=values.get("DATABASE_PATH", cls.database_path),
        )


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
