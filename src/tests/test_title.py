import json
import math
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'tools'), str(ROOT / 'port/atari')]
from c64 import shared_root
import altirra
import build
import c64_screen
import c64_sound
import oracle

DECODED = (ROOT / 'build/c64/original-v2-a/logical.bin').exists()
READY = (DECODED and (shared_root() / 'tools/emulators/local/lib/libatari800.so').exists()
         and (shared_root() / 'tools/toolchain/local/bin/ca65').exists())


ORACLE = DECODED and (shared_root() / 'tools/emulators/local/usr/share/vice/C64/kernal-901227-03.bin').exists()


@unittest.skipUnless(ORACLE, 'needs tools/mmdisk.py output and the VICE ROMs')
class Reference(unittest.TestCase):
    """The reference the Atari's title is checked against is VICE's."""

    def test_the_oracles_title_and_scenes_equal_the_vice_recording(self):
        folder = ROOT / 'test-artifacts/c64/trace-title-scenes'
        player, pictures = oracle.Oracle(), {}
        player.play((ROOT / 'tools/traces/title-scenes.txt').read_text().splitlines(),
                    on_mark=lambda name: pictures.__setitem__(name, player.picture()))
        reference = json.loads((folder / 'trace.json').read_text())
        self.assertIsNone(oracle.compare(player.events, reference))
        self.assertEqual(sum('command' in event for event in player.events), 20)
        for name, rows in pictures.items():
            count, where = c64_screen.differences(c64_screen.vice_picture(folder / f'{name}.png'), rows)
            self.assertEqual(count, 0, f'{name}: rows {where[:3]}')
        self.assertEqual(sorted(pictures), ['frame-1', 'frame-2', 'frame-again'] + [f'scene-{n}' for n in range(2, 10)])


@unittest.skipUnless(DECODED, 'needs tools/mmdisk.py output')
class Tune(unittest.TestCase):
    """What build.py reads out of the C64 title program."""

    def test_three_voices_of_the_same_length(self):
        tune = build.title_tune()
        self.assertEqual(tune['starts'], [0x4d16, 0x4e2f, 0x4ec4])
        self.assertEqual(tune['waveforms'], [0x40, 0x40, 0x20])        # pulse, pulse, sawtooth
        self.assertEqual(tune['registers'][24], 15)                    # full volume
        self.assertEqual([len(voice) for voice in tune['voices']], [70, 37, 19])
        self.assertEqual([sum(length for _, length, _ in voice) for voice in tune['voices']], [850, 850, 849])

    def test_every_pitch_fits_pokey(self):
        tune = build.title_tune()
        notes = {frequency: (hz, wide, narrow) for frequency, hz, wide, narrow in build.title_notes(tune)}
        self.assertEqual(len(notes), 14)
        cents = lambda actual, wanted: abs(1200 * math.log2(actual / wanted))
        for voice, pitches in enumerate(tune['voices']):
            for frequency in {f for f, _, _ in pitches if f >= 0x100}:
                hz, wide, narrow = notes[frequency]
                if voice == 0:      # the joined channels: as good as exact
                    self.assertLess(cents(c64_sound.POKEY_CLOCK / (2 * (wide + 7)), hz), 1)
                else:               # one channel at 64 kHz: within a seventh of a semitone
                    self.assertLess(cents(c64_sound.POKEY_CLOCK / 28 / (2 * (narrow + 1)), hz), 14)
        self.assertAlmostEqual(notes[0x1c31][0], 440, delta=0.1)       # in tune on an NTSC C64

    def test_the_frames_three_colours(self):
        self.assertEqual(build.title_colours(), (0x25, 0x01))          # red and green in the matrix, white


@unittest.skipUnless(DECODED, 'needs tools/mmdisk.py output')
class Operands(unittest.TestCase):
    def test_the_title_program_is_touched_only_for_the_title(self):
        plain, with_title = build.patches(), build.patches(title=True)
        self.assertFalse([p for p in plain if p[4] == 'title'])
        self.assertEqual([p for p in with_title if p[4] != 'title'], plain)
        title = [p for p in with_title if p[4] == 'title']
        self.assertEqual(len({pc for *_, pc in title}), 25)            # 11 video, 11 sound, 3 CIA
        self.assertTrue(all(side == 'A' and offset < 0x0f80 for side, offset, *_ in title))
        program = build.title_program()[1]
        for _, offset, old, new, _, _ in title:                        # every one an operand naming a C64 chip
            self.assertEqual(program[offset], old)
        highs = {new for _, offset, _, new, _, pc in title if offset == pc - 0x4000 + 2}
        self.assertEqual(highs, {0xff})                                # all in the stand-in registers at $FF50


