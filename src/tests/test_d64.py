import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from d64 import D64, DATA_SIZE


class D64Tests(unittest.TestCase):
    def test_geometry(self):
        self.assertEqual(D64.index(18, 0) * 256, 0x16500)
        self.assertEqual(D64.index(35, 16), 682)
        for ts in [(0, 0), (36, 0), (18, 19), (1, -1)]:
            with self.assertRaises(ValueError):
                D64.index(*ts)

    def test_chain_terminal_byte_count(self):
        disk = bytearray(DATA_SIZE)
        disk[:2] = bytes([1, 1])
        disk[2:256] = b'A' * 254
        disk[256:261] = bytes([0, 4]) + b'BCD'
        data, sectors = D64(disk).chain(1, 0)
        self.assertEqual(data, b'A' * 254 + b'BCD')
        self.assertEqual(sectors, [[1, 0], [1, 1]])

    def test_cycle_and_corruption(self):
        disk = bytearray(DATA_SIZE)
        disk[:2] = bytes([1, 0])
        with self.assertRaisesRegex(ValueError, 'Cyclic'):
            D64(disk).chain(1, 0)
        disk[:2] = b'\0\0'
        with self.assertRaisesRegex(ValueError, 'byte count'):
            D64(disk).chain(1, 0)
        errors = bytes([2]) + bytes([1]) * 682
        with self.assertRaisesRegex(ValueError, 'Disk error'):
            D64(disk + errors).sector(1, 0)

    def test_directory_loop(self):
        disk = bytearray(DATA_SIZE)
        for sector in [0, 1]:
            start = D64.index(18, sector) * 256
            disk[start:start + 2] = bytes([18, 1])
        with self.assertRaisesRegex(ValueError, 'Cyclic directory'):
            D64(disk).directory()


if __name__ == '__main__':
    unittest.main()
