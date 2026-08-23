import argparse
import asyncio

from app.application.use_cases.search_location import SearchLocationUseCase
from app.config.settings import get_settings
from app.infrastructure.providers.osm.nominatim import NominatimGeocodingProvider
from app.application.use_cases.nearby_places import NearbyPlacesUseCase
from app.presentation.telegram.bot import (
    create_bot,
    create_dispatcher,
    create_geocoding_provider,
    create_places_provider,
    create_saved_place_repository,
)
from app.shared.logging import configure_logging


async def run_search(query: str, limit: int = 5) -> int:
    settings = get_settings()
    provider = NominatimGeocodingProvider(
        base_url=settings.nominatim_base_url,
        user_agent=settings.nominatim_user_agent,
    )
    use_case = SearchLocationUseCase(provider)
    try:
        locations = await use_case.execute(query, limit=limit)
    finally:
        await provider.close()

    for index, location in enumerate(locations, start=1):
        print(f"{index}. {location.name}")
        print(f"   {location.address}")
        print(f"   {location.coordinates.latitude}, {location.coordinates.longitude}")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Find Location service.")
    parser.add_argument("query", nargs="?")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--bot", action="store_true", help="run the Telegram bot")
    args = parser.parse_args()

    configure_logging()
    if args.bot:
        return asyncio.run(run_bot())
    if not args.query:
        parser.error("query is required unless --bot is used")
    return asyncio.run(run_search(args.query, limit=args.limit))


async def run_bot() -> int:
    settings = get_settings()
    bot = create_bot(settings)
    geocoding_provider = create_geocoding_provider(settings)
    places_provider = create_places_provider(settings)
    dispatcher = create_dispatcher(
        SearchLocationUseCase(geocoding_provider),
        nearby_places=NearbyPlacesUseCase(places_provider),
        saved_places_repository=create_saved_place_repository(settings),
    )
    try:
        await dispatcher.start_polling(bot)
    finally:
        await geocoding_provider.close()
        await places_provider.close()
        await bot.session.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
