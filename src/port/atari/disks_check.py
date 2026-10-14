#!/usr/bin/env python3
"""Play the four-disk build as a person with a real drive would, and check the
disk prompts (docs/DISKS.md).

  python3 port/atari/disks_check.py [--sio] [--no-title]

Unlike port/atari/lockstep.py --disks this is the build people play (keys
through POKEY, the title in front, nothing held), and nothing tells the kernel
which disk is in the drive: only the emulator's disk image is changed, as a
player changes the disk. It checks that

  the game asks for disk B (the boot disk is in the drive) and keeps asking
    while disk A, or the wrong game disk, is in;
  disk B in the drive and RETURN lead to the options menu;
  the short game of play_check.py then goes as it does from one big image;
  nothing has been written to any of the four disks by then (the saves, and
    the roster on disk B, are checked by lockstep.py --disks).

--sio: the OS does every transfer over the emulated serial line, as on a real
machine (Atari800's fast disk patch off).

Writes build/atari/disks-check/ with the disk images, as played, and
pictures of the prompts.
"""
import argparse
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'port/atari'))
from c64 import shared_root            # noqa: E402
import build                            # noqa: E402
import disks                            # noqa: E402
import lockstep                         # noqa: E402
from play_check import expect, text    # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--sio', action='store_true', help='real serial transfers, not the emulator shortcut')
    parser.add_argument('--no-title', action='store_true', help='start at the game, not the C64 title')
    args = parser.parse_args()
    layout = build.build_disks(test=False, title=not args.no_title)
    label = {name: int(value[1:], 16) for name, value in layout['labels'].items()}
    out = build.OUT / 'disks-check'
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    played = [out / f'disk{n}.atr' for n in range(1, 5)]
    for n, copy in enumerate(played, 1):
        shutil.copyfile(build.DISKS_OUT / f'mm1-disk{n}.atr', copy)
    sys.path.insert(0, str(shared_root() / 'port/atari'))
    from harness import Atari
    atari = Atari(played[0], extra_args=['-xe'], sio_patch=not args.sio)
    memory = atari.memory

    def until(condition, what, limit=9000):
        start = atari.frames
        while not condition():
            if atari.frames - start >= limit:
                atari.screenshot(out / 'failed.png')
                raise SystemExit(f"FAILED: {what} (not after {limit} frames; PC ${atari.cpu()['PC']:04x})")
            atari.frame(1)
        return atari.frames - start

    def prompt(letter):
        return any(f'INSERT DISK {letter}' in line for line in text(atari))

    if not args.no_title:
        at_title = lambda: ((memory[0x0314], memory[0x0315]) == (0xe0, 0x4b)
                            and memory[0xfffb] == label['title.title_nmi'] >> 8)
        until(at_title, 'the title')
        atari.frame(60)
        atari.type('\x1b')
    frames = until(lambda: prompt('B') and memory[label['idle']], 'the first prompt')
    expect(True, f'boot disk in the drive: the game asks for disk B ({frames} frames after the title)')
    atari.screenshot(out / 'insert-b.png')

    atari.type('\r')
    atari.frame(300)
    expect(prompt('B') and not any('OPTIONS' in line for line in text(atari)),
           'RETURN with the boot disk still in the drive: asks for disk B again')
    atari.mount_disk(played[2])
    atari.type('\r')
    atari.frame(300)
    expect(prompt('B') and not any('OPTIONS' in line for line in text(atari)),
           'disk C in the drive: asks for disk B again')
    atari.screenshot(out / 'wrong-disk.png')
    atari.mount_disk(played[1])
    atari.type('\r')
    atari.frame(300)
    expect(any('OPTIONS' in line for line in text(atari)), 'disk B in the drive: the options menu')
    expect(lockstep.display_list(atari) == label['text_list'], 'ANTIC is on the text display list')
    atari.type('1')
    atari.frame(200)
    expect(any('INN OF SORPIGAL' in line for line in text(atari)), '1: the inn of Sorpigal')
    for letter in 'abcdef':
        atari.input.control, atari.input.keychar = 1, ord(letter)
        atari.frame(4)
        atari.input.control = atari.input.keychar = 0
        atari.frame(8)
    atari.frame(60)
    expect(any('PARTY IS FULL' in line for line in text(atari)), 'CTRL-A to CTRL-F: six characters in the party')
    atari.type('x')
    atari.frame(400)
    expect(memory[0x0389] == 2 and (memory[0x3b], memory[0x3c]) == (8, 3), 'X: in town at 8,3, play screen on')
    atari.type('i')
    atari.frame(150)
    expect((memory[0x3b], memory[0x3c]) == (8, 4), 'I: one step forward')
    atari.screenshot(out / 'town.png')
    atari._lib.libatari800_exit()
    for n, path in enumerate(played, 1):
        body = path.read_bytes()[16:]
        original = (build.DISKS_OUT / f'mm1-disk{n}.atr').read_bytes()[16:]
        expect(body == original, f'disk {n} is as it was built (nothing was written to it so far)')


if __name__ == '__main__':
    main()
