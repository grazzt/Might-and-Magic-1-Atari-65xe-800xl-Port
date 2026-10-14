#!/usr/bin/env python3
"""The game's logical disk: what its 1541 fastloader makes of the raw sectors.

Derived from the drive code on track 18, sectors 7-11 (source/c64/drive.info).
The loader ignores the DOS directory. A side is 664 blocks of 256 bytes:
tracks 1-35 without track 18, sectors visited in a per-zone interleave order,
and every byte XORed with a key computed from its track and sector. A request
is (block, offset in first block, length) and may run across blocks.

Sides B-D end with a two-block file table that the game loads to $4700 and
searches by two-character name (game code at $C445). Side A has none; its boot
and title code use fixed block numbers. The same two blocks hold the start
block of every monster picture; the encounter file EN reads a picture from
there and monster records from fixed blocks $0165-$017D.

Run without arguments to decode all four original-v2 sides into build/c64/ and
rewrite docs/c64-logical-disk.json.
"""
import argparse
import hashlib
import json
from pathlib import Path

from d64 import D64, SECTORS

ROOT = Path(__file__).resolve().parents[1]

# Sector order within a track, by sectors per track (drive $078C-$07D6).
INTERLEAVE = {
    17: [0, 14, 11, 8, 5, 2, 16, 13, 10, 7, 4, 1, 15, 12, 9, 6, 3],
    18: [0, 13, 8, 3, 16, 11, 6, 1, 14, 9, 4, 17, 12, 7, 2, 15, 10, 5],
    19: [0, 15, 11, 7, 3, 18, 14, 10, 6, 2, 17, 13, 9, 5, 1, 16, 12, 8, 4],
    21: [0, 16, 11, 6, 1, 17, 12, 7, 2, 18, 13, 8, 3, 19, 14, 9, 4, 20, 15, 10, 5],
}
TRACKS = [t for t in range(1, 36) if t != 18]
BLOCKS = sum(SECTORS[t] for t in TRACKS)  # 664
PROTECTED_XOR = 0x25  # command 4 flips these bits in the low block byte


def locate(block):
    """Logical block -> (track, sector). Block numbers wrap, as in the drive."""
    block %= BLOCKS
    for track in TRACKS:
        if block < SECTORS[track]:
            return track, INTERLEAVE[SECTORS[track]][block]
        block -= SECTORS[track]


def key(track, sector):
    """Drive $075C: SEC / ROL A / ADC track / ROR A / ROR A on the sector."""
    value = sector * 2 + 1 + track
    return ((value & 1) << 7 | value >> 2) & 0xff


def decode(disk):
    """Return the whole side as BLOCKS * 256 plain bytes."""
    out = bytearray()
    for block in range(BLOCKS):
        track, sector = locate(block)
        k = key(track, sector)
        out.extend(b ^ k for b in disk.sector(track, sector))
    return bytes(out)


def read(logical, block, offset, length):
    """Bytes a load command returns (commands 0 and, after its XOR, 4)."""
    start = (block % BLOCKS) * 256 + offset
    data = logical[start:start + length]
    if len(data) < length:  # the drive continues from track 1
        data += logical[:length - len(data)]
    return data


TABLE_BLOCK = BLOCKS - 2  # $0296: names, start blocks, lengths, load addresses
TABLE_SLOTS = 48


def directory(logical):
    """Return (side number, entries) from the file table, or (None, []).

    The game compares all 48 name slots; only the leading slots hold entries and
    the rest is unrelated data, so stop at the first name that is not two
    letters or digits. Byte $1FF is the side number the disk-swap check wants
    (1 = B, 2 = C, 3 = D), preceded by $FF.
    """
    table = read(logical, TABLE_BLOCK, 0, 512)
    if table[0x1fe] != 0xff:
        return None, []
    word = lambda base, slot: table[base + slot * 2] | table[base + slot * 2 + 1] << 8
    entries = []
    for slot in range(TABLE_SLOTS):
        name = table[slot * 2:slot * 2 + 2]
        if not all(48 <= c <= 57 or 65 <= c <= 90 for c in name):
            break
        entries.append({'name': name.decode(), 'block': word(0x60, slot),
                        'length': word(0xc0, slot), 'address': word(0x120, slot)})
    return table[0x1ff], entries


def runs(blocks):
    """Sorted block numbers as '$000-$00f $012' ranges."""
    out = []
    for b in blocks:
        if out and out[-1][1] == b - 1:
            out[-1][1] = b
        else:
            out.append([b, b])
    return ' '.join(f'${a:03x}' if a == b else f'${a:03x}-${b:03x}' for a, b in out)


