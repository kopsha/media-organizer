#!/usr/bin/env python
import shutil
from argparse import ArgumentParser
from datetime import datetime, timezone
from mimetypes import guess_type
from pathlib import Path
from pprint import pprint

import exifread
from geopy.extra.rate_limiter import RateLimiter
from geopy.geocoders import Nominatim

geolocator = RateLimiter(
    Nominatim(user_agent="photo-location").reverse, min_delay_seconds=1/10
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


def from_exif_info(exif_data: dict) -> dict:
    if not exif_data:
        return {}

    data = dict()

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
    with open(filepath, "rb") as image_file:
        exif_data = exifread.process_file(image_file, details=False)
        image_data = from_exif_info(exif_data)

    return image_data


def get_image_date_taken(filepath: Path):
    """Extracts the date taken from image metadata."""
    result = None
    try:
        # Attempt to read exif with pillow
        image = Image.open(filepath)
        exif_data = image._getexif() if hasattr(image, "_getexif") else dict()
        pprint(exif_data)
        for tag_id, value in exif_data.items():
            tag_name = TAGS.get(tag_id, tag_id)
            if tag_name == "DateTimeOriginal":
                result = datetime.strptime(value, "%Y:%m:%d %H:%M:%S")
                break
        else:
            raise ValueError(f"{filepath} has no exif data.")
    except Exception:
        timestamp = filepath.stat().st_mtime
        result = datetime.fromtimestamp(timestamp)
    print(".", end="")
    return result


def organize_images_by_date(source: Path, destination: Path, use_copy: bool):
    """Organizes images into folders by year/month/day."""
    file_counter = 0
    media_types_trans = dict(
        image="poze",
        video="video",
        audio="muzica",
    )
    seen = set()
    for src_filepath in source.rglob("*"):
        if file_counter > 50:
            break

        if src_filepath.is_file():
            try:
                full_mime_type, _ = guess_type(src_filepath)
                print("---", src_filepath, "/", full_mime_type, "---")
                if not full_mime_type:
                    continue

                if full_mime_type.startswith("image"):
                    data = scan_image(src_filepath)
                    print(data)

                # date_taken = get_image_date_taken(src_filepath)
                # year = date_taken.strftime("%Y")
                # month = date_taken.strftime("%m - %B")
                #
                # previous_name = src_filepath.parent.name.strip()
                # day_prefix = f"{date_taken.day:02} - "
                # if previous_name.startswith(day_prefix):
                #     previous_name = previous_name[len(day_prefix) :]
                #
                # day_meta = "{day:02} - {name}".format(
                #     day=date_taken.day, name=previous_name
                # )
                #
                # media_type = (full_mime_type or "/").split("/")[0]
                # category = media_types_trans.get(media_type, "altele")
                #
                # # prepare target folder
                # if category == "muzica":
                #     dst_folder = destination / category
                # else:
                #     dst_folder = destination / category / year / month / day_meta
                #
                # if dst_folder not in seen:
                #     dst_folder.mkdir(parents=True, exist_ok=True)
                #     seen.add(dst_folder)
                #
                # # move/copy target file
                # dst_filepath = dst_folder / src_filepath.name
                #
                # if dst_filepath.exists():
                #     print("skip", dst_filepath, "already exists.")
                #     continue

                file_counter += 1
                # if use_copy:
                #     shutil.copy(src_filepath, dst_filepath)
                # else:
                #     shutil.move(src_filepath, dst_filepath)

            except Exception as err:
                print(f"Cannot process {src_filepath}, reason: {err}")

    return file_counter, len(seen)


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

    files, folders = organize_images_by_date(source, destination, args.copy)
    print()
    print(f"Organized {files} files in {folders} folders.")
