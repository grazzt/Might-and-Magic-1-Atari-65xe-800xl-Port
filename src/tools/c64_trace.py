#!/usr/bin/env python3
"""Run a scripted VICE session; record disk-loader commands and printed text.

Nothing in the game is patched: VICE trace points log the registers when
execution passes a few addresses in the game's resident code.

Loader: every drive command goes through $9E74 with the command number in A
and its parameters in $9D00-$9D06 (source/c64/fastload-c64.info). Each logged
read is compared, where RAM still holds it at the next mark, with the same
request served from our logical-disk decoding of the attached side. Each
write is compared with the same blocks decoded from the disk copy VICE leaves
behind, using our own G64 decoder.

Keys: a trace point where the key wait accepts a key ($0E44) records what the
game actually took, so a trace holds its input as well as its output.

Text: the play screen is all bitmap and keeps no text matrix, so the printed
characters are taken from the printers themselves. $0D42 draws a string at row
$0B, column $0C; $0D1C draws one character there; $0E91 is the text-mode
string printer the menus use (cursor in $25, $24).

Keys: the game's key wait ($0E37) clears the KERNAL buffer, then polls it in
a loop at $0E3B that counts in $2D/$2E, and those counters feed the random
generator. `press` runs to the first pass of that loop and puts the key in the
buffer there, so every key is taken on the first poll and a script plays the
same way however long the disk took. `key` after a fixed `wait` does not have
that property; it is for places the game reads keys differently (the title).

Script lines (# starts a comment):
  press XX      run until the game waits for a key, then give it PETSCII XX
  ready         run until the game waits for a key (use before mark)
  wait N        run N instructions (hex with $ or decimal)
  until ADDR    run to an execution address
  key XX ...    put PETSCII bytes into the KERNAL keyboard buffer now
  poll ADDR XX  give a key at a specific JSR GETIN, outside the usual key wait;
                immediately after the press that triggers that event
  poke ADDR XX  write memory bytes (e.g. the KERNAL CTRL flag at $028E)
  attach SIDE   put side A-D in drive 8
  mark NAME     save screenshot NAME.png (with --keep-ram also NAME-ram.bin, all
                64 KB of RAM, and NAME-io.bin, the I/O area $D000-$DFFF)
  snapshot NAME save a VICE snapshot NAME.vsf in the output folder
  resume FILE SIDE  first line only: start from a snapshot with SIDE in the drive
  pauses XX     from here on, give PETSCII XX on the first poll of every pause
                ($C355: a wait on the clock that a key ends); `pauses off` stops
                it. Only straight after `ready`, when the machine is still
  restart       switch the machine off and on: a new VICE with side A in the
                drive and the disks as the game has left them

A resumed run skips the boot. Snapshots do not contain the disks, so a resumed
run sees fresh copies: anything the earlier run wrote to disk is gone.
tools/c64_explore.py wraps this for quick experiments from a snapshot.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from c64 import ROOT, command
from d64 import D64
from g64 import G64, sector_image
import mmdisk

COMMANDS = {0: 'read', 1: 'write', 2: 'set disk id', 3: 'get disk id',
            4: 'protected read', 5: 'reset drive'}

KEY_WAIT_LOOP = '$0e3b'
PAUSE_POLL = 0xc378         # the pause routine's call for a key, once per pass of its loop
PAUSE_POINTS = (10, 11)     # the two trace points there: they put a key in the KERNAL's buffer

# Trace points, in the order the monitor numbers them (1 and 2 share $9E74).
TRACE_POINTS = [
    ('$9e74', 'm 9d00 9d06'),   # 1: loader command, parameters
    ('$9e74', 'm 0100 01ff'),   # 2: stack, for the caller
    ('$0cf8', None),            # 3: string drawn first on the upper bitmap: skip that copy
    ('$0cfe', 'm 000b 000c'),   # 4: string drawn on the lower screen; row, column
    ('$0d4f', None),            # 5: next character of that string in A
    ('$0d1c', 'm 000b 000c'),   # 6: single character in A; row, column
    ('$0e9d', 'm 0024 0025'),   # 7: text-mode string; column, row
    ('$0ea4', None),            # 8: next character of that string in A
    ('$0e44', None),            # 9: the key wait accepted the key in A
]


def settled(lines, instructions=0x8000, counters=None):
    """A script with time added before every mark so that the screenshot shows
    what the game has just drawn.

    VICE's screenshot is its last finished frame, which at a mark taken the
    moment the game asks for a key does not yet hold the newest text. Waiting
    a few frames fixes that, but it also runs the key wait's counters, so
    they are reset afterwards (docs/ORACLE.md, timing rule 2). With counters,
    restore the plain run's exact values instead of zero. Only marks
    taken in the key wait are treated; the others are left as they are.
    The run is then no longer the session the plain script records: use it for
    pictures only, with the same lines on VICE and on the oracle.
    """
    out, waiting = [], False
    for raw in lines:
        words = raw.split('#')[0].split()
        op = words[0] if words else ''
        if op == 'mark' and waiting:    # other marks are mid-flow; leave them alone
            values = counters[words[1]] if counters is not None else (0, 0)
            out += [f'wait ${instructions:x}', 'ready', f'poke 002d {values[0]:02x} {values[1]:02x}']
        if op in ('press', 'ready'):
            waiting = op == 'ready'
        elif op in ('wait', 'until', 'key', 'resume'):
            waiting = False
        out.append(raw)
    return out


def quick(lines, key=0x20):
    """A script in which a key ends every pause, from the first key wait on.

    The game then prints, reads and writes exactly what it does when the
    pauses run out, in a quarter of the time (docs/ORACLE.md, timing rule 3).
    """
    out, done = [], False
    for raw in lines:
        out.append(raw)
        words = raw.split('#')[0].split()
        if words and words[0] == 'restart':
            done = False
        elif words and words[0] == 'ready' and not done:
            out.append(f'pauses {key:02x}')
            done = True
    return out


def segments(lines):
    """The script cut at its `restart` lines: one list of lines per machine."""
    out = [[]]
    for raw in lines:
        if raw.split('#')[0].split() == ['restart']:
            out.append([])
        else:
            out[-1].append(raw)
    return out


def monitor_script(lines, out, disks, log='monitor.txt'):
    cmds = [f'logname "{out}/{log}"', 'log on']
    for number, (address, extra) in enumerate(TRACE_POINTS, 1):
        cmds.append(f'trace exec {address}')
        if extra:
            cmds.append(f'command {number} "{extra}"')
    # Two more at the pause's poll, switched on by `pauses`: a key and a count of one.
    cmds += [f'trace exec ${PAUSE_POLL:04x}', f'command {PAUSE_POINTS[0]} "> $0277 $20"',
             f'trace exec ${PAUSE_POLL:04x}', f'command {PAUSE_POINTS[1]} "> $00c6 $01"']
    cmds += [f'disable {number}' for number in PAUSE_POINTS]
    marks = []
    waiting = False  # stopped on the first pass of the key-wait loop
    for raw in lines:
        words = raw.split('#')[0].split()
        if not words:
            continue
        op, args = words[0], words[1:]
        if op in ('press', 'ready'):
            if not waiting:
                cmds.append(f'until {KEY_WAIT_LOOP}')
            waiting = op == 'ready'
            if op == 'press':
                cmds += [f'> $0277 ${args[0]}', '> $00c6 $01']
        elif op == 'wait':
            cmds.append(f'step {args[0]}')
            waiting = False
        elif op == 'until':
            cmds.append(f'until {args[0]}')
            waiting = False
        elif op == 'key':
            cmds += [f'> $0277 {" ".join("$" + a for a in args)}', f'> $00c6 ${len(args):02x}']
            waiting = False
        elif op == 'poll':
            if not int(args[1], 16):
                raise SystemExit('poll requires a nonzero key')
            cmds += [f'until ${args[0].lstrip("$")}', f'> $0277 ${args[1]}', '> $00c6 $01']
            waiting = False
        elif op == 'poke':
            cmds.append(f'> ${args[0]} {" ".join("$" + a for a in args[1:])}')
        elif op == 'pauses':
            if args[0] == 'off':
                cmds += [f'disable {number}' for number in PAUSE_POINTS]
            else:
                cmds.append(f'command {PAUSE_POINTS[0]} "> $0277 ${args[0]}"')
                cmds += [f'enable {number}' for number in PAUSE_POINTS]
        elif op == 'snapshot':
            cmds.append(f'dump "{out}/{args[0]}.vsf"')
        elif op == 'resume':
            image = disks / f'Might_and_Magic_1_(Original_v2)_Side_{args[1]}.g64'
            cmds += [f'undump "{Path(args[0]).resolve()}"', f'attach "{image}" 8', 'registers']
            marks.append(('attach', args[1]))
            waiting = False
        elif op == 'attach':
            image = disks / f'Might_and_Magic_1_(Original_v2)_Side_{args[0]}.g64'
            cmds += [f'attach "{image}" 8', 'registers']
            marks.append(('attach', args[0]))
        elif op == 'mark':
            name = args[0]
            cmds += ['registers', f'screenshot "{out}/{name}.png" 2', 'bank ram',
                     f'bsave "{out}/{name}-ram.bin" 0 $0000 $ffff', 'bank io',
                     f'bsave "{out}/{name}-io.bin" 0 $d000 $dfff', 'bank cpu']
            marks.append(('mark', name))
        else:
            raise SystemExit(f'Unknown script line: {raw}')
    return cmds + ['quit'], marks


def parse(log, marks):
    """Yield (kind, value) for script steps, loader calls and printed text.

    The monitor logs neither attach nor screenshot commands, so each of those
    script steps also prints the registers; the nth register dump is the nth step.
    """
    marks = iter(marks)
    pattern = re.compile(
        r'#1 \(Trace  exec 9e74\).*\n\.C:9e74 .* A:(..) X:(..) Y:(..) SP:(..) \S+\s+(\d+)\n'
        r'Executing: m 9d00 9d06\n>C:9d00  (.. .. .. ..)  (.. .. ..).*\n'
        r'#2 \(Trace  exec 9e74\).*\n.*\nExecuting: m 0100 01ff\n((?:>C:01.*\n){16})'
        r'|\n\.;(....) .. .. .. .. (..) (..) '
        r'|#([3-9]) \(Trace  exec ....\).*\n\.C:.... .* A:(..) .*\n'
        r'(?:Executing: m 00.. 00..\n>C:00..  (..) (..))?')
    for m in pattern.finditer(log):
        if m.group(12):
            point, a = int(m.group(12)), int(m.group(13), 16)
            pair = [int(g, 16) for g in m.group(14, 15)] if m.group(14) else None
            if point == 3:
                yield 'skip', None
            elif point == 4:
                yield 'string', pair
            elif point == 7:
                yield 'string', pair[::-1]
            elif point == 6:
                yield 'single', (pair, a)
            elif point == 9:
                yield 'key', a
            else:
                yield 'char', a
        elif m.group(9):
            kind, name = next(marks)
            yield kind, {'name': name, 'pc': f'${m.group(9)}', 'port_01': f'${m.group(11)}'}
        else:
            a, x, y, sp, cycle = (int(g, 16 if i < 4 else 10) for i, g in enumerate(m.groups()[:5]))
            p = bytes.fromhex(m.group(6) + m.group(7))
            stack = bytes.fromhex(''.join(line[9:59] for line in m.group(8).splitlines()))
            # Return address of the game's JSR to the $9Dxx jump table.
            caller = (stack[sp + 3] | stack[sp + 4] << 8) - 2
            yield 'call', {'cycle': cycle, 'command': a, 'name': COMMANDS.get(a, '?'),
                           'caller': f'${caller:04x}', 'address': p[0] | p[1] << 8,
                           'length': p[2] | p[3] << 8, 'offset': p[4], 'block': p[5] | p[6] << 8,
                           'x': x, 'y': y}


class Text:
    """Collect printed characters into 'row,column: text' lines."""

    def __init__(self):
        self.lines, self.where, self.chars, self.skipping = [], None, [], False

    def end_line(self):
        if self.chars:
            text = ''.join(chr(c) if 32 <= c < 127 else '/' if c == 13 else f'<{c:02x}>'
                           for c in self.chars)
            self.lines.append(f'{self.where[0]:2d},{self.where[1]:2d}: {text}')
        self.chars = []

    def feed(self, kind, value):
        if kind == 'skip':
            self.end_line()
            self.skipping = True
        elif kind == 'string':
            self.end_line()
            self.where, self.skipping = value, False
        elif kind == 'char' and not self.skipping:
            if value:
                self.chars.append(value)
            else:
                self.end_line()
        elif kind == 'single':
            (row, column), char = value
            # Consecutive single characters on one row read as one line.
            if not (self.chars and self.where and self.where[0] == row
                    and self.where[1] + len(self.chars) == column):
                self.end_line()
                self.where = [row, column]
            self.chars.append(char)

    def take(self):
        self.end_line()
        lines, self.lines = self.lines, []
        return lines


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('script', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--timeout', type=int, default=900)
    parser.add_argument('--keep-ram', action='store_true',
                        help='keep the 64 KB RAM capture of every mark')
    parser.add_argument('--settle', action='store_true',
                        help='wait before every mark so screenshots are current (pictures only; see settled())')
    parser.add_argument('--settle-preserve', action='store_true',
                        help="settle screenshots and restore each mark's original key-wait counters")
    parser.add_argument('--quick', action='store_true', help='a key ends every pause (see quick())')
    parser.add_argument('--keep-log', action='store_true',
                        help='keep monitor.txt, the raw VICE monitor log (megabytes)')
    args = parser.parse_args()
    out = (args.output or ROOT / 'build/trace' / args.script.stem).resolve()
    out.mkdir(parents=True, exist_ok=True)
    for old in out.iterdir():
        if old.is_file():
            old.unlink()
    tmp = Path(tempfile.mkdtemp(prefix='mm-c64-trace-'))
    try:
        lines = args.script.read_text().splitlines()
        if args.settle_preserve:
            from oracle import Oracle
            player, counters = Oracle(), {}
            player.play(lines, pictures=False,
                        on_mark=lambda name: counters.__setitem__(name, bytes(player.mem[0x2d:0x2f])))
            lines = settled(lines, counters=counters)
        else:
            lines = settled(lines) if args.settle else quick(lines) if args.quick else lines
        runs = []       # one VICE per machine: (log file, marks, the disks as that machine left them)
        for number, part in enumerate(segments(lines)):
            # The disks are copied in only when they are not there: a later
            # machine starts with what the earlier ones wrote.
            cmd, env = command(headless=True, state=tmp)
            log_name = f'monitor-{number}.txt'
            cmds, marks = monitor_script(part, out, tmp / 'disks', log_name)
            (out / log_name).write_text('')
            playback = tmp / 'trace.mon'
            playback.write_text('\n'.join(cmds) + '\n')
            with (out / 'vice.log').open('a') as log:
                result = subprocess.run(cmd + ['-warp', '-moncommands', str(playback)], env=env,
                                        stdout=log, stderr=subprocess.STDOUT, timeout=args.timeout)
            if result.returncode:
                raise SystemExit(f'VICE failed ({result.returncode}); see {out}/vice.log')
            left = tmp / f'disks-after-{number}'
            shutil.copytree(tmp / 'disks', left)
            runs.append((out / log_name, marks, left))
        analyse(args, out, runs)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def steps(runs):
    """parse() over every machine's log, with ('restart', n) between machines."""
    for number, (log, marks, _) in enumerate(runs):
        if number:
            yield 'restart', number
        yield from parse(log.read_text(errors='replace'), marks)


