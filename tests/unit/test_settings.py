from pathlib import Path

from app.config.settings import Settings, get_settings
from app.presentation.telegram.middlewares.throttling import (
    BURST_SIZE,
    IDLE_SECONDS,
    PRUNE_INTERVAL_SECONDS,
    REFILL_PER_SECOND,
    WARNING_INTERVAL_SECONDS,
)


def test_settings_read_the_token_and_database_path_from_env() -> None:
    settings = Settings.from_sources(
        env={"TELEGRAM_BOT_TOKEN": "abc", "DATABASE_PATH": "/tmp/places.sqlite3"},
        dotenv_path=None,
    )

    assert settings.telegram_bot_token == "abc"
    assert settings.database_path == "/tmp/places.sqlite3"


def test_database_path_has_a_default() -> None:
    settings = Settings.from_sources(env={}, dotenv_path=None)

    assert settings.database_path == "data/find_location.sqlite3"
    assert settings.telegram_bot_token is None


def test_settings_have_no_provider_configuration() -> None:
    settings = Settings.from_sources(env={}, dotenv_path=None)

    assert not hasattr(settings, "nominatim_base_url")
    assert not hasattr(settings, "overpass_base_url")


def test_settings_load_values_from_a_dotenv_file(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "# bot",
                'TELEGRAM_BOT_TOKEN="123456:telegram-token"',
                "export DATABASE_PATH = /srv/places.sqlite3",
            ]
        ),
        encoding="utf-8",
    )

    settings = Settings.from_sources(env={}, dotenv_path=env_file)

    # Quotes, comments and `export` are what a hand-written .env actually looks
    # like; a token read with its quotes still attached fails at Telegram.
    assert settings.telegram_bot_token == "123456:telegram-token"
    assert settings.database_path == "/srv/places.sqlite3"


def test_env_overrides_dotenv(tmp_path: Path) -> None:
    dotenv = tmp_path / ".env"
    dotenv.write_text("TELEGRAM_BOT_TOKEN=from-file\n", encoding="utf-8")

    settings = Settings.from_sources(
        env={"TELEGRAM_BOT_TOKEN": "from-env"},
        dotenv_path=dotenv,
    )

    assert settings.telegram_bot_token == "from-env"


def test_a_missing_dotenv_file_is_not_an_error(tmp_path: Path) -> None:
    settings = Settings.from_sources(env={}, dotenv_path=tmp_path / "absent.env")

    assert settings.telegram_bot_token is None


def test_get_settings_reads_the_dotenv_it_is_given(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("TELEGRAM_BOT_TOKEN=from-default-dotenv", encoding="utf-8")

    settings = get_settings(env={}, dotenv_path=env_file)

    assert settings.telegram_bot_token == "from-default-dotenv"


def test_admin_ids_are_parsed_from_a_comma_list() -> None:
    settings = Settings.from_sources(env={"ADMIN_IDS": "111,222"}, dotenv_path=None)

    assert settings.admin_ids == (111, 222)


def test_admin_ids_tolerate_spacing_and_trailing_commas() -> None:
    settings = Settings.from_sources(env={"ADMIN_IDS": " 111 , 222 , "}, dotenv_path=None)

    assert settings.admin_ids == (111, 222)


def test_a_non_numeric_admin_id_is_dropped() -> None:
    # A typo in .env must not lock the panel shut for the ids that are valid,
    # and must never widen access either — an unreadable entry is simply gone.
    settings = Settings.from_sources(env={"ADMIN_IDS": "111,oops"}, dotenv_path=None)

    assert settings.admin_ids == (111,)


def test_without_admin_ids_nobody_is_an_admin() -> None:
    settings = Settings.from_sources(env={}, dotenv_path=None)

    assert settings.admin_ids == ()


def test_the_throttle_defaults_match_the_middleware() -> None:
    # The middleware constants are the documented behaviour. Config that
    # silently disagreed with them would make the docs wrong, not the config.
    settings = Settings.from_sources(env={}, dotenv_path=None)

    assert settings.throttle_burst == BURST_SIZE
    assert settings.throttle_refill_per_second == REFILL_PER_SECOND
    assert settings.throttle_warning_seconds == WARNING_INTERVAL_SECONDS


def test_the_throttle_is_tuned_from_the_environment() -> None:
    settings = Settings.from_sources(
        env={
            "THROTTLE_BURST": "10",
            "THROTTLE_REFILL_PER_SECOND": "2.5",
            "THROTTLE_WARNING_SECONDS": "30",
        },
        dotenv_path=None,
    )

    assert settings.throttle_burst == 10
    assert settings.throttle_refill_per_second == 2.5
    assert settings.throttle_warning_seconds == 30.0


def test_a_burst_of_zero_is_refused() -> None:
    # Zero would drop every message from everyone, including the admin who
    # would have to fix it. A misconfiguration must not be a way to lock the
    # bot shut.
    settings = Settings.from_sources(env={"THROTTLE_BURST": "0"}, dotenv_path=None)

    assert settings.throttle_burst == BURST_SIZE


def test_a_refill_of_zero_is_refused() -> None:
    # Nothing ever refills, so every driver is throttled forever once they hit
    # the burst.
    settings = Settings.from_sources(env={"THROTTLE_REFILL_PER_SECOND": "0"}, dotenv_path=None)

    assert settings.throttle_refill_per_second == REFILL_PER_SECOND


def test_unreadable_throttle_values_fall_back_to_the_defaults() -> None:
    settings = Settings.from_sources(
        env={
            "THROTTLE_BURST": "many",
            "THROTTLE_REFILL_PER_SECOND": "fast",
            "THROTTLE_WARNING_SECONDS": "-5",
        },
        dotenv_path=None,
    )

    assert settings.throttle_burst == BURST_SIZE
    assert settings.throttle_refill_per_second == REFILL_PER_SECOND
    assert settings.throttle_warning_seconds == WARNING_INTERVAL_SECONDS


def test_warning_every_time_is_allowed() -> None:
    # Zero is a choice, not a typo: it means answer every dropped message.
    settings = Settings.from_sources(env={"THROTTLE_WARNING_SECONDS": "0"}, dotenv_path=None)

    assert settings.throttle_warning_seconds == 0.0


def test_the_cleanup_timers_default_to_the_middleware_values() -> None:
    settings = Settings.from_sources(env={}, dotenv_path=None)

    assert settings.throttle_idle_seconds == IDLE_SECONDS
    assert settings.throttle_prune_interval_seconds == PRUNE_INTERVAL_SECONDS


def test_the_cleanup_timers_are_tuned_from_the_environment() -> None:
    settings = Settings.from_sources(
        env={"THROTTLE_IDLE_SECONDS": "600", "THROTTLE_PRUNE_INTERVAL_SECONDS": "120"},
        dotenv_path=None,
    )

    assert settings.throttle_idle_seconds == 600.0
    assert settings.throttle_prune_interval_seconds == 120.0


def test_a_zero_idle_window_is_refused() -> None:
    # Forgetting a driver the instant their message lands would hand them a full
    # bucket on every message, which is the same as no rate limit at all.
    settings = Settings.from_sources(env={"THROTTLE_IDLE_SECONDS": "0"}, dotenv_path=None)

    assert settings.throttle_idle_seconds == IDLE_SECONDS
