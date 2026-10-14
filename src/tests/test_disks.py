"""The four-disk build (docs/DISKS.md): the host side of the format, and the game on
four disks in the emulators, changing the disk as a person does."""
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'port/atari'))
from c64 import shared_root
import altirra
import disks

LOGICAL = ROOT / 'build/c64/original-v2-b/logical.bin'
TOOLS = (LOGICAL.exists() and (shared_root() / 'tools/toolchain/local/bin/ca65').exists()
         and ((ROOT / 'tools/zx02/compress.c').exists() or (shared_root() / 'tools/zx02/compress.c').exists())
         and shutil.which('cc') is not None)
EMULATOR = TOOLS and (shared_root() / 'tools/emulators/local/lib/libatari800.so').exists()


class Format(unittest.TestCase):
    """The index, the packing and the reference reader, on made-up data."""

    def disk(self):
        disk = disks.Disk('test disk')
        disk.add(5, bytes(range(256)) * 9 + bytes(100), name='packed or not')        # 2,404 bytes
        disk.add(20, b'abc' * 700, name='compressible')
        disk.add(100, bytes(i * 7 & 255 for i in range(2304)), raw=True, name='written')
        disk.add(0x296, bytes(512), raw=True, name='table')
        return disk

    def test_every_item_reads_back_as_the_kernel_reads_it(self):
        if not TOOLS:
            self.skipTest('needs the shared toolchain, the ZX02 compressor and a C compiler')
        disk = self.disk()
        body, used = disks.pack(disk)
        index = disks.index_of(bytes(body))
        self.assertEqual(index, used['index'])
        for block, item in disk.items.items():
            data = item['data']
            self.assertEqual(disks.read_item(body, index, block, 0, len(data)), data, item['name'])
            self.assertEqual(disks.read_item(body, index, block, 0, len(data) // 2), data[:len(data) // 2],
                             item['name'] + ' (a prefix)')

    def test_a_stored_run_has_an_entry_for_every_block(self):
        if not TOOLS:
            self.skipTest('needs the shared toolchain, the ZX02 compressor and a C compiler')
        body, used = disks.pack(self.disk())
        index = used['index']
        first, raw = index[100]
        self.assertTrue(raw)
        for k in range(9):          # 2,304 bytes: nine blocks, two sectors each
            self.assertEqual(index[100 + k], (first + 2 * k, True))
        self.assertNotIn(109, index)

    def test_a_block_the_disk_lacks_is_not_found(self):
        if not TOOLS:
            self.skipTest('needs the shared toolchain, the ZX02 compressor and a C compiler')
        body, used = disks.pack(self.disk())
        self.assertIsNone(disks.read_item(body, used['index'], 7, 0, 100))

    def test_the_index_is_at_the_end_of_an_enhanced_density_disk(self):
        self.assertEqual(disks.DISK_SECTORS, 1040)
        self.assertEqual(disks.INDEX_SECTOR + disks.INDEX_SECTORS - 1, 1040)
        self.assertGreaterEqual(disks.INDEX_SECTORS * 64, disks.IMAGE_BLOCK + 16)   # room for the boot pieces


@unittest.skipUnless(EMULATOR, 'needs tools/mmdisk.py output, cc65, ZX02 and libatari800 from the shared project')
class FourDisks(unittest.TestCase):
    SCRIPTS = ['boot-to-menu', 'boot-to-fight-and-save', 'boot-to-outdoors', 'boot-to-direct-if',
               'boot-to-treasure-and-reload']

    def lockstep(self, script, *options, timeout=900):
        run = subprocess.run([sys.executable, ROOT / 'port/atari/lockstep.py', ROOT / f'tools/traces/{script}.txt',
                              '--disks', *options], capture_output=True, text=True, timeout=timeout)
        self.assertEqual(run.returncode, 0, run.stdout[-1500:] + run.stderr[-800:])
        self.assertIn('OK: memory equal at all', run.stdout)
        for letter, number in zip('ABCD', range(1, 5)):
            self.assertIn(f'disk {number} (side {letter}): all ', run.stdout)
        return run.stdout

    def test_memory_and_every_item_of_every_disk_equal_the_oracle(self):
        """Each script in its own process: libatari800 is one machine per process."""
        for script in self.SCRIPTS:
            with self.subTest(script=script):
                self.lockstep(script)

    def test_with_the_os_doing_the_serial_transfers(self):
        self.lockstep('boot-to-treasure-and-reload', '--sio')

    def test_disk_d_is_read_after_the_swap(self):
        """boot-to-side-d is not this: its party meets an encounter at the portal and never goes through."""
        self.lockstep('boot-to-direct-if', '--sio')

    def test_with_the_c64_title_in_front(self):
        self.lockstep('boot-to-menu', '--title')

    def test_the_roster_is_written_to_disk_b_and_to_no_other(self):
        out = self.lockstep('boot-to-fight-and-save')
        self.assertIn('disk 2 (side B): all 111 items equal the oracle\'s; 18 bytes written', out)
        self.assertNotRegex(out, r'disk [134] \(side [ACD]\): all \d+ items equal the oracle\'s; \d+ bytes written')

    def test_the_game_asks_for_disk_b_until_it_has_it(self):
        for options in ([], ['--sio']):
            with self.subTest(options=options):
                run = subprocess.run([sys.executable, ROOT / 'port/atari/disks_check.py', *options],
                                     capture_output=True, text=True, timeout=900)
                self.assertEqual(run.returncode, 0, run.stdout[-1500:] + run.stderr[-800:])
                self.assertEqual(run.stdout.count('ok: '), 13)


@unittest.skipUnless(EMULATOR and altirra.program() is not None,
                     'needs tools/mmdisk.py output, cc65, ZX02, libatari800 and AltirraSDL')
class FourDisksInAltirra(unittest.TestCase):
    def test_a_save_and_the_swaps_with_the_os_doing_the_serial_transfers(self):
        run = subprocess.run([sys.executable, ROOT / 'port/atari/lockstep.py',
                              ROOT / 'tools/traces/boot-to-fight-and-save.txt', '--disks', '--altirra', '--sio'],
                             capture_output=True, text=True, timeout=900)
        self.assertEqual(run.returncode, 0, run.stdout[-1500:] + run.stderr[-800:])
        self.assertIn('OK: memory equal at all 14 marks', run.stdout)


if __name__ == '__main__':
    unittest.main()
