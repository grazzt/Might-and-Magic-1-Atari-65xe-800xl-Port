"""Temporary intro rendering and memory reclamation on stock 64 KB."""
import subprocess
import json
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'tools'),str(ROOT/'port/atari')]
import build
from c64 import shared_root
import title65

READY=((ROOT/'build/c64/original-v2-b/logical.bin').exists()
       and (shared_root()/'tools/toolchain/local/bin/ca65').exists())
EMULATOR=READY and (shared_root()/'tools/emulators/local/lib/libatari800.so').exists()


class Nibble(unittest.TestCase):
    def test_compact_table_matches_all_full_byte_mappings(self):
        compact=title65.nibble_table()
        self.assertEqual(len(compact),256)
        for mapping in range(16):
            roles=(0,mapping & 3,mapping >> 2,3)
            for value in range(256):
                actual=compact[(mapping<<4)|(value>>4)]<<4|compact[(mapping<<4)|(value&15)]
                expected=0
                for shift in (6,4,2,0):expected |= roles[(value>>shift)&3]<<shift
                self.assertEqual(actual,expected,(mapping,value))


@unittest.skipUnless(READY,'needs original logical data and cc65')
class Memory(unittest.TestCase):
    def test_title_adds_no_permanent_kernel_bytes(self):
        self.addCleanup(build.select_profile,False)
        plain=build.build_disks(test=True,xe64=True)
        original={n:(build.OUT/n).read_bytes() for n in build.SEGMENTS}
        title=build.build_disks(test=True,xe64=True,title=True)
        self.assertEqual(title['memory65']['resident_segments_bytes'],plain['memory65']['resident_segments_bytes'])
        self.assertEqual(original,{n:(build.OUT/n).read_bytes() for n in build.SEGMENTS})
        self.assertLessEqual(build.TITLE_AT+(build.OUT/'title.bin').stat().st_size,0x9d00)
        for disk in title['disks']:self.assertLess(disk['sectors'],title['index_sector'])


@unittest.skipUnless(EMULATOR,'needs libatari800')
class Intro(unittest.TestCase):
    def check_intro(self,single=False):
        command=[sys.executable,str(ROOT/'port/atari/title65_check.py'),
                 '--out',str(ROOT/'build/atari65xe'/('title-test-single' if single else 'title-test-disks'))]
        if single:command.append('--single')
        run=subprocess.run(command,capture_output=True,text=True,timeout=300)
        self.assertEqual(run.returncode,0,run.stdout[-1500:]+run.stderr[-1500:])
        self.assertIn('OK: original frames, eight scenes, loop and Escape on 64 KB',run.stdout)
        folder=Path(command[command.index('--out')+1])
        report=json.loads((folder/'report.json').read_text())
        self.assertGreater(report['music']['matched_ticks'],1860)
        self.assertLessEqual(report['music']['late_frames'],8)

    def test_four_disks(self):self.check_intro()
    def test_single_image(self):self.check_intro(single=True)
