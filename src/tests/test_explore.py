import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from c64_explore import script
import oracle_explore


class ExploreScript(unittest.TestCase):
    def test_keys_marks_and_special_steps(self):
        lines = script('town.vsf', 'B', 'IY|<5f><attach C><snap out><until $78a2><wait 100>')
        self.assertEqual(lines, [
            'resume town.vsf B', 'wait $100000',
            'press 49', 'press 59', 'ready', 'mark m01',
            'press 5f', 'attach C', 'wait $100000',
            'ready', 'snapshot out', 'until $78a2', 'wait 100'])

    def test_marks_are_numbered(self):
        lines = script('s.vsf', 'A', '||')
        self.assertEqual(lines[2:], ['ready', 'mark m01', 'ready', 'mark m02'])


class OracleExplore(unittest.TestCase):
    def test_the_base_script_ends_at_its_mark(self):
        lines = ['key 5f', 'ready', 'mark menu   # the options', 'press 31', 'ready', 'mark inn']
        self.assertEqual(oracle_explore.base(lines, 'menu'), lines[:3])
        with self.assertRaises(SystemExit):
            oracle_explore.base(lines, 'town')


if __name__ == '__main__':
    unittest.main()
