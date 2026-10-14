#!/usr/bin/env python3
"""Build a focused oracle scenario from an existing script and raw steps.

python3 tools/scenario_explore.py SCRIPT MARK STEPS [--position X Y FACING] [--write FILE]

Unlike oracle_explore.py's compact key string, STEPS is a file in the shared
trace language, including poll/poke. --write saves the complete successful
script, including its prefix and explicit position fixture. Record it in VICE
and run lockstep before treating its outcome as verified.
"""
import argparse
from pathlib import Path

import oracle
from oracle_explore import base, show, where


def position_steps(x, y, facing):
    """Position plus all four facing/delta fields, then a native right turn.

    Changing only $40 leaves its rotating companion fields inconsistent.
    The native turn redraws the view and can invoke the destination's event.
    """
    if not 0 <= x < 16 or not 0 <= y < 16 or facing not in 'NESW' or len(facing) != 1:
        raise ValueError('Position must be X/Y in 0..15 and facing N/E/S/W')
    heading = 'NESW'.index(facing)
    order = [(heading - 1) % 4, (heading - 2) % 4, heading, (heading + 1) % 4]
    masks, deltas = (0xc0, 0x30, 0x0c, 0x03), (0x10, 1, 0xf0, 0xff)
    values = ' '.join(f'{table[index]:02x}' for table in (masks, deltas) for index in order)
    return [f'# Position fixture: {x},{y}, facing {facing}; then a native right turn.',
            f'poke 003b {x:02x} {y:02x}', f'poke 0040 {values}', 'press 4c', 'ready']


class Session:
    """Reusable exploration helper; failed steps never become a saved script."""

    def __init__(self, script, mark):
        self.lines = base(Path(script).read_text().splitlines(), mark)
        self.player = oracle.Oracle()
        self.player.play(self.lines, pictures=False)

    def play(self, lines):
        lines = list(lines)
        before = len(self.player.events)
        try:
            self.player.play(lines, pictures=False, limit=200_000_000)
        except oracle.OracleError:
            show(self.player.events[before:])
            raise
        self.lines.extend(lines)
        show(self.player.events[before:])
        print(where(self.player))

    def position(self, x, y, facing):
        self.play(position_steps(x, y, facing))

    def mark(self, name):
        self.play(['mark ' + name])

    def save(self, path):
        Path(path).write_text('\n'.join(self.lines) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('script', type=Path)
    parser.add_argument('mark')
    parser.add_argument('steps', type=Path)
    parser.add_argument('--position', nargs=3, metavar=('X', 'Y', 'FACING'))
    parser.add_argument('--write', type=Path)
    args = parser.parse_args()
    session = Session(args.script, args.mark)
    if args.position:
        x, y, facing = args.position
        session.position(int(x), int(y), facing)
    session.play(args.steps.read_text().splitlines())
    if args.write:
        session.save(args.write)


if __name__ == '__main__':
    main()
