#!/usr/bin/env python3
"""Build Might and Magic I for Atari 130XE, or the 64 KB profile with --65xe.

  python3 port/atari/build.py [--test [--title] | --no-title] [--65xe] [--disks]

Output in build/atari/:
  mm1.atr       boot sectors (the kernel and boot code, port/atari/src), then
                the four sides of the game as its own loader sees them: 664
                blocks of 256 bytes each, two 128-byte sectors to a block.
  layout.json   label addresses, the patched bytes, the sector layout and the
                parts of the kernel that never change, for the lockstep harness
                and for debugging.

The separate --65xe prototype writes build/atari65xe/: direct grayscale or
warm-colour gameplay, a temporary original title with POKEY music, no in-game
POKEY effects, and literal-byte-checked presentation patches (profile65.py).
Allocation and compatibility notes: docs/65XE.md.

In the default 130XE profile, nothing changes in game files but operands of the
instructions that address the C64's video chip ($D000-$D3FF), sound chip
($D400-$D7FF) and CIAs ($DC00-$DDFF). The first two are Atari hardware too, and
the CIAs' addresses are RAM under the OS ROM, where the kernel is. So each such
operand is pointed at a stand-in register file in RAM (kernel.s, TOP). The list
comes from Phase 1's inventory (tools/disassemble.py) and every site is a
traced instruction.

The disk people play starts with the C64's title program (src/title.s,
docs/TITLE.md): its operands are redirected in the same way, and the boot code
runs it before it loads the game. --no-title leaves it out and the title
program untouched, which is the build the checks of the game use.

The memory the game inherits from the C64's start (zero page, the screen, its
own variables) is taken from the host oracle at the instant the title program
enters the start-up stub, which is where the Atari build enters the game,
with or without the title.

--test builds the kernel so that the key wait takes keys only from the
harness (port/atari/lockstep.py); it has no title either, unless --title asks
for one (lockstep.py --title: the game after the title equals the oracle's).
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'port/atari'))
from c64 import shared_root            # noqa: E402
import c64_screen                       # noqa: E402
import disassemble                      # noqa: E402
import mmdisk                           # noqa: E402
import disks as disks_module            # noqa: E402
import oracle                           # noqa: E402
import c64_sound                        # noqa: E402

OUT = ROOT / 'build/atari'
SOURCE = ROOT / 'port/atari/src'
BOOT_LOAD, BOOT_SECTORS = 0x2200, 56            # up to 7 KB, below the game's $3500
SIDE0 = 1 + BOOT_SECTORS                        # first sector of side A
SECTORS_PER_SIDE = mmdisk.BLOCKS * 2
FAKE_VIC, FAKE_SID, FAKE_CIA = 0xff50, 0xff90, 0xffb0
# The CIA registers the kept code names, in the order of their stand-ins:
# CIA 1's interrupt control, CIA 2's port A and its data direction.
CIA_REGISTERS = [0xdc0d, 0xdd00, 0xdd02]
# What the C64 title program loads before it enters the stub (docs/C64-LOADER.md):
# side, address, length, block.
LOADS = [(0, 0x0b00, 0x14ff, 0x017), (0, 0xa000, 0x292c, 0x03f), (0, 0x8c00, 0x10ef, 0x160),
         (0, 0xc92c, 0x00bc, 0x195), (0, 0xc9e8, 0x0218, 0x190), (0, 0x2000, 0x0200, 0x1a0)]
# What else is in the C64's memory at that instant: leftovers of the title
# program and the cleared lower bitmap. The game may read any of it, and the
# lockstep comparison wants the two machines equal from the start, so the boot
# code loads it from an image after the four sides ("side" 4). The piece under
# the boot code itself is loaded last, by the kernel.
IMAGE_SIDE = 4
IMAGE_PIECES = [(0x3e00, 0x9cff), (0xcc00, 0xcfff)]
# This entire range is zero at stub entry. Recreate it in boot.s rather than
# paying for 63 sector transfers. Assert the captured state on every build.
IMAGE_ZERO = (0xe000, 0xff49)
IMAGE_LAST = (0x2200, 0x3dff)
TABLES_AT = 0x8000          # where the boot code reads the colour tables before moving them
# The title stage (src/title.s). The title program uses $2000-$7F3F for its
# pictures, which includes the boot code's own memory: the boot code is parked
# while the title runs. Both places are free until the game is loaded.
TITLE_AT, TITLE_SIZE = 0x8000, 0x0c00
PARK = 0xa000
TITLE_PROGRAM = (0x4000, 0x0f80)        # side A block 0: address, length
# NTSC C64: the title tune's notes are in tune with this clock (A = 440 Hz).
SID_CLOCK_NTSC = 1022727

# The play screen's colours. The C64 picks three colours for every cell; an
# Atari row has three registers (and a fourth for the command panel). The
# kernel chooses each row's three from what is on it (kernel.s, choose_colours)
# with these two tables: the Atari colour standing in for each C64 colour, and
# how far apart the C64's colours are from one another.
# Nearest colours in Atari800's NTSC palette to VICE's C64 palette, measured
# 2026-10-10; white and the greys are kept neutral and apart from each other.
ATARI_COLOUR = [0x00, 0x0e, 0x4a, 0xbe, 0x7a, 0xdc, 0x88, 0xfe,
                0x3a, 0x28, 0x4c, 0x06, 0x0a, 0xde, 0x9c, 0x0c]


def colour_include():
    """colours.inc: Atari palette and exact symmetric colour distances."""
    palette = c64_screen.PALETTE
    lines = ['atari_colour:', '        .byte ' + ', '.join(f'${v:02X}' for v in ATARI_COLOUR)]
    # Store each symmetric pair once, including the diagonal. An index is
    # distance_base[min(a,b)] + max(a,b); all rounded values survive exactly.
    starts, offset = [], 0
    for a in range(16):
        starts.append(offset - a)
        offset += 16 - a
    lines += ['distance_base:', '        .byte ' + ', '.join(map(str, starts)), 'distance:']
    for a in range(16):
        row = [min(255, round(sum((x - y) ** 2 for x, y in zip(palette[a], palette[b])) ** 0.5 / 1.75))
               for b in range(a, 16)]
        lines.append('        .byte ' + ', '.join(f'{v:3d}' for v in row))
    return '\n'.join(lines) + '\n'


def colour_tables():
    """16 tables of 256 bytes (kernel.s: MAPS).

    A C64 multicolour cell takes pixel pair 01 from the high nibble of its
    screen-matrix byte, 10 from the low nibble and 11 from colour RAM. Table
    number (pair for the high nibble) + 4 * (pair for the low nibble) turns a
    bitmap byte of such a cell into Atari pixel pairs; 11 always stays 11.
    """
    maps = bytearray()
    for index in range(16):
        new = (0, index & 3, index >> 2, 3)
        for byte in range(256):
            out = 0
            for shift in (6, 4, 2, 0):
                out |= new[byte >> shift & 3] << shift
            maps.append(out)
    return bytes(maps)


# From the oracle: boot, leave the title, stop at the stub's first instruction.
TO_STUB = ['until $41ab', 'key 5f', 'until $2000']


def stub_entry():
    """RAM and registers where the C64 enters the start-up stub."""
    player = oracle.Oracle()
    player.play(TO_STUB)
    cpu = player.cpu
    return player.machine.ram_image(), {'a': cpu.a, 'x': cpu.x, 'y': cpu.y, 's': cpu.s, 'p': cpu.p}


def title_program():
    """The C64 title program, as on side A."""
    address, length = TITLE_PROGRAM
    return address, mmdisk.read((ROOT / 'build/c64/original-v2-a/logical.bin').read_bytes(), 0, 0, length)


def title_colours():
    """The three colours every cell of the two title frames has: (matrix byte,
    colour RAM), read from the title program's fill routine at $4215."""
    base, program = title_program()
    fill = program[0x4215 - base:0x422a - base]
    if fill[0] != 0xa9 or fill[19] != 0xa9:
        raise SystemExit('The title program does not fill its colours at $4215 as expected')
    return fill[1], fill[20]


