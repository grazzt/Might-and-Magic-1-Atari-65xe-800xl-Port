#!/usr/bin/env python3
"""Host oracle: run the original C64 game code on the host, deterministically.

A minimal C64 is built around tools/mos6502.py: 64 KB of RAM, the KERNAL ROM
(for its interrupt handler and GETIN, which the game uses), stub video, sound
and CIA chips that keep just enough state for the raster interrupt and the
60 Hz timer, and the memory banking of the CPU port. There is no drive: the
game's disk loader is replaced at its two entry points ($9D0D read, $9D10
write) by copies to and from the decoded disk sides (tools/mmdisk.py).

The run starts where the second boot file jumps to the game's first program
($4000), from a memory image captured once in VICE at that instant
(test-artifacts/c64/oracle-start). From there every instruction executed is
the game's own or the KERNAL's.

It plays the same key scripts as tools/c64_trace.py and records the same
things at the same places in the game's code: keys accepted, text printed and
disk commands. `--compare DIR` checks the record against a VICE trace.json.

Timing. Cycle counts are approximate (see mos6502.py) and a disk read takes no
time, so interrupts fall at different instructions than in VICE. The game's
logic must not depend on that, and the comparison is the test that it does not.
Three rules make key timing the same on both sides: `press` gives the key on
the first pass of the key-wait loop, after waiting at a disk prompt a script
resets the two wait counters, and `pauses` gives a key on the first poll of a
pause (docs/ORACLE.md).

Script steps are those of c64_trace.py, with these differences:
  wait N     runs until the game polls for a key that is not there, or N
             instructions, whichever is first (nothing needs real time here)
  restart    a new machine from the start state; the disks keep what was
             written to them
  snapshot, resume   not supported
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import time

from c64 import ROOT, shared_root
from c64_screen import Segment, render, write_png
from c64_trace import COMMANDS, PAUSE_POLL, Text, quick, settled
import mmdisk
from mos6502 import CPU

START = ROOT / 'test-artifacts/c64/oracle-start'
CYCLES_PER_LINE, LINES = 63, 312           # PAL
FRAME = CYCLES_PER_LINE * LINES
KEY_WAIT_LOOP = 0x0e3b
GETIN = 0xffe4
NEVER = 1 << 62
SPLIT_ROW = 127         # first picture row drawn from the lower bitmap (interrupt at raster line $B0)


class OracleError(RuntimeError):
    pass


class C64:
    """CPU, banking and the few hardware registers the game depends on."""

    def __init__(self, ram, io, state, kernal, chargen, coverage=False):
        self.mem = bytearray(ram)       # what the CPU reads
        self.under = bytearray(ram)     # RAM at $D000-$FFFF, whatever is banked in
        self.kernal, self.chargen = kernal, chargen
        self.cpu = cpu = CPU(self.mem, coverage)
        cpu.io_read, cpu.special, cpu.on_event = self.io_read, self.special, self.on_event
        cpu.a, cpu.x, cpu.y, cpu.s, cpu.pc = (state[k] for k in ('a', 'x', 'y', 's', 'pc'))
        cpu.p = state['p']
        self.mem[0], self.mem[1] = state['ddr'], state['port']
        self.kernal_in = None
        self.remap()
        # Start the frame so that the raster is where VICE had it.
        self.origin = -(state['raster_line'] * CYCLES_PER_LINE + state['raster_cycle'])
        self.vic = bytearray(io[0x000:0x040])
        self.color = bytearray(b & 15 for b in io[0x800:0xc00])
        self.cia1 = bytearray(io[0xc00:0xc10])
        self.cia2 = bytearray(io[0xd00:0xd10])
        self.raster_compare = 0         # not readable from a dump; the KERNAL leaves it unused
        self.vic_flags, self.vic_enable = 0, io[0x01a] & 15
        self.vic_next = NEVER
        # CIA 1 timer A: the KERNAL's 60 Hz interrupt, running at the start.
        self.cia_latch = 0x4025
        self.cia_running = bool(io[0xc0e] & 1)
        self.cia_flags, self.cia_mask = 0, 1
        self.cia_next = (io[0xc04] | io[0xc05] << 8) + 1
        self.sid_writes = 0
        self.sid = bytearray(io[0x400:0x420])
        self.sid_trace = None           # opt-in; kept separate from the gameplay event record
        self.schedule()

    # -- memory ---------------------------------------------------------------
    def remap(self):
        """Show KERNAL ROM or RAM at $E000-$FFFF as bit 1 of the CPU port says.
        BASIC ROM is never shown: the game switches it out in its first instructions."""
        wanted = bool(self.mem[1] & 2)
        if wanted != self.kernal_in:
            self.kernal_in = wanted
            self.mem[0xe000:] = self.kernal if wanted else self.under[0xe000:]

    def ram(self, address):
        """A byte of RAM, regardless of banking."""
        return self.mem[address] if address < 0xd000 else self.under[address]

    def ram_image(self):
        return bytes(self.mem[:0xd000]) + bytes(self.under[0xd000:])

    def store(self, address, value):
        """Write RAM as the CPU's STA does when no I/O is in the way."""
        if address < 0xd000:
            self.mem[address] = value
        else:
            self.under[address] = value
            if address >= 0xe000 and not self.kernal_in:
                self.mem[address] = value

    def io_visible(self):
        port = self.mem[1]
        return port & 3 and port & 4

    def io_read(self, address):
        """Any read of $D000-$DFFF."""
        port = self.mem[1]
        if not port & 3:
            return self.under[address]
        if not port & 4:
            return self.chargen[address - 0xd000]
        if address < 0xd400:
            reg = address & 0x3f
            if reg == 0x11:
                return (self.vic[0x11] & 0x7f) | (self.raster() >> 8) << 7
            if reg == 0x12:
                return self.raster() & 0xff
            if reg == 0x19:
                active = self.vic_flags & self.vic_enable
                return self.vic_flags | 0x70 | (0x80 if active else 0)
            if reg == 0x1a:
                return self.vic_enable | 0xf0
            return self.vic[reg]
        if address < 0xd800:
            return 0                                    # SID
        if address < 0xdc00:
            return self.color[address - 0xd800] | 0xf0
        if address < 0xdd00:
            reg = address & 15
            if reg == 1:
                return 0xff                             # keyboard matrix: nothing held
            if reg in (4, 5) and self.cia_running:
                left = max(self.cia_next - self.cpu.cycles, 0)
                return left >> 8 if reg == 5 else left & 0xff
            if reg == 13:                               # reading acknowledges
                flags = self.cia_flags
                self.cia_flags = 0
                return flags | (0x80 if flags & self.cia_mask else 0)
            return self.cia1[reg]
        if address < 0xde00:
            return self.cia2[address & 15]
        return 0xff

    def special(self, address, value):
        """Writes to the CPU port and to $D000 and above."""
        if address < 2:
            self.mem[address] = value
            self.remap()
        elif address >= 0xe000 or not self.io_visible():
            self.store(address, value)
        elif address < 0xd400:
            reg = address & 0x3f
            if reg == 0x19:
                self.vic_flags &= ~value & 15
            elif reg == 0x1a:
                self.vic_enable = value & 15
            else:
                self.vic[reg] = value
                if reg in (0x11, 0x12):
                    self.raster_compare = self.vic[0x12] | (self.vic[0x11] & 0x80) << 1
                    self.vic_next = self.next_raster(self.raster_compare)
            self.schedule()
        elif address < 0xd800:
            self.sid_writes += 1
            reg = address & 31
            self.sid[reg] = value
            if self.sid_trace is not None:
                cycle = self.cpu.write_cycle
                self.sid_trace.append({'cycle': cycle, 'frame': (cycle - self.origin) // FRAME,
                                       'register': reg, 'value': value})
        elif address < 0xdc00:
            self.color[address - 0xd800] = value & 15
        elif address < 0xdd00:
            reg = address & 15
            self.cia1[reg] = value
            if reg == 4:
                self.cia_latch = self.cia_latch & 0xff00 | value
            elif reg == 5:
                self.cia_latch = self.cia_latch & 0xff | value << 8
            elif reg == 13:
                self.cia_mask = self.cia_mask | value & 31 if value & 0x80 else self.cia_mask & ~value
            elif reg == 14:
                self.cia_running = bool(value & 1)
                if value & 0x10 or self.cia_running and self.cia_next < self.cpu.cycles:
                    self.cia_next = self.cpu.cycles + self.cia_latch + 1
            self.schedule()
        elif address < 0xde00:
            self.cia2[address & 15] = value

    # -- time and interrupts ------------------------------------------------------
    def raster(self):
        return (self.cpu.cycles - self.origin) // CYCLES_PER_LINE % LINES

    def next_raster(self, line):
        """The cycle at which the raster next reaches a line."""
        if line >= LINES:
            return NEVER
        now = self.cpu.cycles
        at = self.origin + (now - self.origin) // FRAME * FRAME + line * CYCLES_PER_LINE
        return at if at > now else at + FRAME

    def irq_line(self):
        return self.vic_flags & self.vic_enable & 1 or self.cia_flags & self.cia_mask & 1

    def schedule(self):
        """Have the CPU call on_event at the next thing that can happen."""
        if self.irq_line() and not self.cpu.fi:
            self.cpu.next_event = 0
        else:
            self.cpu.next_event = min(self.vic_next, self.cia_next if self.cia_running else NEVER)

    def on_event(self):
        cpu, now = self.cpu, self.cpu.cycles
        while self.cia_running and now >= self.cia_next:
            self.cia_flags |= 1
            self.cia_next += self.cia_latch + 1
        while now >= self.vic_next:
            self.vic_flags |= 1
            self.vic_next += FRAME
        if self.irq_line() and not cpu.fi:
            cpu.interrupt(0xfffe)
        cpu.next_event = min(self.vic_next, self.cia_next if self.cia_running else NEVER)


