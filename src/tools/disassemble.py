#!/usr/bin/env python3
"""Split every game binary into code and data, and rebuild each one exactly.

The game is 11 fixed reads from side A and the named files of sides B-D
(docs/C64-LOADER.md). This tool

  1. collects them as modules (a file that is identical on several sides is
     one module),
  2. follows the code statically from known entries (tools/code6502.py),
     with every overlay traced against the resident code it calls,
  3. writes a da65 info file per code module to source/c64/game/, built from
     the traced code/data split and the hand-kept names in
     source/c64/game/symbols.txt and hints in source/c64/game/hints.txt,
  4. disassembles, reassembles and compares every byte (--rebuild),
  5. writes docs/c64-code-map.json: per module the code and data ranges, the
     entries and what is still unexplained; and the hardware inventory.

  python3 tools/disassemble.py            trace and report
  python3 tools/disassemble.py --rebuild  also write info files and rebuild
"""
import argparse
import collections
import hashlib
import json
from pathlib import Path
import subprocess

from area import Area
from c64 import ROOT, shared_root
from code6502 import Image, Trace
import mmdisk

GAME = ROOT / 'source/c64/game'

# Side A's fixed reads, in the order the boot code makes them. Later loads
# overwrite earlier ones where they overlap ($4A00 over the end of $3500).
SIDE_A = [  # block, length, address, id, kind, what
    (0x000, 0x0f80, 0x4000, 'title', 'title', 'Title program'),
    (0x070, 0x145e, 0x5000, 'title-data-1', 'data', 'Title screen data, first load'),
    (0x088, 0x0f4a, 0x5000, 'title-data-2', 'data', 'Title screen data, second load'),
    (0x017, 0x14ff, 0x0b00, 'res-0b00', 'resident', 'Resident: jump table, printers, keys, dice'),
    (0x03f, 0x292c, 0xa000, 'res-a000', 'resident', 'Resident: play logic and strings'),
    (0x160, 0x10ef, 0x8c00, 'res-8c00', 'resident', 'Resident: item and other name tables'),
    (0x195, 0x00bc, 0xc92c, 'res-c92c', 'resident', 'Resident: tables'),
    (0x190, 0x0218, 0xc9e8, 'font', 'data', 'Font, 8 bytes per character from $20'),
    (0x1a0, 0x0200, 0x2000, 'start', 'overlay', 'Start-up stub: loads the rest, first disk prompt'),
    (0x140, 0x16ee, 0x3500, 'res-3500', 'resident', 'Resident: loaded by the start-up stub'),
    (0x184, 0x04a0, 0x4a00, 'res-4a00', 'resident', 'Resident: loaded by the start-up stub'),
]
FILES = {   # named files whose purpose is known (docs/C64-LOADER.md, docs/C64-RUNTIME.md)
    'RO': 'Roster: 18 characters of 128 bytes',
    'GO': 'Options menu, inn and character creation; holds the only disk write',
    'EN': 'Encounter: picks the monsters, reads their records and picture',
    'CM': 'Combat',
    'C3': 'Combat, second part: jump table, texts and monster-ability handlers',
    'ST': 'Treasure and search',
    '91': 'Blacksmith', '92': 'Temple', '93': 'Food shop', '94': 'Statue verses',
    '95': 'Training hall', '96': 'Tavern',
}
RESIDENT_ORDER = ['res-0b00', 'res-a000', 'res-8c00', 'res-c92c', 'font', 'res-3500', 'res-4a00']


class Module:
    def __init__(self, name, base, data, kind, what, sources):
        self.name, self.base, self.data, self.kind, self.what = name, base, data, kind, what
        self.sources = sources          # ['A $017', 'B EG', ...]
        self.blocks = set()             # {(side, first logical block)}
        self.entries = {}               # address -> reason
        self.code = set()               # addresses of instruction bytes
        self.instructions = {}
        self.problems = []

    @property
    def end(self):
        return self.base + len(self.data)

    def __contains__(self, address):
        return self.base <= address < self.end