def title_tune():
    """The tune the title program plays: per voice [(frequency, ticks, gate)],
    with the register set-up and the waveform of each voice.

    Read from the player at $4B73-$4C8C: 25 bytes for the SID's registers, a
    waveform byte per voice, then for each voice four bytes a note (frequency
    low and high, length in sixtieths of a second, gate). A zero low byte
    ends a voice and starts all three again.
    """
    base, program = title_program()
    byte = lambda address: program[address - base]
    if [byte(a) for a in (0x4b73, 0x4b77, 0x4ba3, 0x4ba8, 0x4bad, 0x4bb2, 0x4bb7, 0x4bbc)] != [0xa9] * 8:
        raise SystemExit('The title program does not set up its tune at $4B73 as expected')
    table = byte(0x4b74) | byte(0x4b78) << 8
    starts = [byte(0x4ba4 + 10 * v) | byte(0x4ba9 + 10 * v) << 8 for v in range(3)]
    voices = []
    for start in starts:
        notes, at = [], start
        while byte(at):
            notes.append((byte(at) | byte(at + 1) << 8, byte(at + 2), byte(at + 3)))
            at += 4
        voices.append(notes)
    return {'registers': [byte(table + i) for i in range(25)],
            'waveforms': [byte(table + 25 + v) for v in range(3)], 'starts': starts, 'voices': voices}


