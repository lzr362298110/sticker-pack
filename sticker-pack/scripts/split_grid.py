"""Crop one approved 3-by-3 sticker sheet into nine numbered PNGs."""

import argparse
import tempfile
from pathlib import Path

from PIL import Image, ImageOps


def crop_ranges(values, length, axis):
    if values is None:
        edges = [length * index // 3 for index in range(4)]
        return list(zip(edges[:-1], edges[1:]))

    ranges = []
    previous_end = 0
    for value in values:
        start, end = map(int, value.split(":"))
        if not previous_end <= start < end <= length:
            raise ValueError(
                f"{axis} ranges must be ordered, non-overlapping and inside 0:{length}."
            )
        ranges.append((start, end))
        previous_end = end
    return ranges


def split_sheet(source, out_dir, sheet, x_ranges, y_ranges, size=None):
    destination = out_dir / sheet
    if destination.exists():
        raise FileExistsError(f"Choose a new output location: {destination}")

    with Image.open(source) as original:
        if getattr(original, "n_frames", 1) != 1:
            raise ValueError("Expected one static sticker sheet.")
        oriented = ImageOps.exif_transpose(original)
        if min(oriented.size) < 3:
            raise ValueError("The image is too small to split into nine cells.")

        columns = crop_ranges(x_ranges, oriented.width, "Horizontal")
        rows = crop_ranges(y_ranges, oriented.height, "Vertical")
        has_alpha = "A" in oriented.getbands() or "transparency" in oriented.info
        image = oriented.convert("RGBA" if has_alpha else "RGB")

        out_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".split-", dir=out_dir) as temporary:
            staging = Path(temporary) / sheet
            staging.mkdir()
            for row, (top, bottom) in enumerate(rows, start=1):
                for column, (left, right) in enumerate(columns, start=1):
                    name = f"{sheet}-R{row}C{column}.png"
                    cell = image.crop((left, top, right, bottom))
                    if size is not None:
                        padding = (0, 0, 0, 0) if has_alpha else cell.getpixel((0, 0))
                        cell = ImageOps.pad(
                            cell, (size, size), Image.Resampling.LANCZOS, color=padding
                        )
                    cell.save(staging / name)
            staging.rename(destination)

    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path, help="Approved static sticker sheet")
    parser.add_argument("--sheet", required=True, choices=("01", "02", "03", "04"))
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--x-ranges", nargs=3, metavar="START:END")
    parser.add_argument("--y-ranges", nargs=3, metavar="START:END")
    parser.add_argument("--size", type=int, help="Square output edge in pixels")
    args = parser.parse_args()
    if args.size is not None and args.size < 1:
        parser.error("--size must be a positive integer")

    try:
        destination = split_sheet(
            args.image, args.out_dir, args.sheet, args.x_ranges, args.y_ranges, args.size
        )
    except (OSError, ValueError, Image.DecompressionBombError) as error:
        parser.exit(1, f"Could not split sticker sheet: {error}\n")

    print(f"Saved nine PNGs to {destination}")


if __name__ == "__main__":
    main()

