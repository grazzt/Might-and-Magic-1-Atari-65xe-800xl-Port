import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from g64 import G64, GCR

ENCODE = {value: code for code, value in GCR.items()}


def gcr(data):
    bits = ''.join(f'{ENCODE[b >> 4]:05b}{ENCODE[b & 15]:05b}' for b in data)
    return bits


def track_bits(sectors, gap=bytes([0x55] * 9)):
    """One track: sync, header, gap, sync, data block, gap for each sector."""
    out = ''
    for track, sector, payload in sectors:
        header = [0x08, sector ^ track ^ 0x31 ^ 0x32, sector, track, 0x32, 0x31, 0x0f, 0x0f]
        check = 0
        for b in payload:
            check ^= b
        out += '1' * 40 + gcr(header) + ''.join(f'{b:08b}' for b in gap)
        out += '1' * 40 + gcr([0x07] + list(payload) + [check, 0, 0]) + '01' * 32
    return out


def image(bits):
    bits += '0' * (-len(bits) % 8)
    raw = bytes(int(bits[i:i + 8], 2) for i in range(0, len(bits), 8))
    header = b'GCR-1541' + bytes([0, 84]) + struct.pack('<H', 7928)
    offsets = [12 + 84 * 8] + [0] * 83
    return (header + struct.pack('<84I', *offsets) + struct.pack('<84I', *([3] + [0] * 83))
            + struct.pack('<H', len(raw)) + raw.ljust(7928, b'\xff'))


class G64Tests(unittest.TestCase):
    def test_headers_gaps_and_data(self):
        first, second = bytes(range(256)), bytes(255 - i for i in range(256))
        gap = bytes.fromhex('5294a5294a5294afff')
        disk = G64(image(track_bits([(1, 0, first), (1, 16, second)], gap)))
        # Sectors come back in track order from wherever the first header is.
        sectors = sorted(disk.sectors(0), key=lambda s: s['sector'])
        self.assertEqual([(s['track'], s['sector']) for s in sectors], [(1, 0), (1, 16)])
        self.assertTrue(all(s['header_ok'] and s['data_ok'] for s in sectors))
        self.assertEqual(sectors[0]['id'], [0x31, 0x32])
        self.assertEqual(sectors[0]['gap'], gap.hex())
        self.assertEqual(sectors[0]['data'], first)
        self.assertEqual(sectors[1]['data'], second)
        self.assertIsNone(disk.raw(2))

    def test_block_wrapping_past_the_track_end(self):
        payload = bytes(i * 7 & 0xff for i in range(256))
        bits = track_bits([(5, 3, payload)])
        rotated = bits[-900:] + bits[:-900]  # the data block now spans the join
        sectors = G64(image(rotated)).sectors(0)
        self.assertEqual(len(sectors), 1)
        self.assertTrue(sectors[0]['data_ok'])
        self.assertEqual(sectors[0]['data'], payload)

    def test_bad_data_checksum(self):
        bits = track_bits([(1, 0, bytes(256))])
        marker = '1' * 40 + gcr([0x07])
        at = bits.index(marker) + len(marker)
        broken = bits[:at] + gcr([0x01]) + bits[at + 10:]
        self.assertFalse(G64(image(broken)).sectors(0)[0]['data_ok'])


if __name__ == '__main__':
    unittest.main()