def title_notes(tune):
    """[(SID frequency, Hz, POKEY 16-bit divider, POKEY 8-bit divider)] for
    every pitch of the tune. Voice 1 gets the joined channels 1+2 at 1.79 MHz
    (period N + 7), voices 2 and 3 a channel each at 64 kHz (period N + 1)."""
    out = []
    for frequency in sorted({f for notes in tune['voices'] for f, _, _ in notes if f >= 0x100}):
        hz = SID_CLOCK_NTSC * frequency / 2 ** 24
        wide = round(c64_sound.POKEY_CLOCK / (2 * hz)) - 7
        narrow = round(c64_sound.POKEY_CLOCK / 28 / (2 * hz)) - 1
        if not (0 <= wide <= 65535 and 0 <= narrow <= 255):
            raise ValueError(f'Title note {frequency:04x} does not fit POKEY')
        out.append((frequency, hz, wide, narrow))
    return out


def stand_in(category, operand):
    """Where an operand that names a C64 chip register points in the Atari build."""
    if category == 'VIC-II':
        return FAKE_VIC + (operand & 0x3f)
    if category == 'SID':
        return FAKE_SID + (operand & 0x1f)
    if operand not in CIA_REGISTERS:
        raise SystemExit(f'CIA register ${operand:04x} has no stand-in (CIA_REGISTERS, and fake_cia in kernel.s)')
    return FAKE_CIA + CIA_REGISTERS.index(operand)


def patches(title=False, xe64=False):
    """[(side, offset in the side image, old byte, new byte, module, pc)]."""
    mods, traces, cross = disassemble.analyse()
    by_name = {m.name: m for m in mods}
    out = []
    uses = disassemble.machine_uses(mods)
    for category in ('VIC-II', 'SID', 'CIA'):
        for sites in uses[category].values():
            for name, pc, how in sites:
                module = by_name[name]
                if name == 'title' and not title:
                    continue
                operand = module.instructions[pc].operand
                new = stand_in(category, operand)
                for side, block in sorted(module.blocks):
                    offset = block * 256 + pc - module.base
                    for i, (old, value) in enumerate(((operand & 255, new & 255), (operand >> 8, new >> 8))):
                        out.append((side, offset + 1 + i, old, value, name, pc))
    if xe64:
        import profile65
        out = [p for p in out if not profile65.borrowed(p[5])]
        out.extend(profile65.patch_list(OUT))
    return sorted(set(out))


def sides(patch_list):
    """The four logical sides with the patches applied."""
    images = {}
    for side in 'ABCD':
        path = ROOT / f'build/c64/original-v2-{side.lower()}/logical.bin'
        if not path.exists():
            raise SystemExit('Run python3 tools/analyze_c64.py and tools/mmdisk.py first')
        images[side] = bytearray(path.read_bytes())
    for side, offset, old, new, name, pc in patch_list:
        if images[side][offset] != old:
            raise SystemExit(f'{name} ${pc:04x}: side {side} does not hold the instruction to patch')
        images[side][offset] = new
    return images


