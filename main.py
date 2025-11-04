#!/usr/bin/env python
from argparse import ArgumentParser
from datetime import datetime, timedelta, timezone
from itertools import groupby
from logging import basicConfig, getLogger
from mimetypes import guess_type
from operator import attrgetter
from pathlib import Path
from pprint import pprint
from types import SimpleNamespace
from typing import Any

import exifread

from geocoders import CachedGeolocator

logger = getLogger("Organizer")

TWO_DAYS = 2 * 24 * 3600
ONE_WEEK = 7 * 24 * 3600

geolocator = CachedGeolocator()


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


def parse_exif_info(data: dict) -> dict:
    props = dict()

    if not data:
        return props

    if original_time := data.get("EXIF DateTimeOriginal"):
        timestamp = datetime.strptime(str(original_time), "%Y:%m:%d %H:%M:%S")
        props["created_at"] = timestamp.replace(tzinfo=timezone.utc)

    if "GPS GPSLatitude" in data:
        lat_tag = data.get("GPS GPSLatitude")
        lat_ref = data.get("GPS GPSLatitudeRef")
        lon_tag = data.get("GPS GPSLongitude")
        lon_ref = data.get("GPS GPSLongitudeRef")

        latitude = dms_to_decimal(lat_tag.values, lat_ref)
        longitude = dms_to_decimal(lon_tag.values, lon_ref)
        props["precise_location"] = (latitude, longitude)

    return props


def parse_image(filepath: Path):
    with open(filepath, "rb") as image_file:
        exif_data = exifread.process_file(image_file, details=False, strict=False)
        props = parse_exif_info(exif_data)
        return props


def stat_created_at(filepath: Path) -> datetime:
    stat = filepath.stat()
    earliest = min(stat.st_ctime, stat.st_mtime, stat.st_atime)
    return datetime.fromtimestamp(earliest).replace(tzinfo=timezone.utc)


def scan_all_media_files(source: Path, destination: Path, use_copy: bool):
    """Organizes images into folders by year/month/day."""
    db = list()
    logger.info(f" scanning {source}")

    counter = 0
    for filepath in source.rglob("*"):
        counter += 1

        if filepath.is_dir() or filepath.match(".*") or filepath.match("__*"):
            continue

        if filepath.is_file():
            mime_type, _ = guess_type(filepath)

            if not mime_type:
                continue

            logger.debug(f" reading {filepath.name} [{mime_type}]")

            properties: dict[str, Any] = dict(
                original_path=str(filepath.relative_to(source)),
                original_filename=filepath.stem,
                original_extension=filepath.suffix,
            )

            if mime_type.startswith("image"):
                image_props = parse_image(filepath)
                properties.update(image_props)

            if "created_at" not in properties:
                properties["created_at"] = stat_created_at(filepath)

            if "precise_location" in properties:
                location = geolocator.reverse(*properties["precise_location"])
            else:
                location = {}

            properties["approximate_location"] = location
            address = location.get("address", {"ISO3166-2-lvl4": "RO"})

            # NOTE: pre-compute relevant keys
            properties["location_key"] = "{}__{}".format(
                address.get("ISO3166-2-lvl4"), address.get("postcode")
            )

            db.append(SimpleNamespace(**properties))

    db.sort(key=lambda props: props.created_at)

    return db


def trace_events_timeline(files_db: list):
    if not files_db:
        return

    first, *remaining = files_db
    this_address = first.approximate_location.get("address", {})
    last_event = SimpleNamespace(
        created=first.created_at.date(),
        location_key=first.location_key,
        name=", ".join(
            (
                this_address.get("village")
                or this_address.get("town")
                or this_address.get("city")
                or this_address.get("municipality")
                or first.original_filename,
                this_address.get("county", ""),
                first.created_at.strftime("%b %d, %Y"),
            )
        ).strip(),
        key="{}__{}".format(first.created_at.date().isoformat(), first.location_key),
    )
    first.event = last_event

    for meta in remaining:
        delta = meta.created_at.date() - last_event.created
        same_location = (
            meta.approximate_location and meta.location_key == last_event.location_key
        )

        if delta.days >= 7 or not same_location:
            this_address = meta.approximate_location.get("address", {})
            last_event = SimpleNamespace(
                created=meta.created_at.date(),
                location_key=meta.location_key,
                name=", ".join(
                    (
                        this_address.get("village")
                        or this_address.get("town")
                        or this_address.get("city")
                        or this_address.get("municipality")
                        or meta.original_filename,
                        this_address.get("county", "RO"),
                        meta.created_at.strftime("%b %d, %Y"),
                    )
                ).strip(),
                key="{}__{}".format(
                    meta.created_at.date().isoformat(), meta.location_key
                ),
            )

        meta.event = last_event


if __name__ == "__main__":
    basicConfig(level="INFO")

    parser = ArgumentParser()
    parser.add_argument("--copy", action="store_true", default=False)
    parser.add_argument("source")
    parser.add_argument("destination")
    args = parser.parse_args()

    source = Path(args.source).resolve()
    destination = Path(args.destination).resolve()

    if not source.is_dir():
        parser.error(f"{source} folder does not exist.")
    elif not destination.is_dir():
        parser.error(f"{destination} folder does not exist.")
    elif source == destination:
        parser.error(f"Source and destination cannot be the same ({source})")

    files_meta = scan_all_media_files(source, destination, args.copy)
    trace_events_timeline(files_meta)

    events = dict()

    for key, metas in groupby(files_meta, key=attrgetter("event.key")):
        events[key] = list(metas)

    for key, metas in events.items():
        print(key, repr(metas[0].event.name), "has", len(metas), "files")

    print(".. done ..")