def load_start(coverage=False):
    """The captured machine state at $4000 and the ROMs it needs."""
    roms = shared_root() / 'tools/emulators/local/usr/share/vice/C64'
    state = json.loads((START / 'entry.json').read_text())
    files = {'ram': START / 'entry-ram.bin', 'io': START / 'entry-io.bin',
             'kernal': roms / state['kernal_rom'], 'chargen': roms / state['chargen_rom']}
    data = {}
    for name, path in files.items():
        if not path.is_file():
            raise SystemExit(f'Missing {path}; see docs/REFERENCES.md')
        data[name] = path.read_bytes()
        if hashlib.sha256(data[name]).hexdigest() != state['sha256'][name]:
            raise SystemExit(f'{path} is not the file the start state was captured with')
    return C64(data['ram'], data['io'], state, data['kernal'], data['chargen'], coverage)


class Oracle:
    """The game on the host C64: disk sides, the loader stand-in, observation."""

    def __init__(self, coverage=False):
        self.with_coverage = coverage
        self.coverage = {}              # (side, block, address) of a load -> executed addresses in it
        self.disks = {}
        self.events, self.text = [], Text()
        self.stop_at = None
        self.idle_stop = False
        self.waiting = False            # stopped on the first pass of the key-wait loop
        self.spent = [0, 0]             # instructions and cycles of the machines before a restart
        self.cpu = None
        self.power_on()

    def power_on(self):
        """A machine at the start state, side A in the drive. The disks keep
        what an earlier machine of this run wrote to them."""
        if self.cpu:
            self.spent = [self.spent[0] + self.cpu.instructions, self.spent[1] + self.cpu.cycles]
        self.machine = load_start(self.with_coverage)
        self.loaded = []                # [(start, end, key)] newest last
        self.cpu, self.mem = self.machine.cpu, self.machine.mem
        self.side = 'A'
        self.pause_key = 0              # given on the first poll of every pause; 0 for none
        self.handlers = {
            0x9d0d: self.disk_read, 0x9d10: self.disk_write,
            0x9d07: self.unexpected, 0x9d13: self.unexpected, 0x9d16: self.unexpected,
            0x9d19: self.unexpected, 0x9d1c: self.unexpected,
            # The same places tools/c64_trace.py sets its trace points.
            0x0cf8: lambda: self.text.feed('skip', None),
            0x0cfe: lambda: self.text.feed('string', [self.mem[0x0b], self.mem[0x0c]]),
            0x0d4f: lambda: self.text.feed('char', self.cpu.a),
            0x0d1c: lambda: self.text.feed('single', ([self.mem[0x0b], self.mem[0x0c]], self.cpu.a)),
            0x0e9d: lambda: self.text.feed('string', [self.mem[0x25], self.mem[0x24]]),
            0x0ea4: lambda: self.text.feed('char', self.cpu.a),
            0x0e44: self.key_accepted,
            PAUSE_POLL: self.pause_poll,
        }
        for address in self.handlers:
            self.cpu.hooks[address] = 1
        self.cpu.on_hook = self.on_hook

    # -- hooks ----------------------------------------------------------------------
    def on_hook(self, pc):
        handler = self.handlers.get(pc)
        if handler:
            handler()
        if pc == self.stop_at:
            return True
        return pc == GETIN and self.idle_stop and not self.mem[0xc6]

    def pause_poll(self):
        """The pause routine is about to ask for a key: this is where a key
        that ends pauses arrives, as `press` gives its key to the key wait."""
        if self.pause_key and not self.mem[0xc6]:
            self.type_keys([self.pause_key])

    def unexpected(self):
        raise OracleError(f'Loader entry ${self.cpu.pc:04x} called; only read and write are stood in for')

    def flush_text(self):
        lines = self.text.take()
        if lines:
            self.events.append({'text': lines})

    def key_accepted(self):
        self.flush_text()
        value = self.cpu.a
        name = chr(value) if 32 < value < 127 and value != 0x5f else f'<{value:02x}>'
        if self.events and 'keys' in self.events[-1]:
            self.events[-1]['keys'] += name
        else:
            self.events.append({'keys': name})

    def logical(self, side):
        if side not in self.disks:
            path = ROOT / f'build/c64/original-v2-{side.lower()}/logical.bin'
            if not path.exists():
                raise SystemExit('Run python3 tools/analyze_c64.py and tools/mmdisk.py first')
            self.disks[side] = bytearray(path.read_bytes())
        return self.disks[side]

    def disk_call(self, command):
        cpu, mem = self.cpu, self.mem
        p = mem[0x9d00:0x9d07]
        call = {'command': command, 'name': COMMANDS[command],
                # The game's JSR to the jump table: its return address is on top of the stack.
                'caller': f"${((mem[0x100 | cpu.s + 1 & 0xff] | mem[0x100 | cpu.s + 2 & 0xff] << 8) - 2) & 0xffff:04x}",
                'address': p[0] | p[1] << 8, 'length': p[2] | p[3] << 8,
                'offset': p[4], 'block': p[5] | p[6] << 8, 'side': self.side}
        self.flush_text()
        self.events.append(call)
        return call

    def disk_return(self, call):
        """Leave registers and the loader's zero page as the real routine does
        (source/c64/fastload-c64.info): status 0 compared with 0, Y the low
        byte of the length, X the loader's clock-line value, $FC-$FF used up."""
        cpu, mem = self.cpu, self.mem
        cpu.a, cpu.nz, cpu.fc = 0, 0, 1
        cpu.y = call['length'] & 0xff
        cpu.x = mem[0x9d23]
        mem[0xfc] = call['address'] & 0xff
        mem[0xfd] = (call['address'] >> 8) + (call['length'] >> 8) & 0xff
        mem[0xfe] = mem[0xff] = 0
        cpu.rts()
        for field in ('address', 'length', 'offset', 'block'):
            call[field] = f'${call[field]:0{2 if field == "offset" else 4}x}'

    def disk_read(self):
        call = self.disk_call(0)
        data = mmdisk.read(self.logical(self.side), call['block'], call['offset'], call['length'])
        for i, byte in enumerate(data):
            self.machine.store(call['address'] + i & 0xffff, byte)
        call['sha256'] = hashlib.sha256(data).hexdigest()
        self.note_coverage()
        self.loaded.append((call['address'], call['address'] + call['length'],
                            (self.side, call['block'], call['address'])))
        self.disk_return(call)

    def note_coverage(self):
        """Credit executed addresses to the load that put the code there. Called
        before every load, because a load may overwrite code that has run."""
        seen = self.cpu.seen
        if not any(seen):
            return
        for address in [a for a in range(0x0200, 0xd000) if seen[a]]:
            for start, end, key in reversed(self.loaded):
                if start <= address < end:
                    self.coverage.setdefault(key, set()).add(address)
                    break
        seen[0x0200:0xd000] = [0] * (0xd000 - 0x0200)

    def disk_write(self):
        call = self.disk_call(1)
        data = bytes(self.machine.ram(call['address'] + i & 0xffff) for i in range(call['length']))
        start = (call['block'] % mmdisk.BLOCKS) * 256 + call['offset']
        self.logical(self.side)[start:start + len(data)] = data
        call['sha256'] = hashlib.sha256(data).hexdigest()
        self.disk_return(call)

    def picture(self):
        """The screen as a C64 would show it now: 200 rows of 320 colour numbers.

        Once the game's interrupt handler is installed, what is shown depends
        on its display mode ($0389) and not on the registers of the moment,
        which the handler rewrites twice a frame (docs/C64-CODE.md).
        """
        machine, mem = self.machine, self.mem
        vic = machine.vic
        mode = mem[0x0389] if mem[0x0314] | mem[0x0315] << 8 == 0xc5c5 else 0
        if mode == 2:
            segments = [Segment(0, SPLIT_ROW, 0, 0x18, vic[0x11], vic[0x16]),
                        Segment(SPLIT_ROW, 200, 3, 0x38, vic[0x11], vic[0x16])]
        elif mode == 1:
            segments = [Segment(0, 200, 3, 0x38, vic[0x11], vic[0x16])]
        else:
            segments = [Segment(0, 200, ~machine.cia2[0] & 3, vic[0x18], vic[0x11], vic[0x16])]
        return render(machine.ram_image(), machine.color, machine.chargen, segments, vic[0x21] & 15)

    # -- script -------------------------------------------------------------------------
    def run_until(self, address, limit):
        self.stop_at = address
        had = self.cpu.hooks[address]
        self.cpu.hooks[address] = 1
        done = self.cpu.run(limit)
        self.cpu.hooks[address] = had
        self.stop_at = None
        if self.cpu.pc != address or done >= limit:
            raise OracleError(f'Did not reach ${address:04x} in {limit} instructions; at ${self.cpu.pc:04x}')

    def run_idle(self, limit):
        """Run until the game asks the KERNAL for a key and none is there."""
        self.idle_stop = True
        had = self.cpu.hooks[GETIN]
        self.cpu.hooks[GETIN] = 1
        self.cpu.run(limit)
        self.cpu.hooks[GETIN] = had
        self.idle_stop = False

    def type_keys(self, codes):
        for i, code in enumerate(codes):
            self.mem[0x0277 + i] = code
        self.mem[0xc6] = len(codes)

    def play(self, lines, out=None, keep_ram=False, limit=2_000_000_000, pictures=True, on_mark=None):
        """Play script lines. May be called again to go on from where the last
        call stopped: whether the machine is held at the key wait is kept, so
        that the join adds no pass of the wait loop (the passes feed the dice)."""
        try:
            return self.steps(lines, out, keep_ram, limit, pictures, on_mark)
        finally:
            self.flush_text()

    def steps(self, lines, out, keep_ram, limit, pictures, on_mark):
        for raw in lines:
            words = raw.split('#')[0].split()
            if not words:
                continue
            op, args = words[0], words[1:]
            if op in ('press', 'ready'):
                if not self.waiting:
                    self.run_until(KEY_WAIT_LOOP, limit)
                self.waiting = op == 'ready'
                if op == 'press':
                    self.type_keys([int(args[0], 16)])
            elif op == 'wait':
                self.run_idle(int(args[0][1:], 16) if args[0].startswith('$') else int(args[0]))
                self.waiting = False
            elif op == 'until':
                self.run_until(int(args[0].lstrip('$'), 16), limit)
                self.waiting = False
            elif op == 'key':
                self.type_keys([int(a, 16) for a in args])
                self.waiting = False
            elif op == 'poll':
                address = int(args[0].lstrip('$'), 16)
                if not int(args[1], 16):
                    raise OracleError('poll requires a nonzero key')
                self.run_until(address, limit)
                if bytes(self.mem[address:address + 3]) not in (b'\x20\xe4\xff', b'\x20\x87\xa0'):
                    raise OracleError(f'poll ${address:04x} is not JSR GETIN or the key reader')
                self.type_keys([int(args[1], 16)])
                self.waiting = False
            elif op == 'poke':
                for i, value in enumerate(args[1:]):
                    self.machine.store(int(args[0], 16) + i, int(value, 16))
            elif op == 'attach':
                self.side = args[0]
                self.flush_text()
                self.events.append({'attach': self.side})
            elif op == 'pauses':
                if not self.waiting:
                    raise SystemExit('`pauses` must follow `ready`: the machine has to be still when it changes')
                self.pause_key = 0 if args[0] == 'off' else int(args[0], 16)
            elif op == 'restart':
                self.flush_text()
                if self.with_coverage:
                    self.note_coverage()
                self.events.append({'restart': True})
                self.power_on()
                self.waiting = False
            elif op == 'mark':
                self.flush_text()
                self.events.append({'mark': args[0], 'pc': f'${self.cpu.pc:04x}',
                                    'port_01': f'${self.mem[1]:02x}'})
                if out and keep_ram:
                    (out / f'{args[0]}-ram.bin').write_bytes(self.machine.ram_image())
                if out and pictures:
                    write_png(out / f'{args[0]}.png', self.picture())
                if on_mark:
                    on_mark(args[0])
            else:
                raise SystemExit(f'Step not supported by the oracle: {raw}')
        return self.events