def assemble(test, state, title=False, disks=False, xe64=False, colour65=False):
    """Kernel pieces, the title stage if wanted, then the boot code around
    them. Returns (boot image, labels, image items). disks: the four-disk
    kernel (docs/DISKS.md); the memory image's pieces are then items of disk 1
    (blocks 664 on) for disks.py, not blocks of a fifth side."""
    OUT.mkdir(parents=True, exist_ok=True)
    toolchain = shared_root() / 'tools/toolchain/local/bin'
    run = lambda *args: subprocess.run([str(a) for a in args], check=True)
    ram, registers = state
    first, last = IMAGE_ZERO
    if any(ram[first:last + 1]):
        raise ValueError('Startup zero range changed; restore its image load')
    (OUT / 'zero.bin').write_bytes(ram[0x0000:0x0100])
    (OUT / 'page2.bin').write_bytes(ram[0x028a:0x0292])
    (OUT / 'page3.bin').write_bytes(ram[0x0334:0x0400])
    (OUT / 'low.bin').write_bytes(ram[0x0400:0x0b00])
    config = [f'TEST_MODE = {int(test)}', f'SIDE0 = {SIDE0}', f'BOOT_SECTORS = {BOOT_SECTORS}',
              f'BOOT_LOAD = ${BOOT_LOAD:04X}', f'LOADS = {len(LOADS) + len(IMAGE_PIECES)}', 'TOP_SIZE = $B0',
              f'TABLES_AT = ${TABLES_AT:04X}', f'TITLE = {int(title)}', f'TITLE_AT = ${TITLE_AT:04X}',
              f'PARK = ${PARK:04X}', f'DISKS = {int(disks)}', f'INDEX_SECTOR = {disks_module.INDEX_SECTOR}',
              f'XE64 = {int(xe64)}', f'PF0_65 = ${0x24 if colour65 else 4:02X}',
              f'PF1_65 = ${0x28 if colour65 else 8:02X}']
    config += [f'START_{k.upper()} = ${v:02X}' for k, v in registers.items()]
    if title:
        matrix, colour_ram = title_colours()
        start = json.loads((oracle.START / 'entry.json').read_text())
        config += [f'TITLE_LENGTH = ${TITLE_PROGRAM[1]:04X}', f'TITLE_PF0 = ${ATARI_COLOUR[matrix >> 4]:02X}',
                   f'TITLE_PF1 = ${ATARI_COLOUR[matrix & 15]:02X}', f'TITLE_PF2 = ${ATARI_COLOUR[colour_ram & 15]:02X}']
        config += [f'TITLE_{k.upper()} = ${start[k]:02X}' for k in 'axysp']
    (OUT / 'config.inc').write_text('\n'.join(config) + '\n')
    (OUT / 'colours.inc').write_text(colour_include())
    effects = c64_sound.decode(ram)
    frequencies = c64_sound.pitches(effects)
    dividers = [c64_sound.divisor(f) for f in frequencies]
    if len(frequencies) > 255 or any(not 0 <= d <= 65535 for d in dividers):
        raise ValueError('Sound pitch table does not fit POKEY')
    def byte_table(name, values):
        return name + ': .byte ' + ', '.join(f'${v:02X}' for v in values) + '\n'
    (OUT / 'sound-pitches.inc').write_text(
        f'SOUND_NOTES = {len(frequencies)}\n'
        + byte_table('sound_freq_low', [f & 255 for f in frequencies])
        + byte_table('sound_freq_high', [f >> 8 for f in frequencies])
        + byte_table('sound_div_low', [d & 255 for d in dividers])
        + byte_table('sound_div_high', [d >> 8 for d in dividers]))
    # Linear 8-bit envelope approximation, one update per NTSC VBI. SID's
    # exponential decay and pulse/triangle/saw timbres are presentation differences.
    attack_ms = [2, 8, 16, 24, 38, 56, 68, 80, 100, 250, 500, 800, 1000, 3000, 5000, 8000]
    release_ms = [6, 24, 48, 72, 114, 168, 204, 240, 300, 750, 1500, 2400, 3000, 9000, 15000, 24000]
    rate = lambda ms: max(1, min(240, round(240 * 1000 / (60 * ms))))
    (OUT / 'sound-envelope.inc').write_text(
        byte_table('sound_attack_step', [rate(ms) for ms in attack_ms])
        + byte_table('sound_release_step', [rate(ms) for ms in release_ms]))
    (OUT / 'kernel.cfg').write_text('''MEMORY {
    LOADER: start = $9D00, size = $0300, file = "%s/loader.bin", fill = yes;
    UNDER:  start = $DC00, size = $0400, file = "%s/under.bin", fill = yes;
    TOP:    start = $FF50, size = $00B0, file = "%s/top.bin", fill = yes;
    EXT:    start = $6800, size = $0400, file = "%s/ext.bin", fill = yes;
    EXT2:   start = $7C00, size = $0400, file = "%s/ext2.bin", fill = yes;
}
SEGMENTS {
    LOADER: load = LOADER, type = rw;
    UNDER:  load = UNDER, type = rw;
    TOP:    load = TOP, type = rw;
    EXT:    load = EXT, type = rw;
    EXT2:   load = EXT2, type = rw;
}
''' % ((OUT,) * 5))
    if xe64:
        config_path = OUT / 'kernel.cfg'
        config = ''.join(line for line in config_path.read_text().splitlines(keepends=True)
                         if not line.lstrip().startswith(('EXT:', 'EXT2:')))
        config = config.replace('MEMORY {\n', 'MEMORY {\n' + ''.join(
            f'    {name}: start = ${base:04X}, size = ${size:04X}, file = "{OUT/file}", fill = yes;\n'
            for name, base, size, file in (('FLIP65',0x1c13,5,'flip65.bin'),('COPYCOLOUR65',0x0e1f,24,'copycolour65.bin'),
                                           ('COLOUR65',0x1c18,18,'colour65.bin'),
                                           ('PLAY65',0xc276,58,'play65.bin'),('BANK65',0xc40d,23,'bank65.bin'),
                                           ('WAIT65',0x0e37,4,'wait65.bin'),('PAUSE65',0xa036,3,'pause65.bin'),
                                           ('DELAY65',0xb233,3,'delay65.bin'),('WAITSPY65',0xc91a,18,'waitspy65.bin'))))
        config = config.replace('SEGMENTS {\n', 'SEGMENTS {\n' + ''.join(
            f'    {name}: load = {name}, type = rw;\n' for name in ('FLIP65','COPYCOLOUR65','COLOUR65','PLAY65','BANK65','WAIT65','PAUSE65','DELAY65','WAITSPY65')))
        config_path.write_text(config)
    run(toolchain / 'ca65', '-g', '-I', OUT, SOURCE / 'kernel.s', '-o', OUT / 'kernel.o')
    run(toolchain / 'ld65', '-C', OUT / 'kernel.cfg', '-Ln', OUT / 'kernel.lbl', OUT / 'kernel.o')
    labels = {}
    for line in (OUT / 'kernel.lbl').read_text().splitlines():
        _, address, name = line.split()
        if not name.startswith('.@') and not name.startswith('.__'):
            labels[name.lstrip('.')] = int(address, 16)
    (OUT / 'kernel.inc').write_text(''.join(f'{name} = ${address:04X}\n' for name, address in sorted(labels.items())))
    # The image "side": first what goes into the extended bank at $6C00 (the 16
    # colour tables, then the kernel's EXT2 segment), then the pieces of memory,
    # then the title stage.
    tables = b'' if xe64 else colour_tables() + (OUT / 'ext2.bin').read_bytes()
    image = bytearray(tables)
    items = []          # disks: (address, data) of each piece, block IMAGE_BLOCK + its number
    if disks:
        if tables:
            items.append((TABLES_AT, tables))
        tables_load = (IMAGE_SIDE, TABLES_AT, len(tables), disks_module.IMAGE_BLOCK)
        loads, block = list(LOADS), disks_module.IMAGE_BLOCK + int(bool(tables))
        for first, last in IMAGE_PIECES + [IMAGE_LAST]:
            loads.append((IMAGE_SIDE, first, last - first + 1, block))
            items.append((first, ram[first:last + 1]))
            block += 1
    else:
        tables_load = (IMAGE_SIDE, TABLES_AT, len(tables), 0)
        loads, block = list(LOADS), len(image) // 256
        for first, last in IMAGE_PIECES + [IMAGE_LAST]:
            loads.append((IMAGE_SIDE, first, last - first + 1, block))
            image += ram[first:last + 1]
            image += bytes(-len(image) % 256)
            block = len(image) // 256
    entry = lambda side, address, length, block: (
        f'        .byte {side}\n        .word ${address:04X}, ${length:04X}\n        .byte 0\n        .word ${block:04X}\n')
    table = (''.join(entry(*load) for load in loads[:-1]) + 'last_load:\n' + entry(*loads[-1])
             + 'tables_load:\n' + entry(*tables_load))
    if title:
        notes = title_notes(title_tune())
        (OUT / 'title-music.inc').write_text(
            f'TITLE_NOTES = {len(notes)}\n'
            + byte_table('note_low', [n[0] & 255 for n in notes])
            + byte_table('note_high', [n[0] >> 8 for n in notes])
            + byte_table('note_wide_low', [n[2] & 255 for n in notes])
            + byte_table('note_wide_high', [n[2] >> 8 for n in notes])
            + byte_table('note_narrow', [n[3] for n in notes]))
        (OUT / 'title.cfg').write_text(
            f'MEMORY {{ TITLE: start = ${TITLE_AT:04X}, size = ${TITLE_SIZE:04X}, file = %O; }}\n'
            'SEGMENTS { TITLE: load = TITLE, type = rw; }\n')
        if xe64:
            import title65
            plan_blocks = []
            for plan in title65.scenes():
                plan_blocks.append(block)
                if disks:
                    items.append((title65.PLAN_ADDRESS, plan))
                    block += 1
                else:
                    image += plan
                    image += bytes(-len(image) % 256)
                    block = len(image)//256
            (OUT/'title65-plans.inc').write_text(
                f'TITLE_PLAN_SIDE = {IMAGE_SIDE}\nplan_blocks: .word '
                + ','.join(f'${v:04X}' for v in plan_blocks)+'\n')
            (OUT/'title65-nibbles.bin').write_bytes(title65.nibble_table())
        title_source = SOURCE / ('title65.s' if xe64 else 'title.s')
        run(toolchain / 'ca65', '-g', '-I', OUT, '--bin-include-dir', OUT, title_source, '-o', OUT / 'title.o')
        run(toolchain / 'ld65', '-C', OUT / 'title.cfg', '-Ln', OUT / 'title.lbl', '-o', OUT / 'title.bin',
            OUT / 'title.o')
        for line in (OUT / 'title.lbl').read_text().splitlines():
            _, address, name = line.split()
            if not name.startswith('.@') and not name.startswith('.__'):
                labels['title.' + name.lstrip('.')] = int(address, 16)
        stage = (OUT / 'title.bin').read_bytes()
        table += 'title_load:\n' + entry(IMAGE_SIDE, TITLE_AT, len(stage), block)
        if disks:
            items.append((TITLE_AT, stage))
        image += stage
        image += bytes(-len(image) % 256)
    (OUT / 'loads.inc').write_text(table)
    (OUT / 'image.bin').write_bytes(image)
    size = BOOT_SECTORS * 128
    (OUT / 'boot.cfg').write_text(
        f'MEMORY {{ BOOT: start = ${BOOT_LOAD:04X}, size = ${size:04X}, file = %O, fill = yes; }}\n'
        'SEGMENTS { BOOT: load = BOOT, type = rw; }\n')
    run(toolchain / 'ca65', '-I', OUT, '--bin-include-dir', OUT, SOURCE / 'boot.s', '-o', OUT / 'boot.o')
    run(toolchain / 'ld65', '-C', OUT / 'boot.cfg', '-o', OUT / 'boot.bin', OUT / 'boot.o')
    return (OUT / 'boot.bin').read_bytes(), labels, items


