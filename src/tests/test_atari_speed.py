import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'tools'), str(ROOT / 'port/atari')]
from c64 import shared_root

READY = ((ROOT / 'build/c64/original-v2-b/logical.bin').exists()
         and (shared_root() / 'tools/emulators/local/lib/libatari800.so').exists()
         and (shared_root() / 'tools/toolchain/local/bin/ca65').exists())


@unittest.skipUnless(READY, 'needs decoded C64 disks, cc65 and libatari800')
class DisplayTransitions(unittest.TestCase):
    def run_check(self, *options):
        out = ROOT / 'build/atari/speed-test'
        run = subprocess.run([sys.executable, ROOT / 'port/atari/speed_check.py',
                              '--out', out, *options], capture_output=True, text=True, timeout=60)
        self.assertEqual(run.returncode, 0, run.stdout[-1600:] + run.stderr[-1600:])
        return out

    def test_text_is_stable_and_bitmap_transitions_are_faster(self):
        report = json.loads((self.run_check() / 'report.json').read_text())
        actions = {a['action']: a for a in report['actions']}
        for name in ('enter-town', 'back-to-town'):
            self.assertEqual(actions[name]['text_changed_frames'], 0)
            self.assertTrue(any('text_sha256' in s for s in actions[name]['states']),
                            'The transition must include visible text to test its stability')
        self.assertLessEqual(actions['back-to-town']['frames'], 24)
        for name in ('step', 'turn-left', 'turn-right'):
            self.assertLessEqual(actions[name]['frames'], 29)
        self.assertEqual(report['idle']['frames_in_conversion'], 0)
        self.assertGreater(report['idle_positive_control']['frames_in_conversion'], 30)

    def test_cached_palettes_equal_full_calculation_after_input_changes(self):
        report = json.loads((self.run_check('--cache-probe') / 'cache-probe.json').read_text())
        self.assertEqual(len(report['cases']), 50)
        self.assertEqual(report['proven_uniform_hits'], 4)

    def test_graphics_fast_paths_equal_the_original_converter(self):
        out = ROOT / 'build/atari/graphics-test'
        run = subprocess.run([sys.executable, ROOT / 'port/atari/graphics_check.py',
                              '--out', out], capture_output=True, text=True, timeout=60)
        self.assertEqual(run.returncode, 0, run.stdout[-1600:] + run.stderr[-1600:])
        report = json.loads((out / 'graphics-check.json').read_text())
        self.assertEqual(len(report['refresh_cases']), 24)
        self.assertEqual(report['pixel_patterns'], 17)
        self.assertTrue(report['pair_swap_negative'])

    def test_shared_palette_mapping_equals_full_selection(self):
        out = ROOT / 'build/atari/palette-test'
        baseline = ROOT / 'test-artifacts/palette/before'
        run = subprocess.run([sys.executable, ROOT / 'port/atari/palette_check.py',
                              '--check', baseline, '--out', out],
                             capture_output=True, text=True, timeout=60)
        self.assertEqual(run.returncode, 0, run.stdout[-1600:] + run.stderr[-1600:])
        report = json.loads((out / 'palette-check.json').read_text())
        self.assertEqual(len(report['screens']), 9)
        self.assertEqual(len(report['cases']), 228)
        self.assertEqual({s['mode'] for s in report['screens']}, {0, 1, 2})
        self.assertGreater(sum(c['shared_hits'] for c in report['cases']), 0)
