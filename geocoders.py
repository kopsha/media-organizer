import json
from logging import getLogger
from os import environ
from pathlib import Path

from geopy.extra.rate_limiter import RateLimiter
from geopy.geocoders import Nominatim

logger = getLogger(__name__)
_STORAGE = Path(environ.get("USE_STORAGE", "."))


class CachedGeolocator:
    user_agent = "Schrödinger's Coordinates Storage"
    cache_filename = "_cache_db.json"
    precision = 2

    def __init__(self, min_delay_seconds: float = 1 / 10):
        self.geolocator = RateLimiter(
            Nominatim(user_agent=self.user_agent).reverse,
            min_delay_seconds=min_delay_seconds,
        )
        self.storage = _STORAGE / Path(self.cache_filename)
        self.cache = self._load()

    def _load(self) -> dict:
        data = dict()
        if self.storage.exists():
            with open(self.storage, "r", encoding="utf-8") as file:
                try:
                    data = json.load(file)
                    logger.info(f"Loaded {len(data)} cache entries.")
                except json.JSONDecodeError:
                    logger.info("Corrupted cache, starting clean")

        return data

    def _save(self):
        with open(self.storage, "w", encoding="utf-8") as file:
            json.dump(self.cache, file, indent=4, ensure_ascii=False)

    def reverse(self, lat: float, lon: float) -> dict:
        key = f"{lat:.{self.precision}f},{lon:.{self.precision}f}"

        if key in self.cache:
            return self.cache[key]

        lat_r, lon_r = round(lat, self.precision), round(lon, self.precision)
        location = self.geolocator((lat_r, lon_r), exactly_one=True)

        if not location:
            logger.warning("Some error occured with the geo locator.")
            return {}

        self.cache[key] = location.raw
        self._save()
        return self.cache[key]