# The kernel's segments in main memory, as assembled: file and address.
SEGMENTS = {'loader.bin': 0x9d00, 'under.bin': 0xdc00, 'top.bin': 0xff50}


def fixed(labels):
    """The kernel's code and constant tables in main memory: what must still be
    as assembled whenever the game is looked at (lockstep.py, kernel_changes).
    Variables lie between the pieces; `target` is an operand the disk code
    writes. lockstep.py --kernel-writes shows what does change in a run."""
    if 'lz_at' in labels:       # the four-disk kernel: variables, then code with one operand it rewrites
        pieces = [('loader.bin', labels['set_bank'], labels['lz_left'] - 1),
                  ('loader.bin', labels['disk_write'], labels['lz_at'] - 1),
                  ('loader.bin', labels['lz_at'] + 2, labels['dcb'] - 1)]
    else:
        pieces = [('loader.bin', labels['set_bank'], labels['remain'] - 1),
                  ('loader.bin', labels['disk_write'], labels['target'] - 1),
                  ('loader.bin', labels['target'] + 2, labels['dcb'] - 1)]
    if 'display_start' in labels:
        pieces += [
            ('loader.bin', labels['font_start'], labels['font_source']-1),
            ('loader.bin', labels['font_source']+2, labels['font_end']-1),
            ('under.bin', labels['nmi'], labels['display_start']-1),
            ('under.bin', labels['display_start'], labels['display_end']-1),
            ('top.bin', labels['mode_resume'], labels['mode_resume_end']-1),
            ('top.bin', labels['text_list'], labels['rom_high_end']-1),
            ('top.bin', 0xffe4, 0xffff),
            ('colour65.bin', labels['colour65_start'], labels['colour65_end']-1),
            ('play65.bin', labels['play65_start'], labels['play65_end']-1),
            ('bank65.bin', labels['bank65_start'], labels['bank65_end']-1),
        ]
        pieces += [(name, SEGMENTS[name], SEGMENTS[name]+(OUT/name).stat().st_size-1)
                   for name in ('wait65.bin','pause65.bin','delay65.bin','waitspy65.bin','flip65.bin','copycolour65.bin')]
        return [{'file': name, 'base': f'${SEGMENTS[name]:04x}',
                 'first': f'${first:04x}', 'last': f'${last:04x}'}
                for name, first, last in pieces]
    pieces += [
              ('loader.bin', labels['sound_freq_low'], labels['sound_pitches_end'] - 1),
              ('under.bin', labels['nmi'], labels['row_pf0'] - 1),
              ('top.bin', labels['sound_attack_step'], labels['idempotent_end'] - 1),
              ('top.bin', 0xffe4, 0xffe6),
              ('top.bin', labels['sound_state_end'], 0xffff)]
    return [{'file': name, 'base': f'${SEGMENTS[name]:04x}', 'first': f'${first:04x}', 'last': f'${last:04x}'}
            for name, first, last in pieces]