def modules():
    """Every binary of the game, in a stable order."""
    out = []
    side_a = (ROOT / 'build/c64/original-v2-a/logical.bin')
    if not side_a.exists():
        raise SystemExit('Run python3 tools/analyze_c64.py and tools/mmdisk.py first')
    logical = side_a.read_bytes()
    for block, length, address, name, kind, what in SIDE_A:
        out.append(Module(name, address, mmdisk.read(logical, block, 0, length), kind, what,
                          [f'A ${block:03x}']))
        out[-1].blocks.add(('A', block))
    table = json.loads((ROOT / 'docs/c64-logical-disk.json').read_text())
    by_hash = {}
    for side in table:
        letter = side['side']
        for slot, entry in enumerate(side['files']):
            path = ROOT / f"build/c64/original-v2-{letter.lower()}/logical/{slot:02d}-{entry['name']}.bin"
            data = path.read_bytes()
            key = (entry['name'], entry['sha256'])
            if key in by_hash:
                by_hash[key].sources.append(f"{letter} {entry['name']}")
                by_hash[key].blocks.add((letter, int(entry['block'][1:], 16)))
                continue
            address = int(entry['address'][1:], 16)
            kind = {0x8200: 'area', 0x6000: 'data', 0x6900: 'overlay'}.get(address, 'overlay')
            if address == 0x4ea0 and entry['name'] != 'C3':
                kind = 'data'       # a set of wall pictures
            if data[2] == 0x7b and address != 0x8200:
                kind = 'data'       # a packed picture: length, then runs marked by $7B
            what = FILES.get(entry['name']) or {'area': 'Area: map grids, then code and text for its events',
                                                'data': 'Packed picture'}.get(kind, '')
            if address == 0x4ea0 and entry['name'] != 'C3':
                what = 'Wall picture set'
            module = Module(None, address, data, kind, what, [f"{letter} {entry['name']}"])
            module.file = entry['name']
            module.blocks.add((letter, int(entry['block'][1:], 16)))
            by_hash[key] = module
            out.append(module)
    for module in out:
        if module.name is None:
            sides = ''.join(s[0] for s in module.sources).lower()
            module.name = f'{module.file.lower()}-{sides}'
    return out


def read_hints():
    """source/c64/game/hints.txt: things the tracer cannot work out.

      entry MODULE ADDR [ADDR...]  # code reached through a table or pointer
      noreturn ADDR                # resident subroutine that never returns
      words MODULE ADDR COUNT      # table of code addresses, low and high together
      with MODULE OTHER            # OTHER is in memory whenever MODULE runs
      calls MODULE OTHER           # MODULE's calls into OTHER's range go to OTHER
      same MODULE OTHER            # MODULE is OTHER's code again: same entries
      unused MODULE ADDR [ADDR...] # code that nothing refers to (read by eye)
    """
    hints = collections.defaultdict(list)
    path = GAME / 'hints.txt'
    if path.exists():
        for line in path.read_text().splitlines():
            words = line.split('#')[0].split()
            if words:
                hints[words[0]].append(words[1:])
    return hints


def hexa(word):
    return int(word.lstrip('$'), 16)


def address_tables(trace):
    """Find jumps and calls whose operand the code fills in from two tables.

    The game's dispatch idiom is
        LDA low,X / STA op+1 / LDA high,X / STA op+2 / ... / op: JSR $0000
    Returns [(address of the JSR or JMP, low table, high table)].
    """
    def loader(store):
        for back in (3, 2):
            inst = trace.instructions.get(store - back)
            if inst and inst.length == back and inst.mnemonic == 'LDA' and inst.mode in ('absx', 'absy'):
                return inst.operand
    out = []
    for address, inst in trace.instructions.items():
        if inst.mnemonic not in ('JMP', 'JSR') or inst.mode != 'abs':
            continue
        tables = []
        for byte in (address + 1, address + 2):
            stores = [s for s, kind in trace.references.get(byte, ()) if kind == 'write']
            tables.append({loader(s) for s in stores} - {None})
        if len(tables[0]) == 1 and len(tables[1]) == 1:
            out.append((address, tables[0].pop(), tables[1].pop()))
    return out


VECTORS = {0x0314: 'IRQ', 0x0316: 'BRK', 0x0318: 'NMI', 0xfffa: 'NMI', 0xfffe: 'IRQ'}


def vector_handlers(trace):
    """[(handler address, vector name, where set)] for LDA #lo / STA v / LDA #hi / STA v+1."""
    out = []
    for address, inst in trace.instructions.items():
        chain = [trace.instructions.get(address + offset) for offset in (2, 5, 7)]
        if (inst.mnemonic == 'LDA' and inst.mode == 'imm' and all(chain)
                and chain[0].mnemonic == 'STA' and chain[0].operand in VECTORS
                and chain[1].mnemonic == 'LDA' and chain[1].mode == 'imm'
                and chain[2].mnemonic == 'STA' and chain[2].operand == chain[0].operand + 1):
            out.append((inst.operand | chain[1].operand << 8, VECTORS[chain[0].operand], address))
    return out


