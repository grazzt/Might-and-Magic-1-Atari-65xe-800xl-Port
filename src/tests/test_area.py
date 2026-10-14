import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from area import Area, area_name, world_route

N, E, S, W = 0x40, 0x10, 0x04, 0x01


def make(blocked=None, neighbours=None, code=b''):
    """An area file: open grid except `blocked` {(x, y): bits}; code at $8432."""
    data = bytearray(0x232) + code
    for (x, y), bits in (blocked or {}).items():
        data[0x100 + y * 16 + x] = bits
    for i, (first, second, side) in enumerate(neighbours or [(0, 0, 1)] * 4):
        data[0x208 + i * 3:0x20b + i * 3] = bytes([first, second, side])
    return Area(bytes(data))


def dispatcher(entries):
    """The event lookup as the game has it, with its four tables after it."""
    count = len(entries)
    tables = 0x8432 + 0x3f                      # code padded to $3F bytes, then the count
    cells, masks, low, high = (tables + 1 + count * i for i in range(4))
    le = lambda v: bytes([v & 255, v >> 8])
    code = (bytes([0xa5, 0x3d, 0xa2, 0x00, 0xdd]) + le(cells) + bytes([0xf0, 0x0f, 0xe8, 0xec])
            + le(tables) + bytes([0x90, 0xf5, 0x20, 0x84, 0xa0, 0x20, 0x87, 0x0b, 0x4c, 0x48, 0x0b])
            + bytes([0xa5, 0x40, 0x3d]) + le(masks) + bytes([0xd0, 0x03, 0x4c, 0x60, 0x0b])
            + bytes([0xbd]) + le(low) + bytes([0x8d, 0x64, 0x84])
            + bytes([0xbd]) + le(high) + bytes([0x8d, 0x65, 0x84]))
    code = code.ljust(0x3f, b'\xea') + bytes([count])
    for column in range(4):
        code += bytes(e[column] for e in entries)
    return code


class AreaTests(unittest.TestCase):
    def test_names(self):
        self.assertEqual(area_name(0x04, 0x06), 'EG')
        self.assertEqual(area_name(0x11, 0x0a), 'RK')
        self.assertEqual(area_name(0x1a, 0x0b), '0L')   # 26 and up are digits
        self.assertEqual(area_name(0x1b, 0x05), '1F')

    def test_route_turns_and_blocking(self):
        area = make()
        self.assertEqual(area.route((8, 3), 'N', (8, 5)), ('II', 'N'))
        self.assertEqual(area.route((8, 3), 'N', (9, 3)), ('LI', 'E'))
        self.assertEqual(area.route((8, 3), 'N', (7, 3), 'S'), ('JIJ', 'S'))
        self.assertEqual(area.route((8, 3), 'N', (8, 2)), ('LLI', 'S'))
        walled = make({(8, 3): N | E | W, (8, 2): W | E})
        keys, facing = walled.route((8, 3), 'N', (8, 4))
        self.assertTrue(keys.startswith('LLI'))            # must leave southward
        self.assertIsNone(make({(0, 0): N | E}).route((0, 0), 'N', (5, 5)))
        self.assertIsNone(area.route((8, 3), 'N', (8, 5), avoid={(8, 4), (7, 4), (9, 4), (7, 3),
                                                                 (9, 3), (8, 2)}))

    def test_events_and_handler(self):
        handler = bytes([0xa9, 0x11, 0xa2, 0x0a, 0xa0, 0x02, 0x4c, 0x78, 0x0b])  # to RK on side C
        code = dispatcher([(0x38, 0x0c, 0x00, 0x85), (0x0c, 0xc0, 0x20, 0x85)])
        code = code.ljust(0x8500 - 0x8432, b'\xea') + b'\x60' * 0x20 + handler
        area = make(code=code)
        self.assertEqual(area.events(), [(8, 3, 'S', 0x8500), (12, 0, 'N', 0x8520)])
        self.assertEqual(area.handler(0x8500), b'\x60' * 0x20)
        self.assertEqual(area.exits(), [('RK', 'C', (12, 0, 'N'))])
        self.assertEqual(make(code=b'\x20\x7b\x0b').events(), [])

    def test_world_route_crosses_open_edges(self):
        here, south = ('AA', 'C'), ('AB', 'C')
        world = {here: make(neighbours=[(0, 0, 2), (0, 0, 2), (0, 1, 2), (0, 0, 2)]),
                 south: make(neighbours=[(0, 0, 2), (0, 1, 2), (0, 1, 2), (0, 1, 2)])}
        keys, facing, passed = world_route(world, here, (3, 1), 'S', south, (3, 14))
        self.assertEqual((keys, facing, passed), ('III', 'S', [here, south]))
        self.assertEqual(world[here].neighbours()[2], south)
        # An area that names itself has no neighbour that way: one step south
        # would do if the southern edge wrapped, but the route goes north.
        keys, facing, _ = world_route(world, south, (3, 0), 'S', here, (3, 15))
        self.assertEqual((keys, facing), ('LL' + 'I' * 31, 'N'))


if __name__ == '__main__':
    unittest.main()
