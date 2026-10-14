#!/usr/bin/env python3
"""Play the Atari build a little in AltirraSDL, a second emulator, through its
emulated keyboard, and check that the game follows.

  python3 port/atari/altirra_check.py [--sio]

First it creates a character named ALTI and saves it, which writes the roster
to the disk; then it starts the machine again from that disk and looks for the
name among the characters. Then the same short game as port/atari/play_check.py
plays in Atari800: the options menu, the inn, six characters into the party,
out into the town, one step. At each stop it checks the screen text, the
game's variables, that ANTIC is on the display list that goes with the screen,
and that the kernel's code is still as assembled (lockstep.kernel_changes).

--sio turns Altirra's disk patch off, so that the OS ROM does every sector
transfer over the emulated serial line with its own interrupts, as on a real
machine. Without it Altirra, like Atari800, answers the OS's disk call itself.

Writes build/atari/altirra/NAME.png for each stop (NAME-sio.png with --sio).
"""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'port/atari'))
import altirra                          # noqa: E402
import build                            # noqa: E402
import c64_sound                        # noqa: E402
import lockstep                         # noqa: E402
from play_check import expect           # noqa: E402


def text(emulator):
    """Non-empty lines of the C64 text screen at $0400."""
    screen = emulator.peek(0x0400, 1000)
    lines = []
    for row in range(25):
        line = ''.join(chr(c & 0x7f) if 32 <= c & 0x7f < 96 else ' ' for c in screen[row * 40:row * 40 + 40])
        if line.strip(' !-'):
            lines.append(line.strip(' !'))
    return lines


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--sio', action='store_true', help='no disk patch: the OS does the serial transfers')
    args = parser.parse_args()
    if not altirra.program():
        raise SystemExit('AltirraSDL is not installed (~/.local/bin/altirra, or set $ALTIRRA)')
    layout = build.build(test=False)
    label = {name: int(value[1:], 16) for name, value in layout['labels'].items()}
    images = {name: (build.OUT / name).read_bytes() for name in build.SEGMENTS}
    folder = build.OUT / 'altirra'
    folder.mkdir(exist_ok=True)
    disk = build.OUT / 'mm1.atr'                # Altirra writes to a working copy of its own
    emulator = altirra.Altirra(disk, folder, sio_patch=not args.sio)
    frames = [0]
    seen = lambda words: lambda: any(words in line for line in text(emulator))

    def until(condition, what, limit):
        """Run until the condition holds; the frames it took are reported."""
        start = frames[0]
        while not condition():
            if frames[0] - start >= limit:
                emulator.screenshot(folder / 'failed.png')
                raise SystemExit(f"FAILED: {what} (not after {limit} frames; PC ${emulator.registers()['PC']:04x}; "
                                 f'picture in {folder}/failed.png)')
            emulator.frame(10)
            frames[0] += 10
        print(f'ok: {what} (after {frames[0] - start} frames)')

    def stop(name, play):
        """Checks that hold at every stop, and its picture."""
        emulator.frame(4)
        memory = bytearray(65536)
        for base, image in ((build.SEGMENTS[file], images[file]) for file in images):
            memory[base:base + len(image)] = emulator.peek(base, len(image))
        expect(not lockstep.kernel_changes(memory, layout['fixed'], images), f"{name}: the kernel's code is as assembled")
        wanted = label['bitmap_list' if play else 'text_list']
        expect(emulator.antic()['list'] == wanted,
               f"{name}: ANTIC is on the {'play screen' if play else 'text'} display list")
        pokey = emulator.pokey()
        expect(pokey['AUDCTL'] == 0x50 and pokey['SKCTL'] == 3
               and all(pokey[f'AUDC{channel}'] == 0 for channel in (1, 3, 4)),
               f'{name}: game audio and keyboard restored after SIO')
        emulator.screenshot(folder / f"{name}{'-sio' if args.sio else ''}.png")

    try:
        until(seen('INSERT DISK B'), 'boots to the first prompt', 6000)
        stop('prompt', play=False)
        emulator.press('RETURN')
        until(seen('OPTIONS'), 'RETURN: the options menu, with no disk to swap', 6000)
        stop('menu', play=False)
        # Invoke the original effect 3 at the next VBI. The bridge cannot set
        # CPU registers, so use unused kernel padding and a one-shot IRQ vector.
        # Game code/data are untouched; the handler restores the original vector.
        vector = emulator.peek(0x0314, 2)
        probe = label['probe_scratch']
        code = [0xa9, vector[0], 0x8d, 0x14, 0x03, 0xa9, vector[1], 0x8d, 0x15, 0x03,
                0xa9, 3, 0x20, 0x57, 0xc5, 0x4c, vector[0], vector[1]]
        assert probe + len(code) <= 0xe000
        for offset, value in enumerate(code):
            emulator.poke(probe + offset, value)
        emulator.poke(0x0314, probe & 255)
        emulator.poke(0x0315, probe >> 8)
        emulator.frame(6)
        pokey = emulator.pokey()
        expect(pokey['AUDC2'] & 15 != 0, 'original effect 3 plays a POKEY note')
        sid = emulator.peek(label['fake_sid'], 2)
        expect(pokey['AUDF1'] | pokey['AUDF2'] << 8 == c64_sound.divisor(sid[0] | sid[1] << 8),
               'effect 3 pitch matches the SID sequence')
        emulator.press('C')
        until(seen('SELECT A CLASS'), 'C: a character is rolled', 3000)
        expect(emulator.pokey()['AUDC2'] & 15 == 0, 'C stops effect 3 through the original key reader')
        for _ in range(20):                     # RETURN rolls again
            if seen('6) ROBBER')():
                break
            emulator.press('RETURN', gap=30)
        emulator.press('6')
        until(seen('SELECT A RACE'), '6: a robber', 600)
        stop('create', play=False)
        for _ in range(3):                      # human, good, male
            emulator.press('1', gap=20)
        until(seen('NAME:'), '1 1 1: asked for a name', 600)
        for letter in 'ALTI':
            emulator.press(letter, gap=6)
        emulator.press('RETURN')
        until(seen('SAVE CHARACTER'), 'ALTI RETURN: asked whether to save', 600)
        emulator.press('Y')
        until(lambda: seen('SELECT A CLASS')() and not seen('SAVE CHARACTER')(), 'Y: saved, the next one is rolled', 6000)
        stop('saved', play=False)
        emulator.close()
        copy = altirra.working_copy(disk, folder).read_bytes()
        written = [i for i, (a, b) in enumerate(zip(copy, disk.read_bytes())) if a != b]
        side_b = 16 + (layout['boot_sectors'] + layout['sectors_per_side']) * 128
        expect(0 < len(written) < 512 and side_b <= written[0] and written[-1] < side_b + layout['sectors_per_side'] * 128,
               f'the save changed {len(written)} bytes of the disk, all on side B')

        emulator = altirra.Altirra(disk, folder, sio_patch=not args.sio, fresh=False)
        until(seen('INSERT DISK B'), 'starts again from the disk it wrote', 6000)
        emulator.press('RETURN')
        until(seen('OPTIONS'), 'RETURN: the options menu', 6000)
        emulator.press('V')
        until(seen('ALTI'), 'V: ALTI is among the characters', 3000)
        stop('roster', play=False)
        emulator.press('ESC')
        until(seen('OPTIONS'), 'ESC: back at the options menu', 3000)
        emulator.press('1')
        until(seen('INN OF SORPIGAL'), '1: the inn of Sorpigal', 6000)
        stop('inn', play=False)
        for letter in 'ABCDEF':
            emulator.press(letter, hold=4, gap=8, ctrl=True)
        until(seen('PARTY IS FULL'), 'CTRL-A to CTRL-F: six characters in the party', 600)
        emulator.press('X')
        until(lambda: emulator.peek(0x0389)[0] == 2 and emulator.peek(label['shown_mode'])[0] == 2
              and tuple(emulator.peek(0x3b, 2)) == (8, 3), 'X: in town at 8,3, play screen on', 12000)
        emulator.frame(30)
        stop('town', play=True)
        emulator.press('I')
        until(lambda: tuple(emulator.peek(0x3b, 2)) == (8, 4), 'I: one step forward', 3000)
        emulator.frame(60)
        stop('step', play=True)
    finally:
        emulator.close()


if __name__ == '__main__':
    main()
