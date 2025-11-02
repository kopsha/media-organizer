#!/usr/bin/env python
import shutil
from argparse import ArgumentParser
from datetime import datetime, timezone
from mimetypes import guess_type
from pathlib import Path
from pprint import pprint
from uuid import uuid4

import exifread
from geopy.extra.rate_limiter import RateLimiter
from geopy.geocoders import Nominatim

geolocator = RateLimiter(
    Nominatim(user_agent="photo-location").reverse, min_delay_seconds=1 / 10
)


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
        location = geolocator((latitude, longitude), language="en")
        data["location"] = location.raw.copy()

    return data


def scan_image(filepath: Path) -> dict:
    return image_data


def scan_all_media_files(source: Path, destination: Path, use_copy: bool):
    """Organizes images into folders by year/month/day."""
    db = dict()

    for src_filepath in source.rglob("IMG_*"):
        if src_filepath.is_file():
            try:
                mime_type, _ = guess_type(src_filepath)
                print("---", src_filepath.name, "/", mime_type, "---")

                if not mime_type:
                    continue

                uid = uuid4()
                properties = dict()

                if mime_type.startswith("image"):
                    with open(src_filepath, "rb") as image_file:
                        exif_data = exifread.process_file(image_file, details=False)
                        image_props = cherrypick_image_properties(exif_data)
                        properties.update(image_props)

                properties["original_filename"] = src_filepath.stem
                properties["original_extension"] = src_filepath.suffix
                db[uid] = properties

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

    for uid, props in files.items():
        print(f"{uid}", props)

    print(f"Found {len(files)} files.")