def select_profile(xe64):
    """Keep profile artifacts apart; existing harnesses consume these paths."""
    global OUT, DISKS_OUT, SEGMENTS
    OUT = ROOT / ('build/atari65xe' if xe64 else 'build/atari')
    DISKS_OUT = OUT / 'disks'
    SEGMENTS = {'loader.bin': 0x9d00, 'under.bin': 0xdc00, 'top.bin': 0xff50}
    if xe64:
        SEGMENTS.update({'flip65.bin':0x1c13,'copycolour65.bin':0x0e1f,'colour65.bin':0x1c18, 'play65.bin':0xc276, 'bank65.bin':0xc40d,
                         'wait65.bin':0x0e37,'pause65.bin':0xa036,'delay65.bin':0xb233,'waitspy65.bin':0xc91a})


def build(test=False, title=False, xe64=False, colour65=False):
    """Build the disk. title: start with the C64's title program."""
    select_profile(xe64)
    state = stub_entry()
    boot, labels, _ = assemble(test, state, title, xe64=xe64, colour65=colour65)
    for name, address in (('fake_vic', FAKE_VIC), ('fake_sid', FAKE_SID), ('fake_cia', FAKE_CIA)):
        if labels[name] != address:
            raise SystemExit(f'kernel.s has {name} at ${labels[name]:04x}; build.py expects ${address:04x}')
    patch_list = patches(title, xe64=xe64)
    images = sides(patch_list)
    disk = boot + b''.join(bytes(images[side]) for side in 'ABCD') + (OUT / 'image.bin').read_bytes()
    paragraphs = len(disk) // 16
    header = bytes([0x96, 0x02, paragraphs & 255, paragraphs >> 8 & 255, 128, 0, paragraphs >> 16]) + bytes(9)
    (OUT / 'mm1.atr').write_bytes(header + disk)
    layout = {'test_mode': test, 'title': title, 'boot_sectors': BOOT_SECTORS, 'side0_sector': SIDE0,
              'sectors_per_side': SECTORS_PER_SIDE, 'labels': {k: f'${v:04x}' for k, v in sorted(labels.items())},
              'fake_vic': f'${FAKE_VIC:04x}', 'fake_sid': f'${FAKE_SID:04x}', 'fake_cia': f'${FAKE_CIA:04x}',
              'fixed': fixed(labels),
              'patches': [{'side': side, 'offset': offset, 'old': old, 'new': new, 'module': name, 'pc': f'${pc:04x}'}
                          for side, offset, old, new, name, pc in patch_list]}
    if xe64:
        layout.update(ram_kb=64, target='65xe', palette65=[0,0x24,0x28,14] if colour65 else [0,4,8,14], presentation_ranges=[
            {'first': '$cc00', 'last': '$cfff', 'reason': '65XE crossing rows / reordered text font'},
            {'first': '$028e', 'last': '$028e',
             'reason': 'released CTRL input: Atari keyboard key-up / C64 KERNAL IRQ; checked zero natively'}])
        import profile65
        layout['memory65'] = profile65.allocation(layout, OUT, SEGMENTS)
    (OUT / 'layout.json').write_text(json.dumps(layout, indent=1) + '\n')
    return layout


