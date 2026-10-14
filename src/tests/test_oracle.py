import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from c64 import shared_root
import c64_screen
from c64_trace import quick, segments, settled
import oracle

# Script and the VICE recording it must reproduce (test-artifacts/c64/README.md).
RUNS = [('boot-to-outdoors', 'trace-outdoors'), ('boot-to-fight-and-save', 'trace-fight-save'),
        ('boot-to-town-services', 'trace-town-services'), ('boot-to-side-d', 'trace-side-d'),
        ('boot-to-new-character', 'trace-new-character')]
# Recorded later, without settled pictures: treasure, a save and a restart; a party wiped out.
MORE = [('boot-to-treasure-and-reload', 'trace-treasure-reload'), ('boot-to-death', 'trace-death')]
# What may differ between two runs of one session that took different time (docs/ORACLE.md).
TIMING = (set(range(0x00a0, 0x00a3)) | set(range(0x0100, 0x0200)) | set(range(0x9d00, 0xa000))
          | {0x0029, 0x002a, 0x03a0, 0xc353, 0xc354, 0xc40c, 0xc69f})
READY = ((ROOT / 'build/c64/original-v2-b/logical.bin').exists()
         and (shared_root() / 'tools/emulators/local/usr/share/vice/C64/kernal-901227-03.bin').exists())


@unittest.skipUnless(READY, 'needs tools/mmdisk.py output and the KERNAL ROM of the shared VICE')
class AgainstVice(unittest.TestCase):
    def test_every_recorded_session_replays_identically(self):
        for script, folder in RUNS + MORE:
            with self.subTest(script=script):
                events = oracle.Oracle().play((ROOT / f'tools/traces/{script}.txt').read_text().splitlines())
                reference = json.loads((ROOT / f'test-artifacts/c64/{folder}/trace.json').read_text())
                self.assertIsNone(oracle.compare(events, reference))
                self.assertGreater(len(oracle.comparable(events)), 50)

    def test_a_changed_key_is_noticed(self):
        lines = (ROOT / 'tools/traces/boot-to-new-character.txt').read_text().splitlines()
        lines = ['press 32             # 2' if line.startswith('press 31') else line for line in lines]
        events = oracle.Oracle().play(lines)
        reference = json.loads((ROOT / 'test-artifacts/c64/trace-new-character/trace.json').read_text())
        self.assertIsNotNone(oracle.compare(events, reference))


@unittest.skipUnless(READY, 'needs tools/mmdisk.py output and the KERNAL ROM of the shared VICE')
class Rules(unittest.TestCase):
    def test_a_key_at_every_pause_changes_nothing_but_time(self):
        lines = (ROOT / 'tools/traces/boot-to-fight-and-save.txt').read_text().splitlines()
        plain, fast = oracle.Oracle(), oracle.Oracle()
        plain.play(lines)
        fast.play(quick(lines))
        self.assertEqual(plain.events, fast.events)
        self.assertEqual(plain.logical('B'), fast.logical('B'))
        self.assertLess(fast.cpu.cycles * 3, plain.cpu.cycles)
        a, b = plain.machine.ram_image(), fast.machine.ram_image()
        self.assertEqual({i for i in range(65536) if a[i] != b[i]} - TIMING, set())
        reference = json.loads((ROOT / 'test-artifacts/c64/quick-fight-save/trace.json').read_text())
        self.assertIsNone(oracle.compare(fast.events, reference))

    def test_the_key_that_ends_a_pause_is_remembered_as_the_last_key(self):
        lines = (ROOT / 'tools/traces/boot-to-fight-and-save.txt').read_text().splitlines()
        lines = lines[:lines.index('mark fight') + 1]
        plain, fast = oracle.Oracle(), oracle.Oracle()
        plain.play(lines)
        fast.play(quick(lines))
        self.assertEqual((plain.mem[0x0371], fast.mem[0x0371]), (0x59, 0x20))     # Y; the pause's key

    def test_a_restart_reads_what_the_game_saved(self):
        player = oracle.Oracle()
        player.play((ROOT / 'tools/traces/boot-to-treasure-and-reload.txt').read_text().splitlines())
        roster = [e['sha256'] for e in player.events if e.get('name') in ('read', 'write') and e['address'] == '$6000']
        first_read, written, after_restart = roster[0], roster[-2], roster[-1]
        self.assertEqual(written, after_restart)
        self.assertNotEqual(first_read, after_restart)
        self.assertEqual(sum('restart' in e for e in player.events), 1)

    def test_playing_a_script_in_two_calls_is_playing_it_in_one(self):
        """The join must not add a pass of the key wait: the passes feed the dice."""
        lines = (ROOT / 'tools/traces/boot-to-new-character.txt').read_text().splitlines()
        cut = lines.index('mark rolled') + 1
        whole, parts = oracle.Oracle(), oracle.Oracle()
        whole.play(lines)
        parts.play(lines[:cut])
        parts.play(lines[cut:])
        self.assertEqual(whole.machine.ram_image(), parts.machine.ram_image())
        self.assertEqual(whole.events, parts.events)


