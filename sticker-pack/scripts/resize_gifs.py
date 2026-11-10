"""Export animated GIFs at 240 x 240 without stretching the animation."""

import argparse
import tempfile
from pathlib import Path

from PIL import Image, ImageOps, ImageSequence


SIZE = (240, 240)
TRANSPARENT_INDEX = 255


def gif_frame(image, transparent):
    palette_size = 255 if transparent else 256
    indexed = image.convert("RGB").quantize(colors=palette_size)
    if transparent:
        palette = indexed.getpalette()
        indexed.putpalette(palette + [0] * (768 - len(palette)))
        mask = image.getchannel("A").point(lambda alpha: 255 if alpha < 128 else 0)
        indexed.paste(TRANSPARENT_INDEX, mask=mask)
        indexed.info["transparency"] = TRANSPARENT_INDEX
    return indexed


def resize_gif(source, destination):
    frames = []
    durations = []
    has_transparency = False
    with Image.open(source) as original:
        if original.format != "GIF" or original.n_frames < 2:
            raise ValueError(f"{source.name} must be an animated GIF.")
        loop = original.info.get("loop")
        for frame in ImageSequence.Iterator(original):
            durations.append(frame.info.get("duration", 0))
            rgba = frame.convert("RGBA")
            has_transparency |= rgba.getchannel("A").getextrema()[0] < 255
            frames.append(rgba)

    # GIF stores one transparent color per frame. Use the same reserved index
    # throughout so cleared pixels cannot reveal remnants of earlier frames.
    padding = (0, 0, 0, 0) if has_transparency else frames[0].getpixel((0, 0))
    encoded = [
        gif_frame(ImageOps.pad(frame, SIZE, Image.Resampling.LANCZOS, color=padding),
                  has_transparency)
        for frame in frames
    ]
    options = {"loop": loop} if loop is not None else {}
    if has_transparency:
        options.update(transparency=TRANSPARENT_INDEX, background=TRANSPARENT_INDEX)

    encoded[0].save(
        destination,
        save_all=True,
        append_images=encoded[1:],
        duration=durations,
        disposal=2 if has_transparency else 1,
        optimize=False,
        **options,
    )
    with Image.open(destination) as result:
        if result.size != SIZE or not result.is_animated:
            raise ValueError(f"{source.name} lost its animation at 240 x 240.")


def resize_batch(sources, output):
    if output.exists():
        raise FileExistsError(f"Choose a new output directory: {output}")
    names = {source.name.casefold() for source in sources}
    if len(names) != len(sources):
        raise ValueError("Input GIF filenames must be unique.")

    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".gif-", dir=output.parent) as temporary:
        staging = Path(temporary) / "gifs"
        staging.mkdir()
        for source in sources:
            resize_gif(source, staging / source.name)
        staging.rename(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+", type=Path, help="GIF files or folders")
    parser.add_argument("--out-dir", required=True, type=Path)
    args = parser.parse_args()

    try:
        sources = []
        for path in args.inputs:
            if path.is_dir():
                sources.extend(sorted(file for file in path.iterdir()
                                      if file.is_file() and file.suffix.lower() == ".gif"))
            elif path.is_file() and path.suffix.lower() == ".gif":
                sources.append(path)
            else:
                raise ValueError(f"Expected a GIF file or folder: {path}")
        if not sources:
            raise ValueError("No GIF files found.")
        resize_batch(sources, args.out_dir)
    except (OSError, ValueError, Image.DecompressionBombError) as error:
        parser.exit(1, f"Could not resize GIFs: {error}\n")

    print(f"Saved {len(sources)} animated GIFs to {args.out_dir}")


if __name__ == "__main__":
    main()