BOOT_CALLERS = {'$21fc', '$21ff', '$2225'}  # the second boot file's calls, before $4000


def comparable(events):
    """The parts of a trace that must be the same in VICE and here."""
    out = []
    for e in events:
        if 'command' in e:
            if e['caller'] in BOOT_CALLERS and e['side'] == 'A':
                continue
            out.append({k: e[k] for k in ('name', 'side', 'caller', 'address', 'length',
                                          'offset', 'block', 'sha256') if k in e})
        elif 'mark' in e:
            out.append({'mark': e['mark']})
        else:
            out.append(e)
    return out


def compare(mine, reference):
    """Index and description of the first difference, or None."""
    a, b = comparable(mine), comparable(reference)
    for i, (x, y) in enumerate(zip(a, b)):
        if x != y:
            return i, x, y
    if len(a) != len(b):
        i = min(len(a), len(b))
        return i, a[i] if i < len(a) else None, b[i] if i < len(b) else None
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('script', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--compare', type=Path, help='folder with a VICE trace.json to check against')
    parser.add_argument('--keep-ram', action='store_true', help='write NAME-ram.bin at every mark')
    parser.add_argument('--settle', action='store_true',
                        help='play the script as c64_trace.py --settle does, for comparing pictures')
    parser.add_argument('--quick', action='store_true',
                        help='play the script as c64_trace.py --quick does: a key ends every pause')
    parser.add_argument('--coverage', action='store_true',
                        help='write coverage.json: executed addresses per load (side, block, address)')
    args = parser.parse_args()
    out = (args.output or ROOT / 'build/oracle' / args.script.stem).resolve()
    out.mkdir(parents=True, exist_ok=True)
    oracle = Oracle(args.coverage)
    started = time.time()
    try:
        lines = args.script.read_text().splitlines()
        lines = settled(lines) if args.settle else quick(lines) if args.quick else lines
        events = oracle.play(lines, out, args.keep_ram)
    finally:
        (out / 'trace.json').write_text(json.dumps(oracle.events, indent=1) + '\n')
    instructions, cycles = oracle.spent[0] + oracle.cpu.instructions, oracle.spent[1] + oracle.cpu.cycles
    seconds = time.time() - started
    counts = {kind: sum(kind in e for e in events) for kind in ('text', 'command', 'mark')}
    keys = sum(len(re.findall(r'<..>|.', e['keys'])) for e in events if 'keys' in e)
    print(f"{instructions:,} instructions, {cycles / 985248:.0f} s of C64 time, {seconds:.1f} s here; "
          f"{keys} keys, {counts['text']} text events, {counts['command']} disk commands, {counts['mark']} marks")
    if args.coverage:
        oracle.note_coverage()
        (out / 'coverage.json').write_text(json.dumps(
            [{'side': side, 'block': f'${block:04x}', 'address': f'${address:04x}',
              'executed': [f'${a:04x}' for a in sorted(addresses)]}
             for (side, block, address), addresses in sorted(oracle.coverage.items())], indent=1) + '\n')
    if args.compare:
        reference = json.loads((args.compare / 'trace.json').read_text())
        difference = compare(events, reference)
        if difference:
            index, mine, theirs = difference
            raise SystemExit(f'DIFFERS from {args.compare} at event {index}:\n  oracle: {mine}\n  VICE:   {theirs}')
        print(f'OK: {len(comparable(events))} events equal to {args.compare}/trace.json')


if __name__ == '__main__':
    main()
