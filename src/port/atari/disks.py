"""Four-disk layout for the Atari build: items, ZX02 compression, index, ATRs.

docs/DISKS.md has the format and the reasons. In short, each disk is an
enhanced-density image (1,040 sectors of 128 bytes). It holds the items one side
of the C64 game holds, most compressed with ZX02 and padded to whole sectors,
and an index at its end: two bytes for every block number, the item that starts
there. Bits 0-10 are the first sector, bit 15 marks an item stored as it is.

The compressor is ZX02 (tools/zx02, MIT licence); it is compiled once with the
system C compiler into build/atari.
"""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from c64 import shared_root            # noqa: E402

OUT = ROOT / 'build/atari'
SECTOR = 128
DISK_SECTORS = 1040             # a stock 1050 in enhanced density
BLOCKS = 664                    # blocks of 256 bytes on one C64 side
INDEX_SECTORS = 11              # 64 entries a sector: block numbers up to 703
INDEX_SECTOR = DISK_SECTORS - INDEX_SECTORS + 1
IMAGE_BLOCK = BLOCKS            # the boot code's pieces are items 664, 665, ... of disk 1
MONSTER_RECORDS = (0x165, 0x17e)    # blocks $165-$17D: the game reads them a block at a time
FILE_TABLE = (0x296, 0x297)         # read whole on every side check
WRITTEN = ('RO',)                   # files the game writes back: stored as they are
SIDES = 'ABCD'


class Disk:
    """What is going onto one disk: items by first block, in order."""

    def __init__(self, name, first_sector=1):
        self.name = name
        self.first_sector = first_sector
        self.items = {}         # first block -> {'data', 'raw', 'name'}
        self.runs = []          # stored runs: (first block, blocks), each block indexed

    def add(self, block, data, raw=False, name=''):
        old = self.items.get(block)
        if old:
            if old['raw'] != raw:
                raise SystemExit(f'{self.name}: block ${block:03x} is wanted both stored and packed')
            if len(data) <= len(old['data']):
                if data != old['data'][:len(data)]:
                    raise SystemExit(f'{self.name}: block ${block:03x} read twice with different data')
                return
            if data[:len(old['data'])] != old['data']:
                raise SystemExit(f'{self.name}: block ${block:03x} read twice with different data')
        self.items[block] = {'data': bytes(data), 'raw': raw, 'name': name}


def side_items(disk, logical, info, address_of=None):
    """Items of side B, C or D from the game's own file table (docs/c64-logical-disk.json)."""
    block = lambda text: int(text[1:], 16)
    blocks = lambda first, length: logical[first * 256:first * 256 + length]
    for f in info['files']:
        first, length = block(f['block']), block(f['length'])
        disk.add(first, blocks(first, length), raw=f['name'] in WRITTEN, name=f['name'])
    for first, count in info['monster_pictures']:
        first = block(first)
        disk.add(first, blocks(first, count * 256), name=f'picture ${first:03x}')
    first, last = MONSTER_RECORDS
    disk.add(first, blocks(first, (last - first + 1) * 256), raw=True, name='monster records')
    first, last = FILE_TABLE
    disk.add(first, blocks(first, (last - first + 1) * 256), raw=True, name='file table')


def boot_items(disk, logical, info, extra_raw=()):
    """Side A: everything the title program, the start-up stub and the boot code read."""
    block = lambda text: int(text[1:], 16)
    for f in info['fixed_reads']:
        first, length, address = block(f['block']), block(f['length']), block(f['address'])
        disk.add(first, logical[first * 256:first * 256 + length], name=f"side A ${first:03x} to ${address:04x}")


# --- ZX02 --------------------------------------------------------------------

_binary = None


def compressor():
    global _binary
    if _binary is None:
        source = ROOT / 'tools/zx02'            # vendored (tools/zx02/README.md); the Wizardry port's copy otherwise
        if not (source / 'compress.c').exists():
            source = shared_root() / 'tools/zx02'
        files = ['compress.c', 'optimize.c', 'memory.c', 'zx02.c']
        digest = hashlib.sha256(b''.join((source / name).read_bytes() for name in files)).hexdigest()[:16]
        OUT.mkdir(parents=True, exist_ok=True)
        _binary = OUT / f'zx02-{digest}'
        if not _binary.exists():
            subprocess.run(['cc', '-O3', '-DNDEBUG', '-o', str(_binary), *(str(source / n) for n in files)],
                           check=True)
    return _binary


