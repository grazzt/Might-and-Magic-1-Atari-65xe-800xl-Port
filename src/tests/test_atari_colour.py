import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'port/atari'),str(ROOT/'tools')]
from test_atari import READY

@unittest.skipUnless(READY,'needs cc65, decoded game disks and libatari800')
class Colours(unittest.TestCase):
    def test_drawn_colours_bitmap_invalidation_and_panel_layout(self):
        with tempfile.TemporaryDirectory() as folder:
            run=subprocess.run([sys.executable,ROOT/'port/atari/colour_check.py','--out',folder],
                               capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stdout+run.stderr)
            report=json.loads((Path(folder)/'report.json').read_text())
            self.assertEqual(report['distances'],256)
            self.assertEqual(report['presence_bytes'],256)
            self.assertEqual(len(report['screens']),11)
            self.assertEqual(len(report['cases']),11)
            cases={c['case']:c for c in report['cases'] if c['case']!='panel-layout'}
            self.assertIn(5,cases['green-present']['chosen'])
            self.assertNotIn(8,cases['green-present']['chosen'])
            self.assertIn(10,cases['bitmap-only-change']['chosen'])
            self.assertNotIn(5,cases['bitmap-only-change']['chosen'])
