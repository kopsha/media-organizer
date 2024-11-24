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
        timestamp = os.path.getmtime(file_path)
        result = datetime.fromtimestamp(timestamp)
    print(".", end="")
    return result


def organize_images_by_date(source, destination, use_copy):
    """Organizes images into folders by year/month/day."""
    print("scanning", source)

    file_counter = 0
    for root, _, files in os.walk(source):
        for file in files:
            src_filepath = os.path.join(root, file)

            try:
                date_taken = get_image_date_taken(src_filepath)

                year = date_taken.strftime("%Y")
                month = date_taken.strftime("%m - %B")
                day_meta = "{day} - {name}".format(
                    day=date_taken.strftime("%d"), name=os.path.basename(root)
                )
                dst_folder = os.path.join(destination, year, month, day_meta)
                if not os.path.exists(dst_folder):
                    os.makedirs(dst_folder)

                dst_filepath = os.path.join(dst_folder, file)
                file_counter += 1
                if use_copy:
                    shutil.copy(src_filepath, dst_filepath)
                else:
                    shutil.move(src_filepath, dst_filepath)

            except Exception as err:
                print(f"Cannot process {src_filepath}, reason: {err}")

    return file_counter


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument("--copy", action="store_true", default=False)
    parser.add_argument("source")
    parser.add_argument("destination")
    args = parser.parse_args()

    print(args.source, "to", args.destination)
    if not os.path.isdir(args.source):
        parser.error(f"{args.source} folder does not exist.")
    elif not os.path.isdir(args.destination):
        parser.error(f"{args.destination} folder does not exists.")

    source = os.path.realpath(args.source)
    file_count = organize_images_by_date(source, args.destination, args.copy)
    print()
    print(f"Organized {file_count} files.")
