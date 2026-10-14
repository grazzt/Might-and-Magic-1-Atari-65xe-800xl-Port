#!/usr/bin/env python3
"""Decode G64 tracks directly: sector headers, header gaps and data blocks.

Independent of VICE's c1541. Reports what a D64 cannot hold and this game's
loader uses: the per-sector header disk ID and the bytes after each header.
G64 layout as written by VICE: a 12-byte header, a table of track offsets and
one of speed zones, then each track as a 16-bit length and its GCR bytes.
tools/analyze_c64.py's c1541 extraction is the cross-check: 2,732 sectors agree.
"""
import argparse
import json
from pathlib import Path
import struct

GCR = {0x0a: 0, 0x0b: 1, 0x12: 2, 0x13: 3, 0x0e: 4, 0x0f: 5, 0x16: 6, 0x17: 7,
       0x09: 8, 0x19: 9, 0x1a: 10, 0x1b: 11, 0x0d: 12, 0x1d: 13, 0x1e: 14, 0x15: 15}


class G64:
    def __init__(self, data):
        if data[:8] != b'GCR-1541':
            raise ValueError('Not a G64 image')
        count = data[9]
        self.offsets = struct.unpack(f'<{count}I', data[12:12 + 4 * count])
        self.speeds = struct.unpack(f'<{count}I', data[12 + 4 * count:12 + 8 * count])
        self.data = data

    def raw(self, halftrack):
        """GCR bytes of a half-track index (0 = track 1, 2 = track 2, ...)."""
        offset = self.offsets[halftrack]
        if not offset:
            return None
        length = struct.unpack('<H', self.data[offset:offset + 2])[0]
        return self.data[offset + 2:offset + 2 + length]

    def blocks(self, halftrack):
        """Yield (bit position, bits after the sync mark) around the whole track."""
        raw = self.raw(halftrack)
        if not raw:
            return
        bits = ''.join(f'{b:08b}' for b in raw)
        size = len(bits)
        ring = bits * 3  # a block or sync mark may wrap around the index hole
        position = ring.find('0')  # never start inside a sync mark
        seen = set()
        while position < size * 2:
            start = ring.find('1' * 10, position)
            if start < 0 or start >= size * 2:
                break
            end = start
            while ring[end] == '1':
                end += 1
            if end % size not in seen:
                seen.add(end % size)
                yield end % size, ring[end:end + size]
            position = end

    @staticmethod
    def decode(bits, count):
        """Decode count bytes; None where a 5-bit group is not valid GCR."""
        out = []
        for i in range(count):
            hi, lo = (GCR.get(int(bits[i * 10 + j:i * 10 + j + 5], 2)) for j in (0, 5))
            out.append(None if hi is None or lo is None else hi << 4 | lo)
        return out

    def sectors(self, halftrack):
        """Decode headers and the data block following each one."""
        result, header = [], None
        blocks = list(self.blocks(halftrack))
        kinds = [self.decode(bits, 1)[0] for _, bits in blocks]
        if 0x08 in kinds:  # start at a header so a wrapped data block pairs up
            first_header = kinds.index(0x08)
            blocks = blocks[first_header:] + blocks[:first_header]
        for position, bits in blocks:
            first = self.decode(bits, 1)[0]
            if first == 0x08:
                h = self.decode(bits, 8)
                ok = None not in h and h[1] == h[2] ^ h[3] ^ h[4] ^ h[5]
                gap = bytes(int(bits[80 + i * 8:88 + i * 8], 2) for i in range(9))
                header = {'position': position, 'track': h[3], 'sector': h[2],
                          'id': [h[5], h[4]], 'header_ok': ok, 'gap': gap.hex()}
                result.append(header)
            elif first == 0x07 and header is not None and 'data' not in header:
                d = self.decode(bits, 258)
                payload = d[1:257]
                good = None not in d
                check = 0
                for b in payload if good else []:
                    check ^= b
                header['data'] = bytes(payload) if good else None
                header['data_ok'] = good and check == d[257]
        return result


def sector_image(disk):
    """All 683 standard sectors in D64 order; fails on a missing or bad one."""
    from d64 import SECTORS
    out = bytearray()
    for track in range(1, 36):
        found = {s['sector']: s for s in disk.sectors((track - 1) * 2)
                 if s['header_ok'] and s['track'] == track and s.get('data_ok')}
        for sector in range(SECTORS[track]):
            if sector not in found:
                raise ValueError(f'No readable sector {track}/{sector}')
            out.extend(found[sector]['data'])
    return bytes(out)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image', type=Path)
    args = parser.parse_args()
    disk = G64(args.image.read_bytes())
    report = []
    for halftrack in range(len(disk.offsets)):
        sectors = disk.sectors(halftrack)
        if disk.raw(halftrack) is None:
            continue
        report.append({'track': halftrack / 2 + 1, 'speed': disk.speeds[halftrack],
                       'gcr_bytes': len(disk.raw(halftrack)), 'headers': len(sectors),
                       'ids': sorted({bytes(s['id']).hex() for s in sectors if s['header_ok']}),
                       'gaps': sorted({s['gap'] for s in sectors})})
    print(json.dumps(report, indent=1))


if __name__ == '__main__':
    main()
