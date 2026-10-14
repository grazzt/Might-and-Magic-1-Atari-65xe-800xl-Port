#!/usr/bin/env python3
"""Try keys from a VICE snapshot and print what the game read, printed and took.

This is the exploration loop: resume a snapshot, press some keys, look at the
disk commands and the text, adjust, repeat. A run takes seconds because it
skips the boot. It writes the script it ran and the usual trace folder to
build/explore/NAME/, so a sequence that worked can be copied into a script
under tools/traces/ and replayed from boot.

  python3 tools/c64_trace.py tools/traces/snapshot-town.txt
  python3 tools/c64_explore.py look build/trace/snapshot-town/town.vsf B 'IIL|'

KEYS: a character is pressed as it stands (use upper case). Otherwise:
  |            wait for the next key prompt and mark it (screenshot m01, m02...)
  <0d>         press PETSCII $0D; <5f> is the game's Escape
  <attach C>   put side C in the drive
  <snap NAME>  save a snapshot NAME.vsf at the next key prompt
  <until ADDR> run to an execution address
  <wait N>     run N instructions

A snapshot does not hold the disks: a resumed run starts from fresh copies, so
anything saved before the snapshot was taken is gone.
"""
import argparse
import json
import re
import subprocess
import sys

from c64 import ROOT


def script(snapshot, side, keys):
    """Trace-script lines (tools/c64_trace.py) for a KEYS string."""
    lines = [f'resume {snapshot} {side}', 'wait $100000']  # let the drive see the disk
    marks = 0
    for token in re.findall(r'<[^>]+>|.', keys):
        word, _, value = token.strip('<>').partition(' ')
        if token == '|':
            marks += 1
            lines += ['ready', f'mark m{marks:02d}']
        elif not token.startswith('<'):
            lines.append(f'press {ord(token):02x}')
        elif word == 'attach':
            lines += [f'attach {value}', 'wait $100000']
        elif word == 'snap':
            lines += ['ready', f'snapshot {value}']
        elif word in ('until', 'wait'):
            lines.append(f'{word} {value}')
        else:
            lines.append(f'press {word}')
    return lines


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('name', help='folder under build/explore/')
    parser.add_argument('snapshot', help='.vsf written by a trace script\'s snapshot step')
    parser.add_argument('side', choices=list('ABCD'), help='side in the drive at the snapshot')
    parser.add_argument('keys')
    parser.add_argument('--all-text', action='store_true',
                        help='also show single characters and the party panel')
    parser.add_argument('--timeout', type=int, default=240)
    args = parser.parse_args()
    out = ROOT / 'build/explore' / args.name
    out.parent.mkdir(parents=True, exist_ok=True)
    steps = out.parent / f'{args.name}.txt'
    steps.write_text('\n'.join(script(args.snapshot, args.side, args.keys)) + '\n')
    run = subprocess.run([sys.executable, ROOT / 'tools/c64_trace.py', steps, '--output', out,
                          '--keep-ram', '--timeout', str(args.timeout)],
                         capture_output=True, text=True)
    if run.returncode:
        raise SystemExit(f'FAILED\n{run.stdout[-500:]}\n{run.stderr[-800:]}')
    # Lines that are redrawn all the time: lone symbols, and the party panel on rows 16-19.
    noise = re.compile(r'^\s*\d+,\s*\d+: (@.*|[1-6]\)|[\[`].*|\+|\.|\)|\s*|<..>|\$+_?\$*)$'
                       r'|^\s*1[6-9],\s*(4|24): ')
    for event in json.loads((out / 'trace.json').read_text()):
        if 'command' in event:
            print('DISK', event['side'], event['name'], event['address'], event['length'],
                  f"{event['block']}+{event['offset']}", 'from', event['caller'],
                  event.get('ram_check') or event.get('disk_check') or '')
        elif 'text' in event:
            shown = [line.strip() for line in event['text']
                     if args.all_text or not noise.match(line)]
            if shown:
                print('  TEXT', ' | '.join(shown))
        elif 'keys' in event:
            print('  KEYS', event['keys'])
        elif 'mark' in event:
            print('--', event['mark'], 'at', event['pc'])
    print(f'Script: {steps}\nScreens and RAM: {out}')


if __name__ == '__main__':
    main()