class Scripts(unittest.TestCase):
    def test_quick_switches_pause_keys_on_at_the_first_ready_of_each_machine(self):
        lines = ['until $41ab', 'ready', 'mark menu', 'ready', 'restart', 'key 5f', 'ready', 'press 31']
        self.assertEqual(quick(lines), ['until $41ab', 'ready', 'pauses 20', 'mark menu', 'ready', 'restart',
                                        'key 5f', 'ready', 'pauses 20', 'press 31'])

    def test_a_script_is_cut_at_its_restarts(self):
        self.assertEqual(segments(['ready', 'restart  # off and on', 'key 5f', 'restart']),
                         [['ready'], ['key 5f'], []])


@unittest.skipUnless(READY, 'needs tools/mmdisk.py output and the KERNAL ROM of the shared VICE')
class Pictures(unittest.TestCase):
    def test_every_picture_equals_the_vice_screenshot(self):
        """The settled sessions: other key timing than the plain ones, so they
        are five more sessions to agree on, and every mark has a screenshot."""
        compared = 0
        for script, folder in RUNS:
            folder = ROOT / 'test-artifacts/c64' / folder.replace('trace-', 'settled-')
            with self.subTest(script=script):
                player = oracle.Oracle()
                lines = settled((ROOT / f'tools/traces/{script}.txt').read_text().splitlines())
                pictures = {}
                player.play(lines, on_mark=lambda name: pictures.__setitem__(name, player.picture()))
                reference = json.loads((folder / 'trace.json').read_text())
                self.assertIsNone(oracle.compare(player.events, reference))
                for name, rows in pictures.items():
                    count, where = c64_screen.differences(c64_screen.vice_picture(folder / f'{name}.png'), rows)
                    self.assertEqual(count, 0, f'{script} {name}: rows {where[:3]}')
                    compared += 1
        self.assertEqual(compared, 66)


class Comparison(unittest.TestCase):
    def test_boot_calls_cycle_counts_and_checks_are_ignored(self):
        vice = [{'command': 3, 'name': 'get disk id', 'caller': '$21fc', 'side': 'A', 'cycle': 1},
                {'command': 0, 'name': 'read', 'caller': '$425f', 'side': 'A', 'address': '$c9e8',
                 'length': '$0218', 'offset': '$00', 'block': '$0190', 'sha256': 'x', 'cycle': 9,
                 'x': 1, 'y': 2, 'ram_check': {}},
                {'mark': 'title', 'pc': '$41ab', 'port_01': '$36'}, {'keys': 'I'}, {'text': [' 0, 0: HI']}]
        mine = [{'command': 0, 'name': 'read', 'caller': '$425f', 'side': 'A', 'address': '$c9e8',
                 'length': '$0218', 'offset': '$00', 'block': '$0190', 'sha256': 'x'},
                {'mark': 'title', 'pc': '$1234', 'port_01': '$36'}, {'keys': 'I'}, {'text': [' 0, 0: HI']}]
        self.assertIsNone(oracle.compare(mine, vice))
        mine[-1] = {'text': [' 0, 0: HO']}
        self.assertEqual(oracle.compare(mine, vice)[0], 3)
        self.assertEqual(oracle.compare(mine[:-1], vice)[0], 3)


if __name__ == '__main__':
    unittest.main()