def analyse():
    mods = modules()
    by_name = {m.name: m for m in mods}
    hints = read_hints()
    resident = Image()
    for name in RESIDENT_ORDER:
        resident.load(name, by_name[name].base, by_name[name].data)
    no_return = {hexa(w[0]) for w in hints['noreturn']}
    with_ = collections.defaultdict(list)
    for module, other in hints['with']:
        with_[module].append(other)
    calls = collections.defaultdict(list)
    for module, other in hints['calls']:
        calls[module].append(other)

    def owner_of(target, image):
        """The module a code address belongs to in an image, if it has one."""
        module = by_name.get(image.owner.get(target))
        return module if module and module.kind != 'data' else None

    # Entries: defaults by kind, then hints.
    for m in mods:
        if m.kind in ('overlay', 'title'):
            m.entries[m.base] = 'load address'
            address = m.base    # many start with a table of jumps
            while m.data[address - m.base] == 0x4c and m.data[address + 3 - m.base] == 0x4c or (
                    address > m.base and m.data[address - m.base] == 0x4c):
                m.entries[address] = 'jump table'
                address += 3
        if m.kind == 'area':
            m.entries[0x8432] = 'called by resident code after a move'
    for base in (0x0b00, 0xa000):
        address = base
        while resident.memory.get(address) == 0x4c:
            by_name[resident.owner[address]].entries[address] = 'jump table'
            address += 3
    for module, *addresses in hints['entry']:
        for address in addresses:
            by_name[module].entries.setdefault(hexa(address), 'hint')
    for module, *addresses in hints['unused']:
        for address in addresses:
            by_name[module].entries.setdefault(hexa(address), 'unreferenced')

    images, traces = {}, {}
    for m in mods:
        if m.kind in ('overlay', 'area', 'title'):
            image = Image()
            image.memory, image.owner = dict(resident.memory), dict(resident.owner)
            for other in with_[m.name]:
                image.load(other, by_name[other].base, by_name[other].data)
            image.load(m.name, m.base, m.data)
            images[m.name] = image
            # Stop at the module's edge: the resident code and companions are traced on their own.
            traces[m.name] = Trace(image, no_return=no_return,
                                   stop={a for a, owner in image.owner.items() if owner != m.name})
    images['resident'] = resident
    traces['resident'] = Trace(resident, no_return=no_return)
    tables = {}   # (image name, low, high) -> [targets]; 'words' tables have high = low + 1
    counts = {}   # (image name, low) -> entries of a 'words' table

    def add_table(name, low, high, count, why):
        image, found = images[name], []
        step = 2 if high == low + 1 else 1
        for i in range(count):
            target = image.memory.get(low + i * step, 0) | image.memory.get(high + i * step, 0) << 8
            owner = owner_of(target, image)
            if owner is None:   # a table in one file may point into a file it calls
                owner = next((by_name[other] for other in calls[image.owner.get(low)]
                              if target in by_name[other]), None)
            if owner:
                owner.entries.setdefault(target, why)
                found.append(target)
        tables[(name, low, high)] = found

    for module, table, count in hints['words']:
        name = 'resident' if by_name[module].kind == 'resident' else module
        counts[(name, hexa(table))] = int(count)
        add_table(name, hexa(table), hexa(table) + 1, int(count),
                  f'address table at ${hexa(table):04x} in {module}')

    cross = collections.defaultdict(set)   # target with no owner <- (module, from)
    changed = True
    while changed:
        changed = False
        for module, other in hints['same']:
            by_name[module].entries.update(by_name[other].entries)
        for name, trace in traces.items():
            image = images[name]
            entries = {}
            for m in mods:
                if name == 'resident' and m.kind == 'resident' or m.name == name:
                    entries.update(m.entries)
            before = len(trace.instructions)
            trace.run(entries)
            changed |= len(trace.instructions) != before
            for address, low, high in address_tables(trace):
                if (name, low, high) not in tables and high > low + 1:
                    add_table(name, low, high, high - low,
                              f'address tables at ${low:04x}/${high:04x} for the call at ${address:04x}')
                    changed = True
            for target, vector, where in vector_handlers(trace):
                owner = owner_of(target, image)
                if owner and target not in owner.entries:
                    owner.entries[target] = f'{vector} handler, installed at ${where:04x}'
                    changed = True
            for target, sources in trace.references.items():
                for source, kind in sources:
                    if kind not in ('jsr', 'jmp', 'branch') or image.owner.get(target) == image.owner.get(source):
                        continue
                    owner = owner_of(target, image)
                    if owner and target not in owner.entries:
                        owner.entries[target] = f'called from {image.owner[source]} ${source:04x}'
                        changed = True
                    elif owner is None and target not in image.memory:
                        for other in calls[image.owner[source]]:
                            if target in by_name[other] and target not in by_name[other].entries:
                                by_name[other].entries[target] = f'called from {image.owner[source]} ${source:04x}'
                                changed = True
                        if not any(target in by_name[other] for other in calls[image.owner[source]]):
                            cross[target].add((image.owner[source], source))
    for m in mods:
        trace = traces.get('resident' if m.kind == 'resident' else m.name)
        if trace:
            m.instructions = {a: i for a, i in trace.instructions.items() if a in m and trace.image.owner[a] == m.name}
            m.code = {a for a in trace.code if a in m and trace.image.owner[a] == m.name}
            m.problems = [p for p in trace.problems if p[0] in m and trace.image.owner.get(p[0]) == m.name]
    analyse.tables, analyse.counts = tables, counts
    return mods, traces, cross


