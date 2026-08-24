from pathlib import Path

from app.config.settings import Settings, get_settings


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