DISKS_OUT = OUT / 'disks'


def build_disks(test=False, title=False, xe64=False, colour65=False):
    """The four disks (docs/DISKS.md): build/atari/disks/mm1-disk1.atr to -disk4.atr.
    Disk 1 boots; the game asks for the others with its own INSERT DISK prompt.
    Returns the layout, which says where every item is."""
    select_profile(xe64)
    state = stub_entry()
    boot, labels, image_items = assemble(test, state, title, disks=True, xe64=xe64, colour65=colour65)
    for name, address in (('fake_vic', FAKE_VIC), ('fake_sid', FAKE_SID), ('fake_cia', FAKE_CIA)):
        if labels[name] != address:
            raise SystemExit(f'kernel.s has {name} at ${labels[name]:04x}; build.py expects ${address:04x}')
    patch_list = patches(title, xe64=xe64)
    images = sides(patch_list)
    info = json.loads((ROOT / 'docs/c64-logical-disk.json').read_text())
    DISKS_OUT.mkdir(parents=True, exist_ok=True)
    report = []
    for number, side in enumerate(disks_module.SIDES):
        disk = disks_module.Disk(f'disk {number + 1} (side {side})')
        if side == 'A':
            disks_module.boot_items(disk, bytes(images['A']), info[0])
            for k, (address, data) in enumerate(image_items):
                disk.add(disks_module.IMAGE_BLOCK + k, data, name=f'image piece {k} to ${address:04x}')
        else:
            disks_module.side_items(disk, bytes(images[side]), info[number])
        body, used = disks_module.pack(disk, reserved=BOOT_SECTORS if side == 'A' else 0)
        if side == 'A':
            body[:BOOT_SECTORS * 128] = boot
        path = DISKS_OUT / f'mm1-disk{number + 1}.atr'
        path.write_bytes(disks_module.atr(body))
        report.append({'disk': number + 1, 'side': side, 'path': str(path), 'sectors': used['sectors'],
                       'packed': used['packed'], 'stored': used['stored'],
                       'items': {f'${block:03x}': {k: v for k, v in item.items() if k != 'data'} | {'length': len(item['data'])}
                                 for block, item in sorted(disk.items.items())}})
    layout = {'test_mode': test, 'title': title, 'disks': report, 'boot_sectors': BOOT_SECTORS,
              'index_sector': disks_module.INDEX_SECTOR, 'labels': {k: f'${v:04x}' for k, v in sorted(labels.items())},
              'fake_vic': f'${FAKE_VIC:04x}', 'fake_sid': f'${FAKE_SID:04x}', 'fake_cia': f'${FAKE_CIA:04x}',
              'fixed': fixed(labels),
              'patches': [{'side': side, 'offset': offset, 'old': old, 'new': new, 'module': name, 'pc': f'${pc:04x}'}
                          for side, offset, old, new, name, pc in patch_list]}
    if xe64:
        layout.update(ram_kb=64, target='65xe', palette65=[0,0x24,0x28,14] if colour65 else [0,4,8,14], presentation_ranges=[
            {'first': '$cc00', 'last': '$cfff', 'reason': '65XE crossing rows / reordered text font'},
            {'first': '$028e', 'last': '$028e',
             'reason': 'released CTRL input: Atari keyboard key-up / C64 KERNAL IRQ; checked zero natively'}])
        import profile65
        layout['memory65'] = profile65.allocation(layout, OUT, SEGMENTS)
    (OUT / 'layout-disks.json').write_text(json.dumps(layout, indent=1) + '\n')
    return layout


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--test', action='store_true')
    parser.add_argument('--no-title', action='store_true', help='start at the game, as the checks do')
    parser.add_argument('--title', action='store_true', help='with --test: start with the title all the same')
    parser.add_argument('--disks', action='store_true',
                        help='four 130 KB disk images (build/atari/disks/) instead of one big one (docs/DISKS.md)')
    parser.add_argument('--65xe', dest='xe64', action='store_true', help='64 KB direct display (separate build/atari65xe/)')
    parser.add_argument('--colour', action='store_true', help='with --65xe: fixed warm graphics palette (same RAM budget)')
    args = parser.parse_args()
    if args.colour and not args.xe64:
        parser.error('--colour requires --65xe')
    title = args.title or not (args.test or args.no_title)
    if args.disks:
        layout = build_disks(args.test, title=title, xe64=args.xe64, colour65=args.colour)
        for disk in layout['disks']:
            print(f"{disk['path']}: side {disk['side']}, {disk['sectors']} of {disks_module.INDEX_SECTOR - 1} sectors "
                  f"({disk['packed']} packed items, {disk['stored']} stored)")
        return
    layout = build(args.test, title=title, xe64=args.xe64, colour65=args.colour)
    sites = len({(p['module'], p['pc']) for p in layout['patches']})
    print(f"{OUT}/mm1.atr: {layout['boot_sectors']} boot sectors, 4 sides of {SECTORS_PER_SIDE} sectors; "
          f"{sites} patch sites ({len(layout['patches'])} bytes on disk)")


if __name__ == '__main__':
    main()
