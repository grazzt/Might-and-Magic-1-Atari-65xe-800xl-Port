#!/usr/bin/env python3
"""Measure the 64 KB direct display's input-to-next-wait latency (NTSC).

Uses first-poll scripted inputs and Atari800's patched disk, like speed_check.
It does not measure real keyboard delays or physical-drive load times.
"""
import json
import argparse
import ctypes
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'tools'), str(ROOT/'port/atari')]
import build
import lockstep
import profile65
from speed_check import ACTION_KEYS


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=ROOT/'test-artifacts/64k/speed')
    parser.add_argument('--transients', action='store_true')
    parser.add_argument('--assert-steady', action='store_true')
    parser.add_argument('--colour', action='store_true')
    args = parser.parse_args()
    if args.assert_steady and not args.transients:
        parser.error('--assert-steady requires --transients')
    layout = build.build(test=True, xe64=True, colour65=args.colour)
    game = lockstep.Game(layout)
    lines = (ROOT/'tools/traces/boot-to-town-services.txt').read_text().splitlines()
    lines = lines[:lines.index('mark party')+1]
    for words in lockstep.atari_steps(lines):
        op, values = words[0], words[1:]
        if op == 'press':
            game.press(int(values[0], 16))
        elif op == 'ready':
            game.ready()
        elif op == 'attach':
            game.attach(values[0])
        elif op == 'key':
            game.keys([int(v, 16) for v in values])
        elif op == 'wait':
            game.idle()
        elif op == 'pauses':
            game.memory[game.label['pause_key']] = int(values[0], 16)
        elif op == 'poke':
            for index, value in enumerate(values[1:]):
                game.memory[int(values[0], 16)+index] = int(value, 16)
    game.ready()
    folder = args.out
    folder.mkdir(parents=True, exist_ok=True)
    report = {'emulator': 'Atari800', 'ram_kb': 64, 'timing': 'NTSC, first-poll keys, patched disk', 'actions': []}
    for code, name, _ in ACTION_KEYS:
        game.memory[game.label['script_key']] = code
        states = []
        for count in range(1, 3000):
            game.frames(1)
            if args.transients:
                pixels = game.atari.screen()
                state = {'frame': count, 'visible_pixels': sum(v != 0 for v in pixels),
                         'dma': ctypes.c_ubyte.in_dll(game.atari._lib, 'ANTIC_DMACTL').value,
                         'shown_mode': game.memory[game.label['shown_mode']],
                         'frame_ready': game.memory[game.label['frame_ready']]}
                if hasattr(game, 'display65'):
                    x, y = game.display65.origin
                    state['view_pixels'] = sum(v != 0 for line in range(128)
                        for v in pixels[(y+line)*384+x:(y+line)*384+x+240])
                states.append(state)
                game.atari.screenshot(folder/f'{name}-{count:03d}.png')
            if not game.memory[game.label['script_key']] and game.memory[game.label['waiting']]:
                break
        else:
            raise AssertionError(f'{name}: next wait was not reached')
        game.frames(2)
        profile65.check_display(game, name)
        game.atari.screenshot(folder/f'{name}.png')
        result = {'action': name, 'frames': count, 'milliseconds': round(count*1000/59.923, 1), 'states': states}
        result['blank_frames'] = sum(s['visible_pixels'] == 0 for s in states)
        report['actions'].append(result)
        if args.assert_steady and name in ('step','turn-left','turn-right'):
            assert result['blank_frames'] == 0, f'{name}: display blacked out'
            assert all(s.get('view_pixels', 0) for s in states), f'{name}: view erased before publication'
        print(f'{name}: {count} frames', flush=True)
    (folder/'report.json').write_text(json.dumps(report, indent=2)+'\n')


if __name__ == '__main__':
    main()