# Side A has no table. These are the reads its boot and title code make, with
# block numbers written into the code (traced: test-artifacts/c64/trace-outdoors).
SIDE_A_READS = [  # block, length, C64 address
    (0x000, 0x0f80, 0x4000), (0x190, 0x0218, 0xc9e8), (0x195, 0x00bc, 0xc92c),
    (0x160, 0x10ef, 0x8c00), (0x070, 0x145e, 0x5000), (0x088, 0x0f4a, 0x5000),
    (0x017, 0x14ff, 0x0b00), (0x03f, 0x292c, 0xa000), (0x1a0, 0x0200, 0x2000),
    (0x140, 0x16ee, 0x3500), (0x184, 0x04a0, 0x4a00),
    # The title's scenes (SPACE at the title; tools/traces/title-scenes.txt):
    # eight packed pictures, and the colour matrices of four of them.
    (0x09b, 0x0af2, 0x5000), (0x0b2, 0x098e, 0x5000), (0x0bd, 0x1052, 0x5000), (0x0d3, 0x0a9c, 0x5000),
    (0x1c4, 0x1016, 0x5000), (0x1d7, 0x0ffa, 0x5000), (0x1b1, 0x0fce, 0x5000), (0x12c, 0x0afa, 0x5000),
    (0x0a8, 0x0400, 0x0400), (0x1a5, 0x0400, 0x0400), (0x1ac, 0x0400, 0x0400), (0x122, 0x0400, 0x0400),
]

PICTURE_TABLE = 0x180       # offset in the file table: one start block each
MONSTER_BLOCK = 0x165       # EN at $24FD: block = $0165 + (record number // 8)
MONSTER_BLOCKS = 25         # room for 200 records; 195 are used
MONSTER_RECORD = 32         # 15 characters of name, then 17 bytes of data


def pictures(logical):
    """(start block, block count) per monster picture, as EN at $2183 uses them.

    Each picture runs to the next entry's start; the last entry is only an end
    marker. The list ends where the start blocks stop increasing.
    """
    table = read(logical, TABLE_BLOCK, PICTURE_TABLE, 0x7e)
    starts = [table[0]]
    for value in table[1:]:
        if value <= starts[-1]:
            break
        starts.append(value)
    return [(a, b - a) for a, b in zip(starts, starts[1:])]


def monsters(logical):
    """Monster records as (name, 17 data bytes); blank records end the list."""
    data = read(logical, MONSTER_BLOCK, 0, MONSTER_BLOCKS * 256)
    out = []
    for i in range(0, len(data), MONSTER_RECORD):
        name = data[i:i + 15]
        if name[0] == 32 or not all(32 <= c < 96 for c in name):
            break
        out.append((name.decode().rstrip(), data[i + 15:i + MONSTER_RECORD]))
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.parse_args()
    report = []
    for side in 'abcd':
        folder = ROOT / f'build/c64/original-v2-{side}'
        if not (folder / 'sectors.d64').exists():
            raise SystemExit('Run python3 tools/analyze_c64.py first')
        logical = decode(D64((folder / 'sectors.d64').read_bytes()))
        (folder / 'logical.bin').write_bytes(logical)
        number, entries = directory(logical)
        mapped = {TABLE_BLOCK, TABLE_BLOCK + 1} if entries else set()
        out = folder / 'logical'
        out.mkdir(exist_ok=True)
        for slot, e in enumerate(entries):
            data = read(logical, e['block'], 0, e['length'])
            (out / f"{slot:02d}-{e['name']}.bin").write_bytes(data)
            mapped.update(range(e['block'], e['block'] + (e['length'] + 255) // 256))
            e.update(block=f"${e['block']:04x}", length=f"${e['length']:04x}",
                     address=f"${e['address']:04x}", sha256=hashlib.sha256(data).hexdigest())
        fixed = []
        if not entries:
            for block, length, address in SIDE_A_READS:
                data = read(logical, block, 0, length)
                mapped.update(range(block, block + (length + 255) // 256))
                fixed.append({'block': f'${block:04x}', 'length': f'${length:04x}',
                              'address': f'${address:04x}',
                              'sha256': hashlib.sha256(data).hexdigest()})
        named = len(mapped)
        art = pictures(logical) if entries else []
        beasts = monsters(logical) if entries else []
        for start, count in art:
            mapped.update(range(start, start + count))
        if beasts:
            mapped.update(range(MONSTER_BLOCK, MONSTER_BLOCK + (len(beasts) + 7) // 8))
        # A block of one repeated byte, or two alternating, is treated as unused.
        blank = [b for b in range(BLOCKS) if len(set(logical[b * 256:b * 256 + 256])) <= 2]
        loose = sorted(set(range(BLOCKS)) - mapped - set(blank))
        report.append({'side': side.upper(), 'side_number': number,
                       'logical_sha256': hashlib.sha256(logical).hexdigest(),
                       'blocks': BLOCKS, 'files': entries, 'fixed_reads': fixed,
                       'monster_pictures': [[f'${a:04x}', n] for a, n in art],
                       'monsters': [{'name': name, 'data': data.hex()} for name, data in beasts],
                       'blocks_in_files_or_fixed_reads': named, 'blocks_explained': len(mapped),
                       'blank_blocks': len(blank), 'blocks_unexplained': len(loose),
                       'unexplained': runs(loose)})
        print(f"{side.upper()}: side number {number}, {len(entries)} named files, {len(art)} monster "
              f"pictures, {len(beasts)} monsters, {len(loose)} non-blank blocks unexplained: {runs(loose)}")
    (ROOT / 'docs/c64-logical-disk.json').write_text(json.dumps(report, indent=1) + '\n')


if __name__ == '__main__':
    main()
