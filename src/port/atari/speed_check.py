#!/usr/bin/env python3
"""Measure input-to-next-wait frames and photograph transient display states.

python3 port/atari/speed_check.py --out test-artifacts/speed/before-atari800
python3 port/atari/speed_check.py --emulator altirra --out test-artifacts/speed/before-altirra
python3 port/atari/speed_check.py --emulator vice --out test-artifacts/speed/c64
python3 port/atari/speed_check.py --cache-probe
Test kernel holds the first key poll; game inputs and RNG follow lockstep rules.
"""
import argparse
import ctypes
import hashlib
import json
import re
import subprocess
import tempfile
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'tools'), str(ROOT / 'port/atari')]
import altirra
import build
import lockstep

ACTION_KEYS = [(0x58, 'enter-town', True), (0x49, 'step', False),
               (0x4a, 'turn-left', False), (0x4c, 'turn-right', False),
               (0x23, 'choose-character', False), (0x36, 'character-sheet', True),
               (0x5f, 'back-to-town', True)]


class Runner:
    def __init__(self, layout, name, out):
        self.label = {k: int(v[1:], 16) for k, v in layout['labels'].items()}
        self.name, self.frames = name, 0
        if name == 'altirra':
            self.emulator = altirra.Altirra(build.OUT / 'mm1.atr', out / 'emulator')
        else:
            self.game = lockstep.Game(layout)
            self.emulator = self.game.atari

    def read(self, address, length=1):
        if self.name == 'altirra':
            return self.emulator.peek(address, length)
        return bytes(self.emulator.memory[address:address + length])

    def write(self, address, value):
        if self.name == 'altirra':
            self.emulator.poke(address, value)
        else:
            self.emulator.memory[address] = value

    def display_memory(self, address, length):
        """ANTIC's bank, even when the CPU currently sees game RAM or the OS."""
        if self.name == 'altirra':
            port = self.read(0xd301)[0]
            try:
                self.write(0xd301, port & ~0x10)
                return self.read(address, length)
            finally:
                self.write(0xd301, port)
        pointer = ctypes.c_void_p.in_dll(self.emulator._lib, 'ANTIC_xe_ptr').value
        return ctypes.string_at(pointer + address - 0x4000, length) if pointer else self.read(address, length)

    def frame(self):
        self.emulator.frame(1)
        self.frames += 1

    def until(self, condition, limit=6000):
        for _ in range(limit):
            if condition():
                return
            self.frame()
        raise AssertionError('Timeout waiting for the game')

    def state(self):
        if self.name == 'altirra':
            antic = self.emulator.antic()
            pc = self.emulator.registers()['PC']
            display, dma = antic['list'], antic['DMACTL']
            portb = self.read(0xd301)[0]
        else:
            pc = self.emulator.cpu()['PC']
            display = lockstep.display_list(self.emulator)
            dma = ctypes.c_ubyte.in_dll(self.emulator._lib, 'ANTIC_DMACTL').value
            portb = ctypes.c_ubyte.in_dll(self.emulator._lib, 'PIA_PORTB').value
        return {'pc': pc, 'list': display, 'dma': dma, 'mode': self.read(0x0389)[0],
                'conversion_bank': not bool(portb & 0x10),
                'shown': self.read(self.label['shown_mode'])[0],
                'bitmap_requested': bool(self.read(self.label['fake_vic'] + 0x11)[0] & 0x20),
                'waiting': self.read(self.label['waiting'])[0]}

    def press(self, key, name, out, capture=False):
        self.until(lambda: self.read(self.label['waiting'])[0])
        self.emulator.screenshot(out / f'{name}-start.png')
        start_text = self.display_memory(0x4000, 1000) if self.read(self.label['shown_mode'])[0] == 0 else None
        self.write(self.label['script_key'], key)
        states, consumed = [], False
        for frame in range(1, 2000):
            self.frame()
            consumed |= not self.read(self.label['script_key'])[0]
            state = dict(frame=frame, **self.state())
            state['text_during_bitmap_request'] = (state['bitmap_requested'] and state['list'] == self.label['text_list']
                                                  and bool(state['dma'] & 0x20))
            if start_text is not None and state['list'] == self.label['text_list'] and state['dma'] & 0x20:
                # A late flag cannot detect the earliest garble: verify actual
                # displayed bytes throughout the entire text-to-bitmap action.
                snapshot = self.display_memory(0x4000, 1000)
                state['text_changed'] = snapshot != start_text
                state['text_sha256'] = hashlib.sha256(snapshot).hexdigest()
            states.append(state)
            if capture:
                self.emulator.screenshot(out / f'{name}-{frame:03d}.png')
            if consumed and state['waiting']:
                break
        else:
            raise AssertionError(f'{name}: did not return to a key wait')
        # Publication is at VBI; a key wait may return within the preceding frame.
        for _ in range(2):
            self.frame()
        self.emulator.screenshot(out / f'{name}-end.png')
        result = {'action': name, 'frames': frame, 'milliseconds': round(frame * 1000 / 59.923, 1),
                  'text_changed_frames': sum(s.get('text_changed', False) for s in states), 'states': states}
        print(f"{name}: {frame} frames; {result['text_changed_frames']} changed text snapshot frames")
        return result

    def idle_check(self, force_copy=False):
        """Real polling, after leaving the held first-poll test hook.

        Assert key_given for a positive control: conversion must then run.
        Aging stamp can miss if the frame stops after SBC already read it.
        Ordinary idle polls continuously update stamp,
        so the original build does NOT repeatedly convert an idle screen.
        """
        if self.read(self.label['test_mode'])[0]:
            self.write(self.label['test_mode'], 0)
            self.write(self.label['idle'], 0)
            self.write(self.label['script_key'], 0x23)
            self.until(lambda: self.read(self.label['idle'])[0])
        states = []
        for _ in range(60):
            if force_copy:
                self.write(self.label['key_given'], 1)
            self.frame()
            states.append(self.state())
        # A frame can end inside a main-memory IRQ while refresh still owns
        # the extended bank. PC ranges alone miss those conversion frames.
        count = sum(s['conversion_bank'] for s in states)
        return {'sample_frames': len(states), 'frames_in_conversion': count, 'states': states}


