import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'tools'), str(ROOT / 'port/atari')]
import c64_sound
from c64 import shared_root

READY = ((ROOT / 'build/c64/original-v2-b/logical.bin').exists()
         and (shared_root() / 'tools/emulators/local/lib/libatari800.so').exists()
         and (shared_root() / 'tools/toolchain/local/bin/ca65').exists())


@unittest.skipUnless(READY, 'needs decoded game files, cc65 and the shared emulators')
class Sound(unittest.TestCase):
    def test_original_sequences_and_every_sid_write_are_recorded(self):
        result = c64_sound.record()
        self.assertEqual([len(e['steps']) for e in result['effects']], [2, 2, 6, 10, 48, 12, 14, 7, 10])
        self.assertEqual([e['writes'][-1]['frame'] for e in result['effects']],
                         [22, 12, 88, 90, 506, 338, 54, 177, 114])
        for effect in result['effects']:
            writes = effect['writes']
            self.assertEqual([w['register'] for w in writes[:7]], list(range(7)))
            self.assertEqual([w['value'] for w in writes[:7]], effect['setup'][:7])
            self.assertEqual([(w['register'], w['value']) for w in writes[-8:]],
                             [(r, 0) for r in range(7, -1, -1)])
            for step, offset in zip(effect['steps'], range(7, len(writes) - 8, 3)):
                self.assertEqual([(w['register'], w['value']) for w in writes[offset:offset + 3]],
                                 [(0, step['frequency'] & 255), (1, step['frequency'] >> 8),
                                  (4, step['gate'] | effect['setup'][7])])
        for frequency in c64_sound.pitches(result['effects']):
            expected = c64_sound.SID_CLOCK * frequency / 2**24
            actual = c64_sound.POKEY_CLOCK / (2 * (c64_sound.divisor(frequency) + 7))
            self.assertLess(abs(actual / expected - 1), 0.001)

    def test_real_effects_produce_audio_and_obey_key_and_sound_options(self):
        run = subprocess.run([sys.executable, ROOT / 'port/atari/sound_check.py'],
                             capture_output=True, text=True, timeout=60)
        self.assertEqual(run.returncode, 0, run.stdout[-1200:] + run.stderr[-1200:])
        report = json.loads((ROOT / 'build/atari/sound/report.json').read_text())
        self.assertEqual(len(report['effects']), 9)
        self.assertEqual(len(report['interruptions']), 6)


if __name__ == '__main__':
    unittest.main()
