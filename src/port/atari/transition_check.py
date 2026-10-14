#!/usr/bin/env python3
"""Capture graphics-to-character-screen transitions with ordinary Atari800 keys.

python3 port/atari/transition_check.py --out build/atari/reverse
Builds the playable kernel, not the held first-poll test kernel. Records every
frame for visual inspection; passing settled checks alone does not prove that
all transient pixels are correct. Uses the sibling project's emulator only.
"""
import argparse
import ctypes
import json
import shutil
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'tools'), str(ROOT / 'port/atari')]
import build
import lockstep
from c64 import shared_root


def check(out):
    layout = build.build(test=False)
    labels = {k: int(v[1:], 16) for k, v in layout['labels'].items()}
    images = {name: (build.OUT / name).read_bytes() for name in build.SEGMENTS}
    sys.path.insert(0, str(shared_root() / 'port/atari'))
    from harness import Atari
    # Keep any emulator disk writes away from the deliverable.
    out.mkdir(parents=True, exist_ok=True)
    disk = out / 'play.atr'
    shutil.copyfile(build.OUT / 'mm1.atr', disk)
    atari = Atari(disk, extra_args=['-xe'])
    atari.frame(300)
    assert b'INSERT DISK B' in bytes(atari.memory[0x400:0x7e8])
    atari.type('\r')
    atari.frame(200)
    atari.type('1')
    atari.frame(150)
    for letter in 'abcdef':
        atari.input.control, atari.input.keychar = 1, ord(letter)
        atari.frame(4)
        atari.input.control = atari.input.keychar = 0
        atari.frame(8)
    atari.frame(60)
    atari.type('x')
    atari.frame(300)
    assert atari.memory[0x389] in (1, 2)
    rows = []
    for character in '123456':
        # Vary when the next real key arrives, without moving onto an event.
        atari.frame(120 + int(character))
        assert atari.memory[0x389] in (1, 2)
        atari.screenshot(out / f'char{character}-start.png')
        for frame in range(1, 41):
            atari.input.keychar = ord(character) if frame <= 12 else 0
            atari.frame()
            memory = atari.memory
            rows.append(dict(character=character, frame=frame, pc=atari.cpu()['PC'],
                             display_list=lockstep.display_list(atari),
                             dma=ctypes.c_ubyte.in_dll(atari._lib, 'ANTIC_DMACTL').value,
                             mode=memory[0x389], shown=memory[labels['shown_mode']],
                             ready=memory[labels['frame_ready']], view_page=memory[7]))
            atari.screenshot(out / f'char{character}-{frame:03}.png')
        assert atari.memory[0x389] == atari.memory[labels['shown_mode']] == 0
        assert lockstep.display_list(atari) == labels['text_list']
        assert not lockstep.kernel_changes(bytes(atari.memory), layout['fixed'], images)
        print(f'Character {character}: text screen settled, kernel intact; 40 frames captured')
        atari.type('\x1b', hold=12, gap=12)
        atari.frame(200)
    (out / 'report.json').write_text(json.dumps(rows, indent=2) + '\n')
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=build.OUT / 'reverse')
    check(parser.parse_args().out)


if __name__ == '__main__':
    main()