def gaps(module):
    """[(start, end)] runs of bytes that are not code."""
    out, start = [], None
    for address in range(module.base, module.end + 1):
        data = address < module.end and address not in module.code
        if data and start is None:
            start = address
        elif not data and start is not None:
            out.append((start, address))
            start = None
    return out


def is_text(data):
    """Printable upper-case text, as the game stores it (0 ends, 13 is a new line)."""
    if len(data) < 4 or any(not (b == 13 or 32 <= b < 96) for b in data):
        return False
    return sum(65 <= b <= 90 or b == 32 for b in data) * 10 >= len(data) * 7


def text_runs(module, start, end):
    """Split a data run into [(start, end, 'text' or 'data')]."""
    data = module.data
    out, address = [], start
    while address < end:
        stop = address
        while stop < end and (data[stop - module.base] == 13 or 32 <= data[stop - module.base] < 96):
            stop += 1
        if is_text(data[address - module.base:stop - module.base]):
            out.append((address, stop, 'text'))
            address = stop
        else:
            address = max(stop, address) + 1 if stop == address else stop
    # Fill the holes between text runs with data.
    filled, at = [], start
    for a, b, kind in out:
        if a > at:
            filled.append((at, a, 'data'))
        filled.append((a, b, kind))
        at = b
    if at < end:
        filled.append((at, end, 'data'))
    return filled


def area_layout(module, tables):
    """Named parts of an area file: {start: (end, name, comment)}."""
    parts = {0x8200: (0x8300, 'walls', '16 x 16, south row first; two bits per direction'),
             0x8300: (0x8400, 'states', '16 x 16; low bit of each direction field blocks movement'),
             0x8400: (0x8432, 'area_data', '50 bytes; 8-19 are the four neighbouring areas')}
    for (name, low, high), targets in tables.items():
        if name == module.name and high > low + 1:
            count = high - low
            cells = low - 2 * count
            parts[cells - 1] = (cells, 'event_count', '')
            parts[cells] = (cells + count, 'event_squares', 'y * 16 + x')
            parts[cells + count] = (low, 'event_facings', 'facing masks that trigger each event')
            parts[low] = (high, 'event_low', 'handler addresses, low bytes')
            parts[high] = (high + count, 'event_high', 'handler addresses, high bytes')
    return parts


def ranges(module, tables):
    """Everything that is not code, typed: [(start, end, kind, name, comment)].

    kind is 'bytes', 'text' or 'words' (a table of code addresses).
    """
    named = area_layout(module, tables) if module.kind == 'area' else {}
    for (name, low, high), targets in tables.items():
        owner = module.name if module.kind != 'resident' else 'resident'
        if name != owner or module.kind == 'area':
            continue
        if low in module and high == low + 1:
            named[low] = (low + 2 * analyse.counts[(name, low)], 'WORDS', 'code addresses')
        elif low in module:
            named[low] = (high, f'low_{low:04x}', 'code addresses, low bytes')
            named[high] = (high + (high - low), f'high_{low:04x}', 'code addresses, high bytes')
    out = []
    for start, end in gaps(module):
        address = start
        while address < end:
            if address in named and named[address][0] <= end:
                stop, name, comment = named[address]
                kind = 'words' if name == 'WORDS' else 'bytes'
                out.append((address, stop, kind, '' if name == 'WORDS' else name, comment))
                address = stop
                continue
            stop = min([a for a in named if address < a < end] + [end])
            for a, b, kind in text_runs(module, address, stop):
                out.append((a, b, 'text' if kind == 'text' else 'bytes', '', ''))
            address = stop
    return out