def analyse(args, out, runs):
    logical = {}
    def side_image(side, machine=0):
        """A side as a machine finds it: the original for the first, and for a
        later one what the machine before it left on the disk."""
        if (side, machine) not in logical:
            if machine:
                image = runs[machine - 1][2] / f'Might_and_Magic_1_(Original_v2)_Side_{side}.g64'
                sectors = sector_image(G64(image.read_bytes()))
            else:
                path = ROOT / f'build/c64/original-v2-{side.lower()}/sectors.d64'
                if not path.exists():
                    raise SystemExit('Run python3 tools/analyze_c64.py first')
                sectors = path.read_bytes()
            logical[side, machine] = mmdisk.decode(D64(sectors))
        return logical[side, machine]

    side, events, pending, writes, text, machine = 'A', [], [], [], Text(), 0
    def flush_text():
        lines = text.take()
        if lines:
            events.append({'text': lines})
    for kind, value in steps(runs):
        if kind in ('skip', 'string', 'char', 'single'):
            text.feed(kind, value)
            continue
        flush_text()
        if kind == 'restart':
            for call in pending:        # reads no mark followed: nothing to check them against
                call.pop('_data')
            side, pending, machine = 'A', [], value
            events.append({'restart': True})
            continue
        if kind == 'key':
            # Consecutive keys with nothing printed between them share an event.
            name = chr(value) if 32 < value < 127 and value != 0x5f else f'<{value:02x}>'
            if events and 'keys' in events[-1]:
                events[-1]['keys'] += name
            else:
                events.append({'keys': name})
            continue
        if kind == 'attach':
            side = value['name']
            events.append({'attach': side})
        elif kind == 'mark':
            name = value['name']
            ram = (out / f'{name}-ram.bin').read_bytes()
            # Check reads since the last mark against RAM, newest first, so a
            # region loaded twice is attributed to its latest load only.
            claimed = bytearray(65536)
            for call in reversed(pending):
                span = range(call['address'], min(call['address'] + call['length'], 65536))
                data = bytes.fromhex(call.pop('_data'))
                free = [i for i in span if not claimed[i]]
                call['ram_check'] = {'mark': name, 'bytes_compared': len(free),
                                     'bytes_equal': sum(ram[i] == data[i - call['address']] for i in free)}
                for i in span:
                    claimed[i] = 1
            pending = []
            for call in writes:
                if '_ram' not in call:  # what the game handed to the write call
                    call['_ram'] = ram[call['address']:call['address'] + call['length']]
            events.append({'mark': name, 'pc': value['pc'], 'port_01': value['port_01']})
        else:
            value['side'] = side
            if value['command'] in (0, 4):
                block = value['block'] ^ (mmdisk.PROTECTED_XOR if value['command'] == 4 else 0)
                data = mmdisk.read(side_image(side, machine), block, value['offset'], value['length'])
                value['sha256'] = hashlib.sha256(data).hexdigest()
                value['_data'] = data.hex()
                pending.append(value)
            elif value['command'] == 1:
                value['_machine'] = machine
                writes.append(value)
            events.append(value)
    flush_text()
    for call in pending:
        call.pop('_data')
    # Writes: decode the disk copy the emulator wrote to and look for the data.
    # Each write is looked for on the disks as its own machine left them.
    after = {}
    for call in writes:
        key = (call.pop('_machine'), call['side'])
        if '_ram' not in call:
            continue  # no mark followed the write
        if key not in after:
            image = runs[key[0]][2] / f"Might_and_Magic_1_(Original_v2)_Side_{call['side']}.g64"
            after[key] = mmdisk.decode(D64(sector_image(G64(image.read_bytes()))))
        ram = call.pop('_ram')
        on_disk = mmdisk.read(after[key], call['block'], call['offset'], call['length'])
        before = mmdisk.read(side_image(call['side']), call['block'], call['offset'], call['length'])
        call['sha256'] = hashlib.sha256(on_disk).hexdigest()
        call['disk_check'] = {'bytes': len(ram),
                              'bytes_equal_ram': sum(a == b for a, b in zip(on_disk, ram)),
                              'bytes_changed_on_disk': sum(a != b for a, b in zip(on_disk, before))}
        whole = after[key]
        original = side_image(call['side'])
        start = call['block'] * 256 + call['offset']
        outside = sum(whole[i] != original[i] for i in range(len(whole))
                      if not start <= i < start + call['length'])
        call['disk_check']['bytes_changed_elsewhere'] = outside
    for e in events:
        for field in ('address', 'length', 'offset', 'block'):
            if field in e:
                e[field] = f'${e[field]:0{2 if field == "offset" else 4}x}'
    (out / 'trace.json').write_text(json.dumps(events, indent=1) + '\n')
    if not args.keep_ram:
        for capture in list(out.glob('*-ram.bin')) + list(out.glob('*-io.bin')):
            capture.unlink()
    if not args.keep_log:
        for log, _, _ in runs:
            log.unlink()
    for e in events:
        if 'command' in e:
            check = e.get('ram_check')
            note = f"  RAM {check['bytes_equal']}/{check['bytes_compared']}" if check else ''
            if 'disk_check' in e:
                d = e['disk_check']
                note = (f"  disk {d['bytes_equal_ram']}/{d['bytes']} as in RAM, "
                        f"{d['bytes_changed_on_disk']} changed, {d['bytes_changed_elsewhere']} elsewhere")
            print(f"{e['side']} {e['name']:<14} {e['address']} len {e['length']} block {e['block']}"
                  f"+{e['offset']} from {e['caller']}{note}")
        elif 'text' in e:
            for line in e['text']:
                print('    ' + line)
        elif 'keys' in e:
            print(f"  keys {e['keys']}")
        else:
            print(e)


if __name__ == '__main__':
    main()
