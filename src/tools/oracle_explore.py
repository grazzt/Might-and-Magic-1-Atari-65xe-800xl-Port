#!/usr/bin/env python3
"""Try keys on the host oracle and print what the game read, printed and took.

The oracle's counterpart of tools/c64_explore.py, and much quicker: there is
no emulator and no snapshot, the run starts from boot every time. Play a
script up to one of its marks, then the keys given, and see what happened.

  python3 tools/oracle_explore.py tools/traces/boot-to-fight-and-save.txt town 'IIL|'

KEYS as in c64_explore.py: a character is pressed as it stands (upper case);
  |            wait for the next key prompt, mark it, and show where the party is
  <0d>         press PETSCII $0D; <5f> is the game's Escape
  <attach C>   put side C in the drive
  <until ADDR> run to an execution address
  <wait N>     run N instructions

With --write FILE the steps played after the mark are written out as script
lines, to be pasted into a script under tools/traces/. With --pictures DIR a
picture of every `|` is written there; with --screen the text screen is
printed at every `|` where the game is showing one.
"""
import argparse
from pathlib import Path
import re

from c64 import ROOT
from c64_explore import script
from c64_screen import write_png
import oracle

FACING = {0xc0: 'N', 0x30: 'E', 0x0c: 'S', 0x03: 'W'}
# Lines that are redrawn all the time: lone symbols, and the party panel on rows 16-19.
NOISE = re.compile(r'^\s*\d+,\s*\d+: (@.*|[1-6]\)|[\[`].*|\+|\.|\)|\s*|<..>|\$+_?\$*)$'
                   r'|^\s*1[6-9],\s*(4|24): ')


def base(lines, mark):
    """The script up to and including `mark NAME`."""
    out = []
    for line in lines:
        out.append(line)
        if line.split('#')[0].split() == ['mark', mark]:
            return out
    raise SystemExit(f'No mark {mark} in the script')


def where(player):
    mem = player.mem
    return (f"at {mem[0x3b]},{mem[0x3c]} facing {FACING.get(mem[0x40], f'${mem[0x40]:02x}')}, "
            f"display mode {mem[0x0389]}, side {player.side}")


def screen(player):
    """The text screen at $0400 as lines, when the game is showing text."""
    mem = player.mem
    rows = [''.join(chr(c & 0x7f) if 32 <= c & 0x7f < 96 else ' ' for c in mem[0x0400 + r * 40:0x0428 + r * 40])
            for r in range(25)]
    return [f'    {r:2d} {line.rstrip()}' for r, line in enumerate(rows) if line.strip()]


def show(events, all_text=False):
    for event in events:
        if 'command' in event:
            print('DISK', event['side'], event['name'], event['address'], event['length'],
                  f"{event['block']}+{event['offset']}", 'from', event['caller'])
        elif 'text' in event:
            shown = [line.strip() for line in event['text'] if all_text or not NOISE.match(line)]
            if shown:
                print('  TEXT', ' | '.join(shown))
        elif 'keys' in event:
            print('  KEYS', event['keys'])
        elif 'mark' in event:
            print('--', event['mark'], event.get('where', ''))
            for line in event.get('screen', []):
                print(line)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('script', type=Path)
    parser.add_argument('mark', help='play the script up to this mark first')
    parser.add_argument('keys')
    parser.add_argument('--all-text', action='store_true', help='also show single characters and the party panel')
    parser.add_argument('--write', type=Path, help='write the steps played after the mark to this file')
    parser.add_argument('--pictures', type=Path, help='folder for a picture of every |')
    parser.add_argument('--screen', action='store_true', help='print the text screen at every |')
    args = parser.parse_args()
    steps = script('', '', args.keys)[2:]          # without the resume and its wait
    player = oracle.Oracle()
    player.play(base(args.script.read_text().splitlines(), args.mark), pictures=False)
    before = len(player.events)

    def on_mark(name):
        player.events[-1]['where'] = where(player)
        if args.screen and not player.mem[0x0389]:
            player.events[-1]['screen'] = screen(player)
        if args.pictures:
            args.pictures.mkdir(parents=True, exist_ok=True)
            write_png(args.pictures / f'{name}.png', player.picture())
    try:
        player.play(steps, pictures=False, limit=200_000_000, on_mark=on_mark)
    except oracle.OracleError as error:
        player.flush_text()
        show(player.events[before:], args.all_text)
        raise SystemExit(f'STOPPED: {error}; {where(player)}')
    show(player.events[before:], args.all_text)
    print('End:', where(player))
    if args.write:
        args.write.write_text('\n'.join(steps) + '\n')


if __name__ == '__main__':
    main()