def read_symbols():
    """source/c64/game/symbols.txt: SCOPE ADDRESS NAME [; comment].

    SCOPE is * for an address that means the same everywhere (zero page,
    hardware, KERNAL, resident code) or a module name.
    """
    symbols = collections.defaultdict(dict)
    path = GAME / 'symbols.txt'
    if path.exists():
        for line in path.read_text().splitlines():
            body, _, comment = line.partition(';')
            words = body.split()
            if len(words) >= 3 and not words[0].startswith('#'):
                symbols[words[0]][hexa(words[1])] = (words[2], comment.strip())
    return symbols


def info_file(module, tables, symbols, referenced):
    """da65 info text for a module."""
    lines = [f'# {module.name}: {module.what or "game file"}',
             f'# From {", ".join(module.sources)}. Loads at ${module.base:04X}, {len(module.data)} bytes.',
             '# Generated by tools/disassemble.py from the traced code/data split,',
             '# source/c64/game/hints.txt and symbols.txt. Do not edit; edit those.',
             f'GLOBAL {{ STARTADDR ${module.base:04X}; CPU "6502"; COMMENTS 0; }};', '']
    kinds = {'bytes': 'ByteTable', 'text': 'TextTable', 'words': 'AddrTable'}
    for start, end, kind, name, comment in ranges(module, tables):
        extra = (f' NAME "{name}";' if name else '') + (f' COMMENT "{comment}";' if comment else '')
        lines.append(f'RANGE {{ START ${start:04X}; END ${end - 1:04X}; TYPE {kinds[kind]};{extra} }};')
    lines.append('')
    names = dict(symbols['*'])
    names.update(symbols[module.name])
    taken = {name for start, end, kind, name, comment in ranges(module, tables) if name}
    for address in sorted(names):
        name, comment = names[address]
        inside = address in module
        if (inside or address in referenced) and name not in taken:
            if inside and address not in module.instructions and address in module.code:
                continue    # da65 cannot label the middle of an instruction
            extra = f' COMMENT "{comment}";' if comment and inside else ''
            lines.append(f'LABEL {{ ADDR ${address:04X}; NAME "{name}";{extra} }};')
    return '\n'.join(lines) + '\n'


def rebuild(mods, traces, tables):
    """Write an info file per code module, then da65 -> ca65 -> ld65 -> compare."""
    symbols = read_symbols()
    toolchain = shared_root() / 'tools/toolchain/local/bin'
    out = ROOT / 'build/source/game'
    out.mkdir(parents=True, exist_ok=True)
    (GAME / 'info').mkdir(parents=True, exist_ok=True)
    for old in (GAME / 'info').glob('*.info'):
        old.unlink()
    failures, built = [], 0
    run = lambda *args: subprocess.run([str(a) for a in args], capture_output=True, text=True)
    for m in mods:
        if m.kind == 'data':
            continue
        trace = traces['resident' if m.kind == 'resident' else m.name]
        referenced = set()
        for address, inst in m.instructions.items():
            if inst.operand is not None and inst.mode != 'imm':
                referenced.add(inst.target if inst.target is not None else inst.operand)
        info = GAME / 'info' / f'{m.name}.info'
        info.write_text(info_file(m, tables, symbols, referenced))
        (out / f'{m.name}.orig').write_bytes(m.data)
        (out / f'{m.name}.cfg').write_text(
            f'MEMORY {{ MAIN: start = ${m.base:04X}, size = ${len(m.data):04X}, file = %O; }}\n'
            'SEGMENTS { CODE: load = MAIN, type = ro; }\n')
        steps = [(toolchain / 'da65', '-i', info, '-o', out / f'{m.name}.s', out / f'{m.name}.orig'),
                 (toolchain / 'ca65', '-t', 'none', out / f'{m.name}.s', '-o', out / f'{m.name}.o'),
                 (toolchain / 'ld65', '-C', out / f'{m.name}.cfg', '-o', out / f'{m.name}.bin', out / f'{m.name}.o')]
        error = None
        for step in steps:
            result = run(*step)
            if result.returncode:
                error = f'{Path(step[0]).name}: {result.stderr.strip().splitlines()[:2]}'
                break
        if not error and (out / f'{m.name}.bin').read_bytes() != m.data:
            new = (out / f'{m.name}.bin').read_bytes()
            first = next((i for i, (x, y) in enumerate(zip(new, m.data)) if x != y), min(len(new), len(m.data)))
            error = f'differs from ${m.base + first:04x} ({len(new)} bytes built, {len(m.data)} original)'
        if error:
            failures.append((m.name, error))
        else:
            built += 1
    return built, failures


