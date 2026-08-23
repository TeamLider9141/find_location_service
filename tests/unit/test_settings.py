from pathlib import Path

from app.config.settings import Settings, get_settings


def test_settings_loads_values_from_dotenv_file(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "TELEGRAM_BOT_TOKEN=123456:telegram-token",
                "NOMINATIM_BASE_URL=https://example.test",
                "OVERPASS_BASE_URL=https://overpass.example.test/api",
                'NOMINATIM_USER_AGENT="driver-map-bot/0.1"',
            ]
        ),
        encoding="utf-8",
    )

    settings = Settings.from_sources(env={}, dotenv_path=env_file)

    assert settings.telegram_bot_token == "123456:telegram-token"
    assert settings.nominatim_base_url == "https://example.test"
    assert settings.overpass_base_url == "https://overpass.example.test/api"
    assert settings.nominatim_user_agent == "driver-map-bot/0.1"


def test_environment_values_override_dotenv_file(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("TELEGRAM_BOT_TOKEN=from-dotenv", encoding="utf-8")

    settings = Settings.from_sources(
        env={"TELEGRAM_BOT_TOKEN": "from-environment"},
        dotenv_path=env_file,
    )

    assert settings.telegram_bot_token == "from-environment"


def test_get_settings_reads_project_dotenv_by_default(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("TELEGRAM_BOT_TOKEN=from-default-dotenv", encoding="utf-8")

    settings = get_settings(env={}, dotenv_path=env_file)

    assert settings.telegram_bot_token == "from-default-dotenv"
