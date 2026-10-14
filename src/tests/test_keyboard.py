import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'tools'),str(ROOT/'port/atari')]
from c64 import shared_root

READY=((ROOT/'build/c64/original-v2-b/logical.bin').exists()
       and (shared_root()/'tools/emulators/local/lib/libatari800.so').exists()
       and (shared_root()/'tools/toolchain/local/bin/ca65').exists())


@unittest.skipUnless(READY,'needs decoded disks and shared Atari800/cc65')
class HeldKeys(unittest.TestCase):
    def check(self, option):
        out=ROOT/'build/atari/keyboard-test'/option
        run=subprocess.run([sys.executable,ROOT/'port/atari/keyboard_check.py',
                            '--'+option,'--out',out],capture_output=True,text=True,timeout=60)
        self.assertEqual(run.returncode,0,run.stdout[-1500:]+run.stderr[-1500:])
        return json.loads((out/('unit.json' if option=='unit' else 'battle.json')).read_text())

    def test_repeat_timing_matches_original_c64_scanner_and_reader(self):
        self.assertEqual(len(self.check('unit')['cases']),8)

    def test_holding_ctrl_a_advances_all_six_characters_and_release_stops(self):
        report=self.check('battle')
        self.assertEqual(report['characters'],list(range(6)))
        self.assertGreaterEqual(report['held_combat_commands'],6)
        self.assertTrue(report['release_stopped'])
