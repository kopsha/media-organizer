#!/usr/bin/env python
from argparse import ArgumentParser
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from mimetypes import guess_type
from pathlib import Path
from pprint import pprint
from types import SimpleNamespace

import exifread
from geopy.extra.rate_limiter import RateLimiter
from geopy.geocoders import Nominatim

TWO_DAYS = 2 * 24 * 3600
ONE_WEEK = 7 * 24 * 3600

geolocator = RateLimiter(
    Nominatim(user_agent="photo-location").reverse, min_delay_seconds=1 / 10
)


@lru_cache(maxsize=10_000)
def _reverse_cached(lat_rounded: float, lon_rounded: float) -> dict:
    return geolocator((lat_rounded, lon_rounded), language="en")


def approximate_reverse(latitude: float, longitude: float, precision: int = 2):
    lat, lon = round(latitude, precision), round(longitude, precision)
    return _reverse_cached(lat, lon)


def from_rational(value):
    """Convert exifread Ratio or tuple to float safely."""
    if isinstance(value, tuple):
        num, den = value
        return float(num) / float(den) if den != 0 else 0.0

    return float(value)


def dms_to_decimal(dms, ref):
    """
    Convert DMS (list of rationals) to decimal degrees.
    dms: exifread value like [Ratio(1,1), Ratio(30,1), Ratio(1234,100)]
    ref: 'N'/'S'/'E'/'W'
    """
    degrees = from_rational(dms[0])
    minutes = from_rational(dms[1]) if len(dms) > 1 else 0.0
    seconds = from_rational(dms[2]) if len(dms) > 2 else 0.0
    decimal = degrees + (minutes / 60.0) + (seconds / 3600.0)

    if ref in ("S", "W"):
        decimal = -decimal

    return decimal


def cherrypick_image_properties(exif_data: dict) -> dict:
    data = dict()

    if not exif_data:
        return data

    if original_time := str(exif_data.get("EXIF DateTimeOriginal")):
        timestamp = datetime.strptime(original_time, "%Y:%m:%d %H:%M:%S")
        data["created_at"] = timestamp.replace(tzinfo=timezone.utc)

    if "GPS GPSLatitude" in exif_data:
        lat_tag = exif_data.get("GPS GPSLatitude")
        lat_ref = exif_data.get("GPS GPSLatitudeRef")
        lon_tag = exif_data.get("GPS GPSLongitude")
        lon_ref = exif_data.get("GPS GPSLongitudeRef")

        latitude = dms_to_decimal(lat_tag.values, lat_ref)
        longitude = dms_to_decimal(lon_tag.values, lon_ref)
        data["precise_location"] = (latitude, longitude)

        location = approximate_reverse(latitude, longitude)
        data["approximate_location"] = location.raw.copy()

    return data


def scan_all_media_files(source: Path, destination: Path, use_copy: bool):
    """Organizes images into folders by year/month/day."""
    db = list()

    counter = 0
    for src_filepath in source.rglob("*"):
        counter += 1
        if counter > 1440:
            break

        if src_filepath.is_file():
            try:
                mime_type, _ = guess_type(src_filepath)
                print("---", src_filepath.name, "/", mime_type, "---")

                if not mime_type:
                    continue

                properties = dict()
                stat = src_filepath.stat()

                if mime_type.startswith("image"):
                    with open(src_filepath, "rb") as image_file:
                        exif_data = exifread.process_file(image_file, details=False)
                        image_props = cherrypick_image_properties(exif_data)
                        properties.update(image_props)

                if "created_at" not in properties:
                    timestamps = [stat.st_ctime, stat.st_mtime, stat.st_atime]
                    properties["created_at"] = datetime.fromtimestamp(
                        min(timestamps)
                    ).replace(tzinfo=timezone.utc)
                    if isinstance(properties["created_at"], float):
                        print(">>", timestamps, "<<")

                if "approximate_location" not in properties:
                    properties["approximate_location"] = {}

                properties["original_filename"] = src_filepath.stem
                properties["original_extension"] = src_filepath.suffix

                db.append(SimpleNamespace(**properties))

            except Exception as err:
                print(f"Cannot process {src_filepath}, reason: {err}")

    return db


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument("--copy", action="store_true", default=False)
    parser.add_argument("source")
    parser.add_argument("destination")
    args = parser.parse_args()

    source = Path(args.source).resolve()
    destination = Path(args.destination).resolve()
    print("Reorganizing", source, "to", destination)

    if not source.is_dir():
        parser.error(f"{source} folder does not exist.")
    elif not destination.is_dir():
        parser.error(f"{destination} folder does not exist.")
    elif source == destination:
        parser.error(f"Source and destination cannot be the same ({source})")

    files = scan_all_media_files(source, destination, args.copy)
    print()

    for meta in files:
        print(meta.created_at)

    files.sort(key=lambda fi: fi.created_at)

    last_date = files[0].created_at.date()
    address = files[0].approximate_location.get(
        "address",
        dict(municipality="no_gps", county="", postcode="no_gps"),
    )
    last_location = address["postcode"]

    event_key = f"{last_date.isoformat()}__{last_location}"
    event_name = "{date}__{name}".format(
        date=last_date.isoformat(),
        name="__".join(
            (
                address.get("village")
                or address.get("city")
                or address.get("town")
                or address.get("municipality"),
                address["county"],
            ),
        ).strip("_"),
    )
    event_name = event_name.lower().replace(" ", "-")
    print("new event", event_key, event_name)

    for props in files[1:]:
        current_date = props.created_at.date()
        address = props.approximate_location.get(
            "address",
            dict(municipality="no_gps", county="", postcode="no_gps"),
        )
        print("using address", address)
        current_location = address.get("postcode", "no_gps")

        delta = current_date - last_date
        if delta.days <= 2:
            # print("contd.", event_key)
            pass
        elif delta.days <= 7 and current_location == last_location:
            # print("contd. by location", event_key)
            pass
        else:
            event_key = f"{last_date.isoformat()}__{current_location}"
            event_name = "{date}__{name}".format(
                date=last_date.isoformat(),
                name="__".join(
                    (
                        address.get("village")
                        or address.get("city")
                        or address.get("town")
                        or address.get("municipality"),
                        address["county"],
                    ),
                ).strip("_"),
            )
            event_name = event_name.lower().replace(" ", "-")
            print("new event", event_key, event_name)

        last_date = props.created_at.date()
        last_location = address.get("postcode", "no_gps")

    print(f"Found {len(files)} files.")
