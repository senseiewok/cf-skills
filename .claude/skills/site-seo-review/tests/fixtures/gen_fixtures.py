"""Generate the binary fixture the tests need: a valid 1200x630 PNG for og:image. Standard library only.

Usage:  python gen_fixtures.py [GOOD_SITE_DIR]      (default: the `good` folder next to this file)
Import: png(width, height) -> bytes               a valid 8-bit greyscale PNG of one flat shade
        write_all(root) -> [paths written]         writes images/share.png (1200x630) under root

The checker reads only the IHDR chunk (bytes 16-24: width and height, big-endian), so the image
content does not matter; it is still a complete, viewable PNG. CRCs are computed at run time.
"""
import struct
import sys
import zlib
from pathlib import Path

SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _chunk(tag, data):
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)


def png(width, height):
    """A valid 8-bit greyscale PNG, `width` x `height`, every pixel mid-grey."""
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)   # bit depth 8, colour type 0 (grey), no interlace
    row = b"\x00" + b"\x80" * width                                  # filter type 0, then the pixels
    idat = zlib.compress(row * height, 9)
    return SIGNATURE + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", idat) + _chunk(b"IEND", b"")


def write_all(root):
    root = Path(root)
    out = root / "images" / "share.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(png(1200, 630))
    return [out]


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent / "good"
    for p in write_all(target):
        print(p)
