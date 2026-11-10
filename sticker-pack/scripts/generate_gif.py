"""Generate one native GPT Image 2.6 GIF from an approved sticker PNG."""

import argparse
import base64
import binascii
import io
import json
import os
import uuid
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from PIL import Image, ImageSequence


MODELS = ("gpt-image-2.6-sunburst", "gpt-image-2.6-flare")
EDIT_URL = "https://api.openai.com/v1/images/edits"


def edit_request(key, png, fields):
    boundary = uuid.uuid4().hex
    parts = [
        (
            f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n'
            f"{value}\r\n"
        ).encode("utf-8")
        for name, value in fields.items()
    ]
    parts.extend(
        [
            (
                f'--{boundary}\r\nContent-Disposition: form-data; '
                'name="image[]"; filename="sticker.png"\r\n'
                "Content-Type: image/png\r\n\r\n"
            ).encode("ascii"),
            png,
            f"\r\n--{boundary}--\r\n".encode("ascii"),
        ]
    )
    return Request(
        EDIT_URL,
        data=b"".join(parts),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        method="POST",
    )


def read_gif(response):
    try:
        animation = base64.b64decode(response["data"][0]["b64_json"], validate=True)
        with Image.open(io.BytesIO(animation)) as image:
            if image.format != "GIF" or image.n_frames < 2:
                raise ValueError("Expected a GIF with at least two frames.")
            for frame in ImageSequence.Iterator(image):
                frame.load()
    except (KeyError, IndexError, TypeError, OSError, ValueError, EOFError, binascii.Error) as error:
        raise ValueError("The API did not return a readable animated GIF.") from error
    return animation


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path, help="Approved single-cell PNG")
    parser.add_argument("prompt", type=Path, help="UTF-8 prompt text file")
    parser.add_argument("output", type=Path, help="New GIF file")
    parser.add_argument("--model", choices=MODELS, default=MODELS[0])
    parser.add_argument("--size", type=int, default=512, help="Square frame side in pixels")
    parser.add_argument("--frame-count", type=int, default=9)
    parser.add_argument("--frame-duration-ms", type=int, default=200)
    args = parser.parse_args()

    if not 2 <= args.frame_count <= 16:
        parser.error("--frame-count must be between 2 and 16.")
    if not 20 <= args.frame_duration_ms <= 2000:
        parser.error("--frame-duration-ms must be between 20 and 2000.")
    if args.size <= 0 or args.size % 16:
        parser.error("--size must be positive and divisible by 16.")
    if args.output.suffix.lower() != ".gif" or args.output.exists():
        parser.error("Choose a new output path ending in .gif.")

    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key:
        parser.error("Set OPENAI_API_KEY in the execution environment.")

    try:
        prompt = args.prompt.read_text(encoding="utf-8-sig").strip()
        if not prompt:
            raise ValueError("The prompt is empty.")
        png = args.image.read_bytes()
        with Image.open(io.BytesIO(png)) as image:
            if image.format != "PNG" or image.n_frames != 1:
                raise ValueError("Expected one static PNG.")
            image.verify()

        fields = {
            "model": args.model,
            "prompt": prompt,
            "output_format": "gif",
            "n": 1,
            "size": f"{args.size}x{args.size}",
            "frame_count": args.frame_count,
            "frame_duration_ms": args.frame_duration_ms,
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with urlopen(edit_request(key, png, fields), timeout=300) as response:
            animation = read_gif(json.load(response))
        with args.output.open("xb") as output:
            output.write(animation)
    except HTTPError as error:
        request_id = error.headers.get("x-request-id", "unavailable")
        parser.exit(1, f"Image API returned HTTP {error.code}. Request ID: {request_id}\n")
    except (URLError, OSError, ValueError, Image.DecompressionBombError) as error:
        parser.exit(1, f"Could not generate GIF: {error}\n")

    print(f"Saved {args.output}")


if __name__ == "__main__":
    main()