class Prepared(unittest.TestCase):
    """title_check.py's own model of what src/title.s does to the colour matrix."""

    def test_unused_colours_become_the_frames_or_the_commonest(self):
        import title_check
        memory = bytearray(65536)
        bitmap, matrix = title_check.BITMAP, title_check.MATRIX
        for cell in range(1000):
            memory[matrix + cell] = 0x25
        for row, col in ((0, 0), (5, 0), (20, 39)):                    # the frame: pair 01, red
            memory[bitmap + row * 320 + col * 8] = 0x15
        memory[matrix + 5 * 40 + 10] = 0xea                            # a picture cell drawing both colours
        memory[bitmap + 5 * 320 + 10 * 8] = 0x18                       # pairs 01 and 10
        memory[matrix + 6 * 40 + 10] = 0xea                            # and one drawing only its low colour
        memory[bitmap + 6 * 320 + 10 * 8] = 0x20
        memory[matrix + 20 * 40 + 5] = 0xbb                            # text: neither
        self.assertEqual(bytes(title_check.prepared(memory, 2)), bytes(memory))        # even scenes: untouched
        out = title_check.prepared(memory, 3)
        self.assertEqual(out[matrix], 0x22)                            # frame cell: its green is not drawn
        self.assertEqual(out[matrix + 5 * 40 + 10], 0xea)
        self.assertEqual(out[matrix + 6 * 40 + 10], 0x2a)
        self.assertEqual(out[matrix + 5 * 40 + 20], 0x2a)              # empty, in the pictures' rows: frame + commonest
        self.assertEqual(out[matrix + 20 * 40 + 5], 0x22)              # empty, below: the frame's only


@unittest.skipUnless(READY, 'needs decoded game files, cc65 and libatari800 from the shared project')
class Title(unittest.TestCase):
    def test_frames_tune_scenes_and_escape_in_atari800(self):
        run = subprocess.run([sys.executable, ROOT / 'port/atari/title_check.py'], capture_output=True, text=True,
                             timeout=300)
        self.assertEqual(run.returncode, 0, run.stdout[-1200:] + run.stderr[-1200:])
        self.assertEqual(run.stdout.count('ok: '), 32)

    def test_the_game_after_the_title_equals_the_oracle(self):
        """Two scripts with the title first; the second starts the machine twice."""
        for script, marks in (('boot-to-menu', 2), ('boot-to-treasure-and-reload', 27)):
            with self.subTest(script=script):
                run = subprocess.run([sys.executable, ROOT / 'port/atari/lockstep.py',
                                      ROOT / f'tools/traces/{script}.txt', '--title'], capture_output=True, text=True)
                self.assertEqual(run.returncode, 0, run.stdout[-600:] + run.stderr[-600:])
                self.assertIn(f'OK: memory equal at all {marks} marks', run.stdout)

    def test_the_disk_without_the_title_has_no_trace_of_it(self):
        """The boot code's title part is conditional, the title stage is the
        last thing on the disk and side A's title program is patched only for
        it: the two disks differ in nothing else."""
        with_title = build.build(test=False, title=True)
        titled = (build.OUT / 'mm1.atr').read_bytes()
        stage = (build.OUT / 'title.bin').stat().st_size
        layout = build.build(test=False, title=False)
        plain = (build.OUT / 'mm1.atr').read_bytes()
        self.assertFalse(layout['title'])
        self.assertFalse([p for p in layout['patches'] if p['module'] == 'title'])
        self.assertNotIn('title_load', (build.OUT / 'loads.inc').read_text())
        self.assertEqual(len(titled) - len(plain), -(-stage // 256) * 256)
        boot = 16 + 128 * layout['boot_sectors']
        differing = {i for i in range(boot, len(plain)) if plain[i] != titled[i]}
        patched = {boot + p['offset'] for p in with_title['patches'] if p['module'] == 'title'}
        self.assertEqual(differing, patched)


@unittest.skipUnless(READY and altirra.program() is not None, 'needs AltirraSDL as well')
class TitleInAltirra(unittest.TestCase):
    def play(self, *options):
        run = subprocess.run([sys.executable, ROOT / 'port/atari/title_check.py', '--altirra', *options],
                             capture_output=True, text=True, timeout=600)
        self.assertEqual(run.returncode, 0, run.stdout[-1200:] + run.stderr[-1200:])
        self.assertEqual(run.stdout.count('ok: '), 12)

    def test_with_altirras_disk_patch(self):
        self.play()

    def test_with_the_os_doing_the_serial_transfers(self):
        self.play('--sio')


if __name__ == '__main__':
    unittest.main()
