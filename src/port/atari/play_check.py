#!/usr/bin/env python3
"""Play the Atari build a little through the emulated keyboard, as a person
would, and check that the game follows.

  python3 port/atari/play_check.py

Unlike port/atari/lockstep.py this uses the build people play: keys come from
POKEY through the kernel's keyboard routine, the key wait is not held, and the
kernel picks the disk side the game asks for. It checks the screen text, a
few game variables and which display list ANTIC is on; it does not compare
with the oracle, because real key timing is not the oracle's.

Writes build/atari/play-town.png and play-step.png.
"""
from pathlib import Path
import argparse
import ctypes
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'port/atari'))
from c64 import shared_root            # noqa: E402
import build                            # noqa: E402
import lockstep                         # noqa: E402


def text(atari):
    """Non-empty lines of the C64 text screen at $0400."""
    screen = bytes(atari.memory[0x0400:0x0400 + 1000])
    lines = []
    for row in range(25):
        line = ''.join(chr(c & 0x7f) if 32 <= c & 0x7f < 96 else ' ' for c in screen[row * 40:row * 40 + 40])
        if line.strip(' !-'):
            lines.append(line.strip(' !'))
    return lines


def expect(condition, what):
    if not condition:
        raise SystemExit(f'FAILED: {what}')
    print(f'ok: {what}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--65xe', dest='xe64', action='store_true')
    parser.add_argument('--colour', action='store_true')
    args = parser.parse_args()
    if args.colour and not args.xe64:
        parser.error('--colour requires --65xe')
    layout = build.build(test=False, xe64=args.xe64, colour65=args.colour)
    label = {name: int(value[1:], 16) for name, value in layout['labels'].items()}
    sys.path.insert(0, str(shared_root() / 'port/atari'))
    from harness import Atari
    atari = Atari(build.OUT / 'mm1.atr', extra_args=['-xl' if args.xe64 else '-xe'])
    if args.xe64:
        expect(ctypes.c_int.in_dll(atari._lib, 'MEMORY_ram_size').value == 64,
               'the requested RAM size is configured')
    atari.frame(300)
    play(atari, label, out=build.OUT)


def play(atari, label, out=build.OUT):
    """The short game, from the first prompt. Also played after the title
    (port/atari/title_check.py)."""
    memory = atari.memory
    expect(any('INSERT DISK B' in line for line in text(atari)), 'boots to the first prompt')
    atari.type('\r')
    atari.frame(200)
    expect(any('OPTIONS' in line for line in text(atari)), 'RETURN: the options menu, with no disk to swap')
    expect(lockstep.display_list(atari) == label['text_list'], 'ANTIC is on the text display list')
    atari.type('1')
    atari.frame(150)
    expect(any('INN OF SORPIGAL' in line for line in text(atari)), '1: the inn of Sorpigal')
    for letter in 'abcdef':
        atari.input.control, atari.input.keychar = 1, ord(letter)
        atari.frame(4)
        atari.input.control = atari.input.keychar = 0
        atari.frame(8)
    atari.frame(60)
    expect(any('PARTY IS FULL' in line for line in text(atari)), 'CTRL-A to CTRL-F: six characters in the party')
    atari.type('x')
    atari.frame(300)
    expect(memory[0x0389] == 2 and (memory[0x3b], memory[0x3c]) == (8, 3), 'X: in town at 8,3, play screen on')
    expect(lockstep.display_list(atari) == label['bitmap_list'], "ANTIC is on the play screen's display list")
    atari.screenshot(out / 'play-town.png')
    atari.type('i')
    atari.frame(120)
    expect((memory[0x3b], memory[0x3c]) == (8, 4), 'I: one step forward')
    atari.screenshot(out / 'play-step.png')
    colours = set(atari.screen())
    expect(len(colours) >= 4, 'the play screen is drawn in several colours')


if __name__ == '__main__':
    main()
