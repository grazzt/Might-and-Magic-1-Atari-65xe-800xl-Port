import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import c64_screen as S


class Drawing(unittest.TestCase):
    def setUp(self):
        self.ram = bytearray(65536)
        self.color = bytearray(1000)
        self.chargen = bytearray(4096)

    def test_multicolour_bitmap_takes_its_four_colours_from_four_places(self):
        self.ram[0x2000] = 0b00011011           # one byte: the four pixel pairs
        self.ram[0x0400] = 0x25                 # 01 -> 2, 10 -> 5
        self.color[0] = 7                       # 11 -> 7
        rows = S.render(self.ram, self.color, self.chargen,
                        [S.Segment(0, 200, 0, 0x18, 0x3b, 0x18)], background=6)
        self.assertEqual(list(rows[0][:8]), [6, 6, 2, 2, 5, 5, 7, 7])

    def test_hires_bitmap(self):
        self.ram[0xe000] = 0b10100000
        self.ram[0xcc00] = 0x1e
        rows = S.render(self.ram, self.color, self.chargen,
                        [S.Segment(0, 200, 3, 0x38, 0x3b, 0x08)], background=0)
        self.assertEqual(list(rows[0][:4]), [1, 14, 1, 14])

    def test_text_uses_the_character_rom_in_bank_0(self):
        self.chargen[0x800 + 1 * 8] = 0b11000000        # screen code 1 in the second set
        self.ram[0x0400], self.color[0] = 1, 3
        rows = S.render(self.ram, self.color, self.chargen,
                        [S.Segment(0, 200, 0, 0x17, 0x1b, 0x08)], background=0)
        self.assertEqual(list(rows[0][:4]), [3, 3, 0, 0])

    def test_split_frame(self):
        self.ram[0x2000 + 8 * 40 * 0] = 0xff            # row 0, upper bitmap
        self.ram[0xe000 + 8 * 40 * 1] = 0xff            # row 8, lower bitmap
        self.ram[0x0400], self.ram[0xcc00 + 40] = 0x10, 0x20
        rows = S.render(self.ram, self.color, self.chargen,
                        [S.Segment(0, 8, 0, 0x18, 0x3b, 0x08), S.Segment(8, 200, 3, 0x38, 0x3b, 0x08)], 0)
        self.assertEqual((rows[0][0], rows[8][0]), (1, 2))


class Png(unittest.TestCase):
    def test_round_trip_and_comparison(self):
        rows = [bytearray((x + y) % 16 for x in range(S.WIDTH)) for y in range(S.HEIGHT)]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'p.png'
            S.write_png(path, rows)
            width, height, pixels = S.read_png(path)
        self.assertEqual((width, height), (320, 200))
        back = S.colour_numbers(pixels)
        self.assertEqual(S.differences(rows, back), (0, []))
        back[5][7] ^= 1
        self.assertEqual(S.differences(rows, back), (1, [5]))

    def test_palette_colours_are_distinct(self):
        self.assertEqual(len(set(S.PALETTE)), 16)


if __name__ == '__main__':
    unittest.main()
