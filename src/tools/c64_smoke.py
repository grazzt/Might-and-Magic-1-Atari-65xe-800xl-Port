#!/usr/bin/env python3
"""Boot original v2 through the A->B swap and assert the options menu in RAM.

Inputs are injected into the C64 KERNAL keyboard buffer; this checks loading and
game execution, not physical keyboard emulation or deterministic game timing.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

from c64 import ROOT, command


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'test-artifacts/c64/baseline')
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    # A failed run must not leave an earlier passing result or stale captures.
    for name in ['result.json', 'menu.txt', 'title.png', 'insert-b.png', 'menu.png',
                 'title-ram.bin', 'menu-ram.bin']:
        (out / name).unlink(missing_ok=True)
    # Every run uses fresh copies, never a previous session's save disks.
    with tempfile.TemporaryDirectory(prefix='mm-c64-smoke-') as tmp:
        cmd, env = command(headless=True, state=Path(tmp))
        side_b = Path(tmp) / 'disks/Might_and_Magic_1_(Original_v2)_Side_B.g64'
        monitor_log = out / 'monitor.txt'
        monitor_log.write_text('')  # VICE's monitor logger appends.
        commands = [f'logname "{monitor_log}"', 'log on', 'step $2000000',
                    'until $41ab', 'registers', 'io $d000', 'io $dd00',
                    f'screenshot "{out}/title.png" 2', 'bank ram',
                    f'bsave "{out}/title-ram.bin" 0 $0000 $ffff', 'bank cpu',
                    '> $0277 $5f', '> $00c6 $01', 'step $1000000',
                    f'screenshot "{out}/insert-b.png" 2',
                    f'attach "{side_b}" 8', 'step $100000',
                    '> $0277 $0d', '> $00c6 $01', 'step $4000000',
                    'registers', 'io $d000', 'io $dd00',
                    f'screenshot "{out}/menu.png" 2', 'bank ram',
                    f'bsave "{out}/menu-ram.bin" 0 $0000 $ffff', 'bank cpu', 'quit']
        monitor = Path(tmp) / 'capture.mon'
        monitor.write_text('\n'.join(commands) + '\n')
        with (out / 'vice.log').open('w') as log:
            result = subprocess.run(cmd + ['-warp', '-moncommands', str(monitor)],
                                    env=env, stdout=log, stderr=subprocess.STDOUT, timeout=90)
        if result.returncode:
            raise SystemExit(f'VICE failed ({result.returncode}); see {out}/vice.log')
    ram = (out / 'menu-ram.bin').read_bytes()
    if len(ram) != 65536:
        raise SystemExit('Incomplete RAM capture')
    screen = ram[0x0400:0x0400 + 1000]
    lines = [''.join(chr((c & 127) + 64) if (c & 127) < 32 else chr(c & 127)
                     for c in screen[i:i + 40]).rstrip() for i in range(0, 1000, 40)]
    text = '\n'.join(lines) + '\n'
    for expected in ['MIGHT AND MAGIC', 'CREATE NEW CHARACTERS', 'VIEW ALL CHARACTERS', 'GO TO TOWN']:
        if expected not in text:
            raise SystemExit(f'Menu assertion failed: {expected}; inspect {out}/menu.png')
    (out / 'menu.txt').write_text(text)
    report = {'result': 'pass', 'source': 'Original_v2 G64, sides A and B',
              'machine': 'VICE x64sc; PAL; true 1541; virtual device traps disabled',
              'input': 'KERNAL buffer injection: $5f (left arrow), $0d (Return)',
              'asserted': ['options menu text in screen RAM'],
              'not_tested': ['physical keyboard', 'side C/D swaps', 'party creation', 'save/reload',
                             'deterministic RNG', 'Atari execution'],
              'files': {name: hashlib.sha256((out / name).read_bytes()).hexdigest()
                        for name in ['title.png', 'insert-b.png', 'menu.png', 'title-ram.bin', 'menu-ram.bin']}}
    (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(f'PASS: original v2 boots, accepts side B, and reaches the options menu. Artifacts: {out}')


if __name__ == '__main__':
    main()