def summary(module, tables):
    """Byte counts by kind for one code module."""
    counts = collections.Counter(code=len(module.code))
    for start, end, kind, name, comment in ranges(module, tables):
        data = module.data[start - module.base:end - module.base]
        if kind == 'text':
            counts['text'] += end - start
        elif kind == 'words' or name:
            counts['tables'] += end - start
        elif len(set(data)) == 1:
            counts['fill'] += end - start
        else:
            counts['other data'] += end - start
    return counts


def report(mods, traces, cross, verbose):
    total = collections.Counter()
    for m in mods:
        if m.kind == 'data':
            total['data files'] += len(m.data)
            continue
        counts = summary(m, analyse.tables)
        total.update(counts)
        if verbose or m.problems:
            print(f"{m.name:14s} ${m.base:04x}-${m.end - 1:04x} {len(m.data):6d} bytes  "
                  + '  '.join(f'{k} {n}' for k, n in counts.items()))
        for address, reason, entry in m.problems:
            print(f'      PROBLEM ${address:04x} {reason} (from entry ${entry:04x}: {m.entries.get(entry, "?")})')
    print('Bytes: ' + ', '.join(f'{k} {n}' for k, n in total.items()))
    if verbose:
        print('Calls to addresses outside the resident code and the calling module:')
        for target in sorted(cross):
            names = sorted({c[0] for c in cross[target]})
            print(f'  ${target:04x} from {len(cross[target])} places in {len(names)} modules: '
                  + ' '.join(names[:8]) + (' ...' if len(names) > 8 else ''))


# What ties the code to the C64. An address belongs to the first row it fits.
MACHINE = [  # category, first, last, note
    ('CPU port', 0x0000, 0x0001, 'memory configuration'),
    ('KERNAL variables', 0x00a0, 0x00a2, 'jiffy clock'),
    ('KERNAL variables', 0x00c5, 0x00c6, 'keyboard'),
    ('KERNAL variables', 0x00cc, 0x00cc, 'cursor'),
    ('KERNAL variables', 0x0277, 0x0291, 'keyboard buffer and flags'),
    ('KERNAL variables', 0x0314, 0x0319, 'interrupt vectors'),
    ('Text screen', 0x0400, 0x07ff, 'screen matrix; colours of the upper bitmap in play'),
    ('Disk loader', 0x9d00, 0x9d1f, 'parameters and jump table'),
    ('Lower-screen colours', 0xcc00, 0xcfff, 'screen matrix of VIC bank 3'),
    ('VIC-II', 0xd000, 0xd3ff, ''),
    ('SID', 0xd400, 0xd7ff, ''),
    ('Colour RAM', 0xd800, 0xdbff, ''),
    ('CIA', 0xdc00, 0xddff, ''),
    ('KERNAL calls and RAM under ROM', 0xe000, 0xffff, 'lower bitmap is at $E000; vectors at $FFFA'),
]


def machine_uses(mods):
    """{category: {address: [(module, pc, how)]}} from every traced instruction."""
    out = collections.defaultdict(lambda: collections.defaultdict(list))
    for m in mods:
        for pc, inst in sorted(m.instructions.items()):
            if inst.operand is None or inst.mode in ('imm', 'rel'):
                continue
            if inst.mnemonic in ('JSR', 'JMP') and inst.mode == 'abs' and inst.operand in (0x0000, 0xffff):
                continue    # a placeholder the code fills in before use
            # STA $D7FF,X with X from 1 is a store to $D800 and up.
            indexed = inst.mode in ('absx', 'absy', 'zpx', 'zpy')
            address = inst.operand + 1 if indexed and inst.operand & 0xff == 0xff else inst.operand
            for category, first, last, note in MACHINE:
                if first <= address <= last:
                    how = ('call' if inst.mnemonic in ('JSR', 'JMP') else
                           'write' if inst.mnemonic in ('STA', 'STX', 'STY') else
                           'modify' if inst.writes else 'read')
                    if inst.mode in ('absx', 'absy', 'zpx', 'zpy'):
                        how += ' indexed'
                    out[category][address].append((m.name, pc, how))
                    break
    return out