def encode(data):
    """A ZX02 stream for data, cached by content under build/atari/zx02-cache."""
    cache = OUT / 'zx02-cache'
    cache.mkdir(parents=True, exist_ok=True)
    path = cache / (hashlib.sha256(data).hexdigest() + '.zx02')
    if path.exists():
        return path.read_bytes()
    with tempfile.TemporaryDirectory() as directory:
        source, target = Path(directory) / 'in', Path(directory) / 'out'
        source.write_bytes(data)
        subprocess.run([str(compressor()), str(source), str(target)], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        stream = target.read_bytes()
    path.write_bytes(stream)
    return stream


def decode(stream, size):
    """Reference decoder: the first `size` bytes of a standard forward ZX02 stream."""
    at, reservoir, extra, offset = 0, 0x80, None, 1
    out = bytearray()

    def byte():
        nonlocal at
        value = stream[at]
        at += 1
        return value

    def bit():
        nonlocal reservoir, extra
        if extra is not None:
            value, extra = extra, None
            return value
        if reservoir == 0x80:
            value = byte()
            reservoir = (value << 1 | 1) & 255
        else:
            value = reservoir
            reservoir = (reservoir << 1) & 255
        return value >> 7

    def elias():
        value = 1
        while bit():
            value = value << 1 | bit()
            if value > 256:
                raise ValueError('invalid ZX02 Elias code')
        return value

    state = 0
    while len(out) < size:
        if state == 0:
            for _ in range(elias()):
                out.append(byte())
                if len(out) == size:
                    return bytes(out)
            state = 2 if bit() else 1
        else:
            add = 0
            if state == 2:
                high = elias()
                if high == 256:
                    break
                low = byte()
                offset = (high - 1 << 7) + (low >> 1) + 1
                extra = low & 1
                add = 1
            length = (elias() + add) & 255 or 256
            if offset > len(out):
                raise ValueError('a ZX02 match reaches before the output')
            for _ in range(length):
                out.append(out[-offset])
                if len(out) == size:
                    return bytes(out)
            state = 2 if bit() else 0
    if len(out) != size:
        raise ValueError(f'decoded {len(out)} of {size} bytes')
    return bytes(out)


# --- the images ----------------------------------------------------------------

def pack(disk, reserved=0):
    """Lay out one disk. Returns (sectors: bytearray of 1040 * 128, report dict).

    reserved: sectors at the start that something else holds (the boot sectors).
    An item is packed if that is smaller than it is; it always goes to whole
    sectors, a stored run (monster records, file table) with every block indexed.
    """
    body = bytearray(DISK_SECTORS * SECTOR)
    index = {}
    sector = 1 + reserved
    packed = stored = 0
    ordered = sorted(disk.items.items())
    for block, item in ordered:
        data = item['data']
        raw = item['raw']
        if not raw:
            stream = encode(data)
            if len(stream) < len(data):
                data, raw = stream, False
            else:
                raw = True
        if sector + -(-len(data) // SECTOR) > INDEX_SECTOR:
            raise SystemExit(f'{disk.name}: out of sectors at item ${block:03x} {item["name"]}')
        body[(sector - 1) * SECTOR:(sector - 1) * SECTOR + len(data)] = data
        if raw:
            # one entry for each block of a stored run, two sectors apart
            for k in range(-(-len(item['data']) // 256)):
                index[block + k] = (sector + 2 * k, True)
            stored += 1
        else:
            index[block] = (sector, False)
            packed += 1
        item['sector'], item['sectors'], item['stored'] = sector, -(-len(data) // SECTOR), raw
        sector += -(-len(data) // SECTOR)
    table = bytearray(INDEX_SECTORS * SECTOR)
    for block, (first, raw) in index.items():
        if block >= INDEX_SECTORS * 64:
            raise SystemExit(f'{disk.name}: block ${block:03x} is beyond the index')
        if not 0 < first < 2048:
            raise SystemExit(f'{disk.name}: sector {first} does not fit an index entry')
        entry = first | 0x8000 * raw
        table[block * 2:block * 2 + 2] = entry.to_bytes(2, 'little')
    body[(INDEX_SECTOR - 1) * SECTOR:] = table
    return body, {'sectors': sector - 1, 'packed': packed, 'stored': stored, 'index': index}


def atr(body):
    """An ATR file: header, then the sectors."""
    paragraphs = len(body) // 16
    header = bytes([0x96, 0x02, paragraphs & 255, paragraphs >> 8 & 255, SECTOR, 0, paragraphs >> 16]) + bytes(9)
    return header + bytes(body)


def read_item(body, index, block, offset, length):
    """What the kernel's read of (block, offset, length) gives, from an image body: the
    host twin of kernel.s's transfer, for the checks."""
    entry = index.get(block)
    if entry is None:
        return None
    sector, raw = entry
    start = (sector - 1) * SECTOR + (SECTOR if offset & 0x80 else 0)
    skip = offset & 0x7f
    if raw:
        return bytes(body[start + skip:start + skip + length])
    if offset:
        return None
    return decode(bytes(body[start:]), length)


def index_of(body):
    """The index as an image holds it: {block: (sector, raw)}."""
    out = {}
    table = body[(INDEX_SECTOR - 1) * SECTOR:]
    for block in range(INDEX_SECTORS * 64):
        entry = int.from_bytes(table[block * 2:block * 2 + 2], 'little')
        if entry:
            out[block] = (entry & 0x7ff, bool(entry & 0x8000))
    return out
