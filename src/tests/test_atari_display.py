import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'port/atari'))
import display_demo as demo


class Layout(unittest.TestCase):
    def test_no_row_crosses_a_character_set_boundary(self):
        for row in range(demo.ROWS):
            start = demo.row_address(row)
            self.assertEqual(start // 0x400, (start + 319) // 0x400, row)
            self.assertEqual((start % 0x400) // 8, row % 3 * 40)    # its first character code

    def test_c64_layout_would_cross(self):
        crossing = [row for row in range(16) if (row * 320) // 0x400 != (row * 320 + 319) // 0x400]
        self.assertEqual(crossing, [3, 6, 9, 12])


class Recoding(unittest.TestCase):
    def test_pixels_take_row_colours_and_the_panel_takes_the_fourth(self):
        rows = [bytearray(320) for _ in range(200)]
        for x in range(0, 8):
            rows[0][x] = 12                 # cell 0: grey
        for x in range(8, 16):
            rows[0][x] = 2                  # cell 1: red, rarer
        rows[0][16] = rows[0][17] = 12
        for x in range(240, 248):
            rows[0][x] = 3                  # first panel cell: cyan
        cells, palettes = demo.convert(rows)
        self.assertEqual(palettes[0][:2], [12, 2])
        self.assertEqual(palettes[0][3], 3)
        self.assertEqual(cells[0][0][0], 0b01010101)    # most used colour -> pair 01
        self.assertEqual(cells[0][1][0], 0b10101010)
        self.assertEqual(cells[0][30][0], 0b11111111)   # panel -> pair 11, shown in register 3
        self.assertEqual(cells[0][0][1], 0)             # black stays background


if __name__ == '__main__':
    unittest.main()
