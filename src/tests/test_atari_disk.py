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
class Disk(unittest.TestCase):
    def test_exact_partial_upper_ram_reads_and_batched_write(self):
        with tempfile.TemporaryDirectory() as folder:
            run=subprocess.run([sys.executable,ROOT/'port/atari/disk_probe.py','--out',folder],
                               capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stdout+run.stderr)
            report=json.loads((Path(folder)/'report.json').read_text())
            self.assertTrue(report['exact'])
            self.assertEqual(report['cases'][0]['swaps'],2)
            self.assertEqual(report['cases'][0]['length'],1024)
            self.assertEqual(report['cases'][-1]['write_bytes'],2304)
            self.assertEqual(report['cases'][-1]['swaps'],2)
