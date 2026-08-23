import logging


def configure_logging(level: int = logging.INFO) -> None:
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    # aiogram polls Telegram once a second over aiohttp; at INFO that is one
    # request line per second and nothing else stays readable.
    logging.getLogger("aiohttp").setLevel(logging.WARNING)
