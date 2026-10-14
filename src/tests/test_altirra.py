import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'port/atari'))
from c64 import shared_root
import altirra

READY = ((ROOT / 'build/c64/original-v2-b/logical.bin').exists() and altirra.program() is not None
         and (shared_root() / 'tools/toolchain/local/bin/ca65').exists())


@unittest.skipUnless(READY, 'needs tools/mmdisk.py output, cc65 from the shared project and AltirraSDL')
class Play(unittest.TestCase):
    """The build in a second emulator: save a character, start again, walk into town."""

    def play(self, *options):
        run = subprocess.run([sys.executable, ROOT / 'port/atari/altirra_check.py', *options],
                             capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stdout[-600:] + run.stderr[-600:])
        self.assertEqual(run.stdout.count('ok: '), 43)

    def test_with_altirras_disk_patch(self):
        self.play()

    def test_with_the_os_doing_the_serial_transfers(self):
        self.play('--sio')

    def test_wilderness_combat_matches_the_oracle_with_serial_transfers(self):
        run = subprocess.run([sys.executable, ROOT / 'port/atari/lockstep.py',
                              ROOT / 'tools/traces/boot-to-wilderness-travel.txt', '--altirra', '--sio'],
                             capture_output=True, text=True, timeout=300)
        self.assertEqual(run.returncode, 0, run.stdout[-2000:] + run.stderr[-1000:])
        self.assertIn('OK: memory equal at all 13 marks', run.stdout)


class WorkingCopy(unittest.TestCase):
    def test_the_working_copy_is_found_by_the_images_hash(self):
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            disk = Path(folder) / 'a.atr'
            disk.write_bytes(b'abc')
            self.assertEqual(altirra.working_copy(disk, folder), Path(folder) / 'config/altirra/disk_state'
                             / 'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad' / 'disk.atr')


if __name__ == '__main__':
    unittest.main()
