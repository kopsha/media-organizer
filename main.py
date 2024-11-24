#!/usr/bin/env python
import os
import shutil
from argparse import ArgumentParser
from datetime import datetime

from PIL import Image
from PIL.ExifTags import TAGS


def get_image_date_taken(file_path):
    """Extracts the date taken from image metadata."""
    result = None
    try:
        image = Image.open(file_path)
        exif_data = image._getexif() if hasattr(image, "_getexit") else dict()
        for tag_id, value in exif_data.items():
            tag_name = TAGS.get(tag_id, tag_id)
            if tag_name == "DateTimeOriginal":
                result = datetime.strptime(value, "%Y:%m:%d %H:%M:%S")
                break
        else:
            raise ValueError(f"{file_path} has no exif data.")
    except Exception as err:
        print("WARN:", err)
        timestamp = os.path.getmtime(file_path)
        result = datetime.fromtimestamp(timestamp)
    return result


def organize_images_by_date(source, destination, use_copy):
    """Organizes images into folders by year/month/day."""
    os.makedirs(destination)
    print("scanning", source)

    for root, _, files in os.walk(source):
        for file in files:
            src_filepath = os.path.join(root, file)

            try:
                date_taken = get_image_date_taken(src_filepath)

                # Create a folder structure based on year/month/day
                year = date_taken.strftime("%Y")
                month = date_taken.strftime("%m - %B")
                day_meta = "{day} - {name}".format(
                    day=date_taken.strftime("%d"), name=os.path.basename(root)
                )

                dst_folder = os.path.join(destination, year, month, day_meta)
                if not os.path.exists(dst_folder):
                    os.makedirs(dst_folder)

                dst_filepath = os.path.join(dst_folder, file)
                if use_copy:
                    shutil.copy(src_filepath, dst_filepath)
                else:
                    shutil.move(src_filepath, dst_filepath)

            except Exception as err:
                print(f"Cannot process {src_filepath}, reason: {err}")


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument("--copy", action="store_true", default=False)
    parser.add_argument("source")
    parser.add_argument("destination")
    args = parser.parse_args()

    print(args.source, "to", args.destination)
    if not os.path.isdir(args.source):
        parser.error(f"{args.source} is not a folder.")
    elif os.path.exists(args.destination):
        parser.error(f"{args.destination} folder already exists.")

    source = os.path.realpath(args.source)
    organize_images_by_date(source, args.destination, args.copy)