def pointer_constants(mods):
    """Addresses built from two immediates and stored to adjacent locations.

    LDA #low / STA p / LDA #high / STA p+1: how the code aims a zero-page
    pointer. Returns {target: [(module, pc, p)]} for targets in screen,
    bitmap or colour memory, which absolute operands alone would not show.
    """
    areas = [(0x0400, 0x07ff), (0x2000, 0x3fff), (0xcc00, 0xcfff), (0xd800, 0xdbff), (0xe000, 0xffff)]
    out = collections.defaultdict(list)
    pointers = {inst.operand for m in mods for inst in m.instructions.values()
                if inst.mode in ('indx', 'indy')}
    for m in mods:
        for pc, inst in sorted(m.instructions.items()):
            chain = [m.instructions.get(pc + 2)]
            if not (inst.mnemonic == 'LDA' and inst.mode == 'imm' and chain[0]
                    and chain[0].mnemonic == 'STA' and chain[0].mode in ('zp', 'abs')):
                continue
            second = m.instructions.get(pc + 2 + chain[0].length)
            store = m.instructions.get(pc + 4 + chain[0].length) if second else None
            if (second and store and second.mnemonic == 'LDA' and second.mode == 'imm'
                    and store.mnemonic == 'STA' and store.operand == chain[0].operand + 1):
                target = inst.operand | second.operand << 8
                if (chain[0].operand in pointers and any(a <= target <= b for a, b in areas)
                        and not (m.kind != 'resident' and target in m)):
                    out[target].append((m.name, pc, chain[0].operand))
    return out


def machine_routines(mods, traces):
    """Group machine-specific operands by the subroutine they are in.

    A subroutine starts at an entry or at the target of a JSR; an instruction
    belongs to the nearest start below it in its module. Returns
    [(module, start, callers, {category: count})].
    """
    callers = collections.Counter()
    starts = {}
    for m in mods:
        if m.kind == 'data':
            continue
        trace = traces['resident' if m.kind == 'resident' else m.name]
        found = {a for a in m.entries if a in m}
        for target, sources in trace.references.items():
            if target in m and any(kind == 'jsr' for _, kind in sources):
                found.add(target)
        starts[m.name] = sorted(found)
        for inst in m.instructions.values():
            if inst.mnemonic == 'JSR':
                callers[(m.name if inst.operand in m else None, inst.operand)] += 1

    def start_of(name, pc):
        below = [a for a in starts[name] if a <= pc]
        return below[-1] if below else pc

    groups = collections.defaultdict(collections.Counter)
    for category, by_address in machine_uses(mods).items():
        for sites in by_address.values():
            for name, pc, how in sites:
                groups[(name, start_of(name, pc))][category] += 1
    for target, sites in pointer_constants(mods).items():
        for name, pc, pointer in sites:
            groups[(name, start_of(name, pc))][f'pointer to ${target:04x}'] += 1
    resident = {m.name for m in mods if m.kind == 'resident'}
    out = []
    for (name, start), counts in sorted(groups.items()):
        count = callers[(name, start)] + (callers[(None, start)] if name in resident else 0)
        out.append((name, start, count, dict(counts)))
    return out


def write_map(mods, traces, cross):
    """docs/c64-code-map.json: modules, address tables, machine dependencies."""
    symbols = read_symbols()['*']
    tables = analyse.tables
    report = {'modules': [], 'address_tables': [], 'machine': [], 'pointer_constants': [],
              'calls_outside': []}
    for m in mods:
        entry = {'name': m.name, 'sources': m.sources, 'address': f'${m.base:04x}',
                 'length': len(m.data), 'kind': m.kind, 'what': m.what,
                 'sha256': hashlib.sha256(m.data).hexdigest()}
        if m.kind != 'data':
            entry['bytes'] = dict(summary(m, tables))
            entry['entries'] = len(m.entries)
            entry['unreferenced_code'] = [f'${a:04x}' for a, why in sorted(m.entries.items())
                                          if why == 'unreferenced']
            entry['problems'] = [f'${a:04x} {reason}' for a, reason, _ in m.problems]
        report['modules'].append(entry)
    for (name, low, high), targets in sorted(tables.items()):
        report['address_tables'].append({
            'in': name, 'low': f'${low:04x}', 'high': f'${high:04x}',
            'entries': analyse.counts.get((name, low), high - low),
            'targets': [f'${t:04x}' for t in targets]})
    uses = machine_uses(mods)
    for category, first, last, note in MACHINE:
        for address in sorted(a for a in uses[category] if first <= a <= last):
            sites = uses[category][address]
            report['machine'].append({
                'category': category, 'address': f'${address:04x}',
                'name': symbols.get(address, ('', ''))[0],
                'uses': len(sites),
                'by_kind': dict(collections.Counter(how for _, _, how in sites)),
                'sites': [f'{name} ${pc:04x} {how}' for name, pc, how in sites]})
    for target, sites in sorted(pointer_constants(mods).items()):
        report['pointer_constants'].append({
            'target': f'${target:04x}',
            'sites': [f'{name} ${pc:04x} -> ${p:04x}' for name, pc, p in sites]})
    report['machine_routines'] = [
        {'module': name, 'routine': f'${start:04x}',
         'name': (read_symbols()[name].get(start) or symbols.get(start) or ('', ''))[0],
         'callers': count, 'touches': counts}
        for name, start, count, counts in machine_routines(mods, traces)]
    for target in sorted(cross):
        report['calls_outside'].append({
            'target': f'${target:04x}', 'name': symbols.get(target, ('', ''))[0],
            'from': sorted({name for name, _ in cross[target]}), 'sites': len(cross[target])})
    (ROOT / 'docs/c64-code-map.json').write_text(json.dumps(report, indent=1) + '\n')
    return report


