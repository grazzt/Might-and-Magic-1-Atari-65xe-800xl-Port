#!/usr/bin/env python3
"""Draw a C64 screen from memory, and compare it with a VICE screenshot.

The host oracle (tools/oracle.py) keeps the video chip's registers but draws
nothing. This turns its memory into the 320 x 200 picture a C64 would show:
text, hires bitmap or multicolour bitmap, from whichever 16 KB bank and at
whichever addresses the registers select. A frame may be split: the game shows
one bitmap above a raster line and another below it.

Pictures are lists of rows of colour numbers 0-15. PNG reading and writing
use only zlib. Comparison maps each pixel of a VICE screenshot (384 x 272,
with border) to the nearest of the sixteen colours.

  python3 tools/c64_screen.py VICE.png ORACLE.png    count differing pixels
"""
from pathlib import Path
import struct
import sys
import zlib

WIDTH, HEIGHT = 320, 200
BORDER_LEFT, BORDER_TOP = 32, 35        # of a VICE PAL screenshot
# The sixteen colours as VICE 3.7.1 writes them into a screenshot with its
# default video settings. Fifteen are measured from the screenshots under
# test-artifacts/c64 by matching them with pictures drawn here; blue (6) does
# not occur in them and is an estimate.
PALETTE = [(0, 0, 0), (255, 255, 255), (189, 81, 108), (145, 245, 220),
           (184, 85, 246), (119, 220, 70), (72, 58, 255), (255, 255, 92),
           (196, 121, 45), (138, 103, 0), (240, 143, 166), (119, 119, 119),
           (165, 165, 165), (195, 255, 153), (136, 152, 255), (213, 213, 213)]


class Segment:
    """Rows first..last-1 of the picture, drawn with one set of register values."""

    def __init__(self, first, last, bank, memory, control1, control2):
        self.first, self.last = first, last
        self.base = bank * 0x4000
        self.screen = self.base + (memory >> 4) * 0x400
        self.bitmap = self.base + (memory >> 3 & 1) * 0x2000
        self.charset = self.base + (memory >> 1 & 7) * 0x800
        self.is_bitmap, self.multicolour = bool(control1 & 0x20), bool(control2 & 0x10)
        # Banks 0 and 2 show the character ROM at $1000-$1FFF.
        self.rom_charset = bank in (0, 2) and 0x1000 <= self.charset - self.base < 0x2000


def render(ram, color, chargen, segments, background):
    """ram: 64 KB of RAM; color: 1000 colour nibbles; returns 200 rows of 320."""
    rows = [bytearray(WIDTH) for _ in range(HEIGHT)]
    for seg in segments:
        for y in range(seg.first, seg.last):
            row, cell_row, line = rows[y], y // 8, y % 8
            for column in range(40):
                cell = cell_row * 40 + column
                matrix, nibble = ram[seg.screen + cell], color[cell] & 15
                x = column * 8
                if seg.is_bitmap:
                    bits = ram[seg.bitmap + cell * 8 + line]
                    if seg.multicolour:
                        colours = (background, matrix >> 4, matrix & 15, nibble)
                        for pair in range(4):
                            row[x + pair * 2] = row[x + pair * 2 + 1] = colours[bits >> (6 - pair * 2) & 3]
                    else:
                        for bit in range(8):
                            row[x + bit] = matrix >> 4 if bits >> (7 - bit) & 1 else matrix & 15
                else:
                    offset = seg.charset - seg.base - 0x1000 + matrix * 8 + line
                    bits = chargen[offset] if seg.rom_charset else ram[seg.charset + matrix * 8 + line]
                    for bit in range(8):
                        row[x + bit] = nibble if bits >> (7 - bit) & 1 else background
    return rows


def _chunk(kind, body):
    return struct.pack('>I', len(body)) + kind + body + struct.pack('>I', zlib.crc32(kind + body))


