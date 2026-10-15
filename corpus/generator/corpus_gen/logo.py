"""A small school logo as PNG bytes, built with the standard library only."""

import struct
import zlib

SIZE = 64


def _chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))


def _pixel(x: int, y: int) -> bytes:
    """Return a blue disc with a white open book on a white background."""
    centre = (SIZE - 1) / 2
    inside_disc = (x - centre) ** 2 + (y - centre) ** 2 <= (SIZE / 2 - 2) ** 2
    in_book = 20 <= y <= 42 and 14 <= x <= 49 and x not in (31, 32)
    if inside_disc and not in_book:
        return bytes((0x1F, 0x4E, 0x9A))
    return b"\xff\xff\xff"


def logo_png() -> bytes:
    """Return a 64x64 RGB PNG: deterministic, a few hundred bytes."""
    rows = b"".join(b"\x00" + b"".join(_pixel(x, y) for x in range(SIZE)) for y in range(SIZE))
    header = struct.pack(">IIBBBBB", SIZE, SIZE, 8, 2, 0, 0, 0)  # 8-bit RGB
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", header)
        + _chunk(b"IDAT", zlib.compress(rows, 9))
        + _chunk(b"IEND", b"")
    )
