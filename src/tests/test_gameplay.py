import contextlib
import io
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from c64 import shared_root
import coverage_check
import oracle

READY = ((ROOT / 'build/c64/original-v2-b/logical.bin').exists()
         and (shared_root() / 'tools/emulators/local/usr/share/vice/C64/kernal-901227-03.bin').exists())


@unittest.skipUnless(READY, 'needs decoded game files and the VICE KERNAL ROM')
class Gameplay(unittest.TestCase):
    def test_new_behaviors_and_settled_pictures_match_vice(self):
        with contextlib.redirect_stdout(io.StringIO()):
            report = coverage_check.check(pictures=True)
        self.assertEqual(set(report), set(coverage_check.CASES))
        self.assertTrue(all(row['behavior_checked'] and row['reference_equal']
                            and row['pictures_equal'] == row['marks'] for row in report.values()))

    def test_a_failed_item_use_cannot_pass_as_a_successful_one(self):
        player, marks = oracle.Oracle(), {}
        lines = (ROOT / 'tools/traces/boot-to-combat-item.txt').read_text().splitlines()
        player.play(lines, pictures=False,
                    on_mark=lambda name: marks.__setitem__(name, player.machine.ram_image()))
        broken = bytearray(marks['item-used'])
        broken[0x0acc] = 3
        marks['item-used'] = bytes(broken)
        with self.assertRaisesRegex(AssertionError, 'charged item was not used'):
            coverage_check.verify('combat-item', player, marks)

    def test_unconsciousness_does_not_count_as_death(self):
        player, marks = oracle.Oracle(), {}
        lines = (ROOT / 'tools/traces/boot-to-death-and-raising.txt').read_text().splitlines()
        player.play(lines, pictures=False,
                    on_mark=lambda name: marks.__setitem__(name, player.machine.ram_image()))
        broken = bytearray(marks['one-character-dead'])
        broken[0x083f] = 0x40
        marks['one-character-dead'] = bytes(broken)
        with self.assertRaisesRegex(AssertionError, 'Crag did not die'):
            coverage_check.verify('death-and-raising', player, marks)


if __name__ == '__main__':
    unittest.main()