def write_png(path, rows):
    """An indexed PNG with the sixteen C64 colours."""
    raw = b''.join(b'\0' + bytes(row) for row in rows)
    header = struct.pack('>IIBBBBB', len(rows[0]), len(rows), 8, 3, 0, 0, 0)
    palette = b''.join(bytes(c) for c in PALETTE)
    with open(path, 'wb') as out:
        out.write(b'\x89PNG\r\n\x1a\n' + _chunk(b'IHDR', header) + _chunk(b'PLTE', palette)
                  + _chunk(b'IDAT', zlib.compress(raw, 9)) + _chunk(b'IEND', b''))


def read_png(path):
    """(width, height, rows of (r, g, b)) for an 8-bit RGB, RGBA or indexed PNG."""
    data = Path(path).read_bytes()
    position, body, palette = 8, b'', None
    while position < len(data):
        length, kind = struct.unpack('>I4s', data[position:position + 8])
        chunk = data[position + 8:position + 8 + length]
        if kind == b'IHDR':
            width, height, depth, colour_type = struct.unpack('>IIBB', chunk[:10])
        elif kind == b'PLTE':
            palette = [tuple(chunk[i:i + 3]) for i in range(0, len(chunk), 3)]
        elif kind == b'IDAT':
            body += chunk
        position += 12 + length
    size = {2: 3, 6: 4, 3: 1}[colour_type]
    if depth != 8:
        raise ValueError('Only 8-bit PNGs are read')
    raw = zlib.decompress(body)
    stride = width * size
    previous, rows = bytearray(stride), []
    for y in range(height):
        kind = raw[y * (stride + 1)]
        line = bytearray(raw[y * (stride + 1) + 1:(y + 1) * (stride + 1)])
        for i in range(stride):
            left = line[i - size] if i >= size else 0
            up = previous[i]
            corner = previous[i - size] if i >= size else 0
            if kind == 1:
                line[i] = line[i] + left & 255
            elif kind == 2:
                line[i] = line[i] + up & 255
            elif kind == 3:
                line[i] = line[i] + (left + up) // 2 & 255
            elif kind == 4:
                estimate = left + up - corner
                distances = (abs(estimate - left), abs(estimate - up), abs(estimate - corner))
                line[i] = line[i] + (left, up, corner)[distances.index(min(distances))] & 255
        previous = line
        if size == 1:
            rows.append([palette[v] for v in line])
        else:
            rows.append([tuple(line[i:i + 3]) for i in range(0, stride, size)])
    return width, height, rows


def colour_numbers(rows):
    """Map (r, g, b) pixels to the nearest of the sixteen colours."""
    cache = {}
    out = []
    for row in rows:
        line = bytearray()
        for pixel in row:
            if pixel not in cache:
                cache[pixel] = min(range(16), key=lambda i: sum((a - b) ** 2 for a, b in zip(PALETTE[i], pixel)))
            line.append(cache[pixel])
        out.append(line)
    return out


def vice_picture(path):
    """The 320 x 200 picture area of a VICE PAL screenshot, as colour numbers."""
    width, height, rows = read_png(path)
    if (width, height) != (384, 272):
        raise ValueError(f'{path}: expected a 384 x 272 VICE screenshot')
    inner = [row[BORDER_LEFT:BORDER_LEFT + WIDTH] for row in rows[BORDER_TOP:BORDER_TOP + HEIGHT]]
    return colour_numbers(inner)


def differences(a, b):
    """Number of differing pixels, and the rows that hold any."""
    rows = [y for y in range(HEIGHT) if bytes(a[y]) != bytes(b[y])]
    return sum(x != y for r in rows for x, y in zip(a[r], b[r])), rows


def main():
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    vice = vice_picture(sys.argv[1])
    width, height, rows = read_png(sys.argv[2])
    count, where = differences(vice, colour_numbers(rows))
    print(f'{count} of {WIDTH * HEIGHT} pixels differ' + (f', in rows {where[0]}-{where[-1]}' if where else ''))


if __name__ == '__main__':
    main()