def check_areas(mods):
    """Compare the event tables found here with tools/area.py's own reading.

    The two were written separately: area.py pattern-matches the dispatcher,
    this tool follows the code. Returns (files compared, [disagreements]).
    """
    compared, wrong = 0, []
    for m in mods:
        if m.kind != 'area':
            continue
        handlers = {handler for *_, handler in Area(m.data).events()}
        if not handlers:
            continue    # SE on side D has no event tables
        compared += 1
        found = {a for a, why in m.entries.items() if why.startswith('address tables')}
        if handlers != found:
            wrong.append(m.name)
    return compared, wrong


def check_coverage(mods, paths):
    """Compare addresses the host oracle executed (tools/oracle.py --coverage)
    with the static split. Returns [(module, executed, not traced as code)]."""
    by_block = {block: m for m in mods for block in m.blocks}
    executed = collections.defaultdict(set)
    for path in paths:
        for load in json.loads(Path(path).read_text()):
            module = by_block.get((load['side'], hexa(load['block'])))
            if module and hexa(load['address']) == module.base:
                executed[module.name].update(hexa(a) for a in load['executed'])
    by_name = {m.name: m for m in mods}
    return [(name, len(found), sorted(found - set(by_name[name].instructions)))
            for name, found in sorted(executed.items())]


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--rebuild', action='store_true')
    parser.add_argument('-v', '--verbose', action='store_true')
    parser.add_argument('--coverage', nargs='+', metavar='JSON',
                        help='coverage.json files from tools/oracle.py: check them against the split')
    args = parser.parse_args()
    mods, traces, cross = analyse()
    report(mods, traces, cross, args.verbose)
    result = write_map(mods, traces, cross)
    by_category = collections.Counter()
    for row in result['machine']:
        by_category[row['category']] += row['uses']
    print('Machine-specific operands: ' + ', '.join(f'{k} {n}' for k, n in by_category.items()))
    compared, wrong = check_areas(mods)
    if wrong:
        raise SystemExit(f'Event tables disagree with tools/area.py in: {" ".join(wrong)}')
    print(f"OK: {compared} area files' event handlers agree with tools/area.py")
    if any(m.problems for m in mods):
        raise SystemExit('Tracing problems remain; run with -v')
    if args.coverage:
        rows = check_coverage(mods, args.coverage)
        missed = 0
        for name, count, unknown in rows:
            m = next(m for m in mods if m.name == name)
            missed += len(unknown)
            print(f'  {name:10s} executed {count:5d} of {len(m.instructions):5d} traced instructions'
                  + (f'; NOT TRACED: {" ".join(f"${a:04x}" for a in unknown[:12])}' if unknown else ''))
        total = sum(count for _, count, _ in rows)
        if missed:
            raise SystemExit(f'{missed} executed addresses are not instructions in the static split')
        print(f'OK: all {total} executed instruction addresses in {len(rows)} files are code in the static split')
    if args.rebuild:
        built, failures = rebuild(mods, traces, analyse.tables)
        for name, error in failures:
            print(f'FAILED {name}: {error}')
        if failures:
            raise SystemExit(f'{len(failures)} of {built + len(failures)} modules do not rebuild')
        print(f'OK: {built} code modules rebuild byte for byte from source/c64/game/info/*.info')


if __name__ == '__main__':
    main()
