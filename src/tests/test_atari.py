import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'port/atari'))
from c64 import shared_root
import lockstep
from coverage_check import CASES

SCRIPTS = ['boot-to-menu', 'boot-to-new-character', 'boot-to-town-services',
           'boot-to-fight-and-save', 'boot-to-outdoors', 'boot-to-side-d',
           'boot-to-treasure-and-reload', 'boot-to-death', 'boot-to-ctrl-attack']
SCRIPTS += ['boot-to-' + name for name in CASES]
READY = ((ROOT / 'build/c64/original-v2-b/logical.bin').exists()
         and (shared_root() / 'tools/emulators/local/lib/libatari800.so').exists()
         and (shared_root() / 'tools/toolchain/local/bin/ca65').exists())


@unittest.skipUnless(READY, 'needs tools/mmdisk.py output, cc65 and libatari800 from the shared project')
class Lockstep(unittest.TestCase):
    def test_atari_memory_and_disk_equal_the_oracle(self):
        """Each script in its own process: libatari800 is one machine per process."""
        for script in SCRIPTS:
            with self.subTest(script=script):
                run = subprocess.run([sys.executable, ROOT / 'port/atari/lockstep.py',
                                      ROOT / f'tools/traces/{script}.txt'], capture_output=True, text=True)
                self.assertEqual(run.returncode, 0, run.stdout[-600:] + run.stderr[-600:])
                self.assertIn('OK: memory equal at all', run.stdout)

    def test_with_a_key_at_every_pause_too(self):
        run = subprocess.run([sys.executable, ROOT / 'port/atari/lockstep.py',
                              ROOT / 'tools/traces/boot-to-fight-and-save.txt', '--quick'], capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stdout[-600:] + run.stderr[-600:])
        self.assertIn('OK: memory equal at all 14 marks', run.stdout)


@unittest.skipUnless(READY, 'needs tools/mmdisk.py output, cc65 and libatari800 from the shared project')
class Play(unittest.TestCase):
    def test_keyboard_play_reaches_the_town_and_walks(self):
        run = subprocess.run([sys.executable, ROOT / 'port/atari/play_check.py'], capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stdout[-600:] + run.stderr[-600:])
        self.assertEqual(run.stdout.count('ok: '), 9)


class Steps(unittest.TestCase):
    def test_a_direct_poll_keeps_its_triggering_key_and_caller(self):
        self.assertEqual(lockstep.atari_steps(['key 5f', 'press 4c', 'poll 89f0 20', 'ready']),
                         [['press', '4c'], ['poll', '89f0', '20'], ['ready']])

    def test_title_steps_are_skipped_and_mid_flight_marks_too(self):
        lines = ['until $41ab', 'mark title', 'key 5f', 'wait $100', 'mark insert-b',
                 'until $2500', 'mark monsters', 'press 49']
        self.assertEqual(lockstep.atari_steps(lines),
                         [['wait', '$100'], ['mark', 'insert-b'], ['skip', 'monsters'], ['press', '49']])

    def test_after_a_restart_the_title_steps_are_skipped_again(self):
        lines = ['key 5f', 'ready', 'mark saved', 'restart', 'until $41ab', 'mark title-2', 'key 5f',
                 'wait $100', 'mark insert-b-2', 'pauses 20']
        self.assertEqual(lockstep.atari_steps(lines),
                         [['ready'], ['mark', 'saved'], ['restart'], ['wait', '$100'], ['mark', 'insert-b-2'],
                          ['pauses', '20']])

    def test_ctrl_flag_is_set_before_the_key_and_cleared_after(self):
        lines = ['key 5f', 'press 01', 'until $78a2', 'poke 028e 04', 'ready']
        self.assertEqual(lockstep.atari_steps(lines),
                         [['poke', '028e', '04'], ['press', '01'], ['poke', '028e', '00'], ['ready']])


class Comparison(unittest.TestCase):
    def test_ignored_ranges_patches_and_the_held_counter(self):
        oracle = bytearray(65536)
        atari = bytearray(65536)
        atari[0x00a2] = 9           # clock: ignored
        atari[0x9d40] = 9           # kernel: ignored
        atari[0x1bdb] = 9           # a patched operand
        atari[0x002d] = 1           # held one instruction into the key wait
        self.assertEqual(lockstep.compare(atari, oracle, {0x1bdb}, waiting=True), [])
        self.assertEqual(lockstep.compare(atari, oracle, {0x1bdb}, waiting=False), [(0x2d, 1, 0)])
        atari[0x6000] = 5
        self.assertEqual(lockstep.compare(atari, oracle, set(), waiting=True),
                         [(0x1bdb, 9, 0), (0x6000, 5, 0)])


class Kernel(unittest.TestCase):
    def test_a_store_into_the_kernels_code_is_reported_and_its_variables_are_not(self):
        fixed = [{'file': 'under.bin', 'base': '$dc00', 'first': '$dc86', 'last': '$dd10'}]
        images = {'under.bin': bytes(range(256)) * 4}
        memory = bytearray(65536)
        memory[0xdc00:0xe000] = images['under.bin']
        memory[0xdc0d] = 0x7f       # the saved zero page: a variable
        self.assertEqual(lockstep.kernel_changes(memory, fixed, images), [])
        memory[0xdd02] |= 3         # what the game's store to CIA 2 did to LDA #>text_list
        self.assertEqual(lockstep.kernel_changes(memory, fixed, images), [(0xdd02, 0x03, 0x02)])

    def test_the_cia_registers_the_game_names_have_stand_ins_clear_of_the_key_entry(self):
        import build
        addresses = [build.stand_in('CIA', register) for register in build.CIA_REGISTERS]
        self.assertEqual(addresses, [0xffb0, 0xffb1, 0xffb2])
        self.assertEqual(build.stand_in('VIC-II', 0xd011), 0xff61)
        self.assertEqual(build.stand_in('SID', 0xd418), 0xffa8)
        with self.assertRaises(SystemExit):
            build.stand_in('CIA', 0xdc00)


if __name__ == '__main__':
    unittest.main()