def check(name, out, rebuild=True, capture_transients=True):
    out.mkdir(parents=True, exist_ok=True)
    layout = build.build(test=True) if rebuild else json.loads((build.OUT / 'layout.json').read_text())
    runner = Runner(layout, name, out)
    try:
        # The disk prompt has its own key poll, outside the held test key wait.
        runner.until(lambda: b'INSERT DISK B' in runner.read(0x0400, 1000))
        runner.write(runner.label['side'], 1)
        runner.write(0x0277, 0x0d)
        runner.write(0x00c6, 1)
        runner.until(lambda: runner.read(runner.label['waiting'])[0])
        report = {'emulator': name, 'timing': 'NTSC, first-poll script keys, patched disk', 'actions': []}
        runner.press(0x31, 'inn', out)
        for key in range(1, 7):
            runner.write(0x028e, 4)
            runner.press(key, f'party-{key}', out)
            runner.write(0x028e, 0)
        for key, action, capture in ACTION_KEYS:
            report['actions'].append(runner.press(key, action, out, capture and capture_transients))
        report['idle'] = runner.idle_check()
        report['idle_positive_control'] = runner.idle_check(force_copy=True)
        print('Idle conversion frames:', report['idle']['frames_in_conversion'],
              'positive control:', report['idle_positive_control']['frames_in_conversion'])
        assert report['idle']['frames_in_conversion'] == 0, 'Idle input stalls in refresh'
        assert report['idle_positive_control']['frames_in_conversion'] > 30, 'Positive control did not recopy'
        for action in report['actions']:
            assert action['text_changed_frames'] == 0, f"{action['action']}: text was reused before publication"
        (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
        return report
    finally:
        if name == 'altirra':
            runner.emulator.close()


def vice_check(out):
    """Original PAL C64, true drive: cycle stamps at successive first polls.

    Unlike Atari patched-disk timings, enter-town includes the original disk
    transfer. Walking/turns and character screens have no intervening loads.
    """
    from c64 import command
    from c64_trace import monitor_script
    out = out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    lines = (ROOT / 'tools/traces/boot-to-town-services.txt').read_text().splitlines()
    lines = lines[:lines.index('mark party')]
    lines = [line for line in lines if not line.startswith('mark ')]
    for key, name, _ in ACTION_KEYS:
        lines += [f'press {key:02x}', 'ready']
    with tempfile.TemporaryDirectory(prefix='mm1-speed-vice-') as folder:
        folder = Path(folder)
        cmd, env = command(headless=True, state=folder)
        commands, _ = monitor_script(lines, out, folder / 'disks')
        # No call/character traces needed: until already logs its stop's cycle.
        first_until = next(i for i, c in enumerate(commands) if c.startswith('until '))
        commands = commands[:2] + ['delete'] + commands[first_until:]
        (out / 'monitor.txt').write_text('')
        playback = out / 'speed.mon'
        playback.write_text('\n'.join(commands) + '\n')
        with (out / 'vice.log').open('w') as log:
            subprocess.run(cmd + ['-warp', '-moncommands', str(playback)], env=env,
                           stdout=log, stderr=subprocess.STDOUT, check=True, timeout=180)
    raw = (out / 'monitor.txt').read_text()
    stamps = [int(c) for c in re.findall(r'^\.C:0e3b .*\s+(\d+)$', raw, re.MULTILINE | re.I)]
    stamps = stamps[-len(ACTION_KEYS)-1:]
    assert len(stamps) == len(ACTION_KEYS)+1, 'Missing first-poll cycle stamps'
    actions = []
    for (_, name, _), start, end in zip(ACTION_KEYS, stamps, stamps[1:]):
        cycles = end - start
        assert cycles > 0
        actions.append({'action': name, 'cycles': cycles,
                        'frames': round(cycles / 19656, 3),
                        'milliseconds': round(cycles * 1000 / 985248, 1)})
        print(f'{name}: {cycles} cycles, {actions[-1]["milliseconds"]} ms (PAL C64)')
    report = {'emulator': 'vice', 'timing': 'PAL, original true drive, first-poll keys', 'actions': actions}
    (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


def cache_probe(out):
    """Exercise both cache paths and invalidations against forced full selection.

    Synthetic display inputs in a held test machine; no game execution after
    the probe. A second call with shown_mode=0 always bypasses both caches.
    """
    from sound_check import call
    layout = build.build(test=True)
    game = lockstep.Game(layout)
    game.frames(300)
    game.memory[game.label['side']] = 1
    game.keys([0x0d])
    game.ready()
    mem, label = game.memory, game.label
    put = game.atari._lib.PIA_PutByte
    put.argtypes = [ctypes.c_uint16, ctypes.c_ubyte]
    put(0xd301, 0xc2)            # CPU sees display bank; ANTIC keeps the same bank
    cases = [
        ('uniform', [0x12]*30 + [0x34]*10, [6]*40),
        ('unchanged', [0x12]*30 + [0x34]*10, [6]*40),
        ('matrix-changed', [0x12]*29 + [0x52] + [0x34]*10, [6]*40),
        ('ram-high-bits', [0x12]*29 + [0x52] + [0x34]*10, [0xa6]*40),
        ('ram-changed', [0x12]*29 + [0x52] + [0x34]*10, [5]*40),
        ('panel-varied', [0x12]*30 + [0x34]*10, [6]*30 + [3]*10),
        ('varied-unchanged', [0x12]*30 + [0x34]*10, [6]*30 + [3]*10),
        ('same-histogram', [0x34]*10 + [0x12]*30, [6]*30 + [3]*10),
        ('different-histogram', [0x56]*40, [3, 4]*20),
        ('back-to-uniform', [0x12]*30 + [0x34]*10, [6]*40),
    ]
    checked, hits = [], 0
    def output(row):
        return ([mem[label[n]+row] for n in ('row_pf0', 'row_pf1', 'row_pf2', 'row_pf3')],
                bytes(mem[label['pair']:label['pair']+16]), bytes(mem[label['pair4']:label['pair4']+16]))
    for row in (0, 6, 13, 14, 24):
        mem[label['row']] = row
        mem[0xf4:0xf8] = bytes([0, 4, 0, 0xd8])
        for index, (name, matrix, cram) in enumerate(cases):
            mem[0x400:0x428], mem[0xd800:0xd828] = bytes(matrix), bytes(cram)
            mem[label['shown_mode']] = 0 if index == 0 else 2
            mem[label['chosen']:label['chosen']+3] = bytes([255]*3)
            call(game, label['choose_colours'])
            cached = output(row)
            if name == 'unchanged' and row >= 6:
                assert bytes(mem[label['chosen']:label['chosen']+3]) == bytes([255]*3), 'Uniform cache was not reached'
                hits += 1
            mem[label['shown_mode']] = 0
            call(game, label['choose_colours'])
            assert cached == output(row), f'Row {row}, {name}: cached palette differs from a full calculation'
            checked.append({'row': row, 'case': name})
        # Mimic the text snapshot overwriting the first cache's padding.
        if row == 6:
            mem[0x43c0:0x43fc] = bytes([32]*60)
            mem[label['shown_mode']] = 0
            call(game, label['choose_colours'])
            first = output(row)
            call(game, label['choose_colours'])
            assert first == output(row), 'Text-to-bitmap cache invalidation failed'
    out.mkdir(parents=True, exist_ok=True)
    (out / 'cache-probe.json').write_text(json.dumps({'cases': checked, 'proven_uniform_hits': hits}, indent=2)+'\n')
    print(f'OK: {len(checked)} cached/full palette comparisons; {hits} proven uniform cache hits')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--emulator', choices=['atari800', 'altirra', 'vice'], default='atari800')
    parser.add_argument('--out', type=Path, default=build.OUT / 'speed')
    parser.add_argument('--no-build', action='store_true')
    parser.add_argument('--cache-probe', action='store_true')
    parser.add_argument('--settled-only', action='store_true',
                        help='keep start/end PNGs; still check every transition frame state/text byte')
    args = parser.parse_args()
    if args.cache_probe:
        cache_probe(args.out)
    elif args.emulator == 'vice':
        vice_check(args.out)
    else:
        check(args.emulator, args.out, not args.no_build, not args.settled_only)


if __name__ == '__main__':
    main()
