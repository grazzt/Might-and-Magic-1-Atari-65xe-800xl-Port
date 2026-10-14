import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from d64 import D64, DATA_SIZE, SECTORS
import mmdisk


def drive_key(track, sector):
    """The drive's instruction sequence at $075C, one step at a time."""
    a = (sector << 1 | 1) & 0xff               # SEC / ROL A
    carry = sector >> 7
    total = a + track + carry                   # ADC track
    a, carry = total & 0xff, total >> 8
    a, carry = carry << 7 | a >> 1, a & 1       # ROR A
    return carry << 7 | a >> 1                  # ROR A


class LogicalDiskTests(unittest.TestCase):
    def test_geometry(self):
        self.assertEqual(mmdisk.BLOCKS, 664)
        for count, order in mmdisk.INTERLEAVE.items():
            self.assertEqual(sorted(order), list(range(count)))
        self.assertEqual(mmdisk.locate(0), (1, 0))
        self.assertEqual(mmdisk.locate(1), (1, 16))
        self.assertEqual(mmdisk.locate(21), (2, 0))
        self.assertEqual(mmdisk.locate(17 * 21 - 1), (17, 5))
        self.assertEqual(mmdisk.locate(17 * 21), (19, 0))  # track 18 is skipped
        self.assertEqual(mmdisk.locate(663), (35, 3))
        self.assertEqual(mmdisk.locate(664), (1, 0))       # wraps like the drive
        self.assertEqual(len({mmdisk.locate(b) for b in range(664)}), 664)

    def test_key_matches_drive_arithmetic(self):
        for track in range(1, 36):
            for sector in range(SECTORS[track]):
                self.assertEqual(mmdisk.key(track, sector), drive_key(track, sector))
        self.assertEqual(mmdisk.key(1, 0), 0x00)
        self.assertEqual(mmdisk.key(1, 16), 0x08)
        self.assertEqual(mmdisk.key(2, 0), 0x80)

    def test_decode_and_read_across_blocks(self):
        disk = bytearray(DATA_SIZE)
        for block in (0, 1, 663):
            track, sector = mmdisk.locate(block)
            start = D64.index(track, sector) * 256
            k = mmdisk.key(track, sector)
            disk[start:start + 256] = bytes((block + i) & 0xff ^ k for i in range(256))
        logical = mmdisk.decode(D64(disk))
        self.assertEqual(len(logical), 664 * 256)
        self.assertEqual(mmdisk.read(logical, 0, 0xfe, 4), bytes([0xfe, 0xff, 1, 2]))
        self.assertEqual(mmdisk.read(logical, 663, 0xff, 3), bytes([0x96, 0, 1]))

    def test_directory(self):
        logical = bytearray(664 * 256)
        table = mmdisk.TABLE_BLOCK * 256
        logical[table:table + 4] = b'GO0L'
        logical[table + 0x60:table + 0x64] = bytes([0x3a, 0x01, 0xca, 0x01])
        logical[table + 0xc0:table + 0xc4] = bytes([0x9a, 0x16, 0x7f, 0x05])
        logical[table + 0x120:table + 0x124] = bytes([0x00, 0x69, 0x00, 0x82])
        logical[table + 4:table + 6] = b'\x7f\x7f'  # not a name: ends the list
        logical[table + 0x1fe:table + 0x200] = b'\xff\x02'
        number, entries = mmdisk.directory(bytes(logical))
        self.assertEqual(number, 2)
        self.assertEqual(entries, [
            {'name': 'GO', 'block': 0x13a, 'length': 0x169a, 'address': 0x6900},
            {'name': '0L', 'block': 0x1ca, 'length': 0x057f, 'address': 0x8200}])
        logical[table + 0x180:table + 0x186] = bytes([0x00, 0x03, 0x07, 0x0a, 0x00, 0x7c])
        self.assertEqual(mmdisk.pictures(bytes(logical)), [(0, 3), (3, 4), (7, 3)])
        logical[table + 0x1fe] = 0x0b  # side A has no table
        self.assertEqual(mmdisk.directory(bytes(logical)), (None, []))

    def test_monsters(self):
        logical = bytearray(664 * 256)
        start = mmdisk.MONSTER_BLOCK * 256
        logical[start:start + 32] = b'FLESH EATER    ' + bytes(range(1, 18))
        logical[start + 32:start + 64] = b'5 HEADED HYDRA ' + bytes(17)
        logical[start + 64:start + 96] = bytes([0xff]) * 32
        self.assertEqual(mmdisk.monsters(bytes(logical)),
                         [('FLESH EATER', bytes(range(1, 18))), ('5 HEADED HYDRA', bytes(17))])

    def test_runs(self):
        self.assertEqual(mmdisk.runs([0, 1, 2, 5, 7, 8]), '$000-$002 $005 $007-$008')

if __name__ == '__main__':
    unittest.main()
