#!/usr/bin/env python3
"""Display experiment: show the C64 game screen on an Atari without converting
the bitmap's layout.

The game keeps its screen as a C64 multicolour bitmap: 40 cells of 8 bytes per
character row, two bits per pixel. ANTIC mode 4 draws characters that are
exactly such cells, so a row of the bitmap can serve as that row's character
set. This script takes a screen from the host oracle, re-codes its pixels for
the Atari's colour registers (the C64 picks three colours per cell, the Atari
three per row plus a fourth for marked cells), builds a boot disk around
src/display_demo.s and photographs the result in Atari800.

  python3 port/atari/display_demo.py [SCRIPT [MARK]]

Output in build/atari/: display-demo.atr, display-demo.png (Atari800) and
display-demo-c64.png (the same screen as the C64 shows it).
"""
import collections
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from c64 import shared_root            # noqa: E402
import c64_screen                       # noqa: E402
import oracle                           # noqa: E402

OUT = ROOT / 'build/atari'
LOAD, BUFFER = 0x3000, 0x4000
ROWS, PANEL_COLUMN, VIEW_ROWS = 25, 30, 16
# Atari colour register values (hue, luminance) standing in for the C64's sixteen.
ATARI = [0x00, 0x0e, 0x34, 0xac, 0x56, 0xc6, 0x84, 0x1e, 0x26, 0xf2, 0x3a, 0x04, 0x08, 0xca, 0x8a, 0x0c]


def row_address(row):
    """Three rows to a 1 KB block, so that no row crosses a character-set boundary."""
    return BUFFER + row // 3 * 0x400 + row % 3 * 320


def distance(a, b):
    return sum((x - y) ** 2 for x, y in zip(c64_screen.PALETTE[a], c64_screen.PALETTE[b]))


def convert(rows):
    """C64 colour numbers (200 x 320) -> (cells, palettes, marked).

    cells[row][column] is 8 bytes of Atari pixel pairs; palettes[row] the four
    colour numbers for pairs 01, 10, 11 and for 11 in a marked cell; marked
    cells are the command panel beside the view, drawn in one colour.
    """
    cells, palettes = [], []
    for row in range(ROWS):
        panel = row < VIEW_ROWS
        count, panel_count = collections.Counter(), collections.Counter()
        for y in range(row * 8, row * 8 + 8):
            for x in range(0, 320, 2):
                colour = rows[y][x]
                if colour:
                    (panel_count if panel and x >= PANEL_COLUMN * 8 else count)[colour] += 1
        chosen = [c for c, _ in count.most_common(3)]
        chosen += [chosen[-1] if chosen else 1] * (3 - len(chosen))
        fourth = panel_count.most_common(1)[0][0] if panel_count else chosen[2]
        palettes.append(chosen + [fourth])
        line = []
        for column in range(40):
            marked = panel and column >= PANEL_COLUMN
            data = bytearray()
            for y in range(row * 8, row * 8 + 8):
                byte = 0
                for pair in range(4):
                    colour = rows[y][column * 8 + pair * 2]
                    if colour == 0:
                        value = 0
                    elif marked:
                        value = 3
                    else:
                        value = 1 + min(range(3), key=lambda i: distance(colour, chosen[i]))
                    byte = byte << 2 | value
                data.append(byte)
            line.append(bytes(data))
        cells.append(line)
    return cells, palettes


def tables(palettes, sectors):
    def table(name, values):
        return f'{name}:\n' + ''.join(
            '        .byte ' + ', '.join(f'${v:02X}' for v in values[i:i + 8]) + '\n'
            for i in range(0, len(values), 8))
    lines = [f'SECTORS = {sectors}', '']
    lines.append(table('chbase_table', [row_address(r) >> 8 & 0xfc for r in range(ROWS)]))
    for i, name in enumerate(('pf0_table', 'pf1_table', 'pf2_table', 'pf3_table')):
        lines.append(table(name, [ATARI[p[i]] for p in palettes]))
    lines.append(table('row0_colours', [ATARI[c] for c in palettes[0]]))
    # Character codes: a row's 40 cells start at code 0, 40 or 80 of its block.
    # The second set marks the panel columns (bit 7: colour register 3).
    for name, mark in (('codes_plain', 0), ('codes_panel', 0x80)):
        codes = [(r * 40 + c) | (mark if c >= PANEL_COLUMN else 0) for r in range(3) for c in range(40)]
        lines.append(table(name, codes))
    dlist = ['dlist:', '        .byte $70, $70          ; 16 blank lines: 25 rows need the room']
    for row in range(ROWS):
        source = 'codes_panel' if row < VIEW_ROWS else 'codes_plain'
        interrupt = '$C4' if row < ROWS - 1 else '$44'      # mode 4, load address, interrupt
        dlist.append(f'        .byte {interrupt}\n        .word {source} + {row % 3 * 40}')
    dlist += ['        .byte $41', '        .word dlist']
    return '\n'.join(lines + dlist) + '\n'


def build(script, mark):
    OUT.mkdir(parents=True, exist_ok=True)
    player = oracle.Oracle()
    found = {}
    player.play((ROOT / f'tools/traces/{script}.txt').read_text().splitlines(),
                on_mark=lambda name: found.__setitem__(name, player.picture()))
    rows = found[mark]
    c64_screen.write_png(OUT / 'display-demo-c64.png', rows)
    cells, palettes = convert(rows)
    picture = bytearray(9 * 0x400)
    for row in range(ROWS):
        offset = row_address(row) - BUFFER
        picture[offset:offset + 320] = b''.join(cells[row])
    size = BUFFER - LOAD + len(picture)
    sectors = (size + 127) // 128
    (OUT / 'tables.inc').write_text(tables(palettes, sectors))
    toolchain = shared_root() / 'tools/toolchain/local/bin'
    source = ROOT / 'port/atari/src/display_demo.s'
    (OUT / 'demo.cfg').write_text(
        f'MEMORY {{ MAIN: start = ${LOAD:04X}, size = ${BUFFER - LOAD:04X}, file = %O, fill = yes; }}\n'
        'SEGMENTS { CODE: load = MAIN, type = rw; }\n')
    subprocess.run([toolchain / 'ca65', '-I', OUT, source, '-o', OUT / 'demo.o'], check=True)
    subprocess.run([toolchain / 'ld65', '-C', OUT / 'demo.cfg', '-o', OUT / 'demo.bin', OUT / 'demo.o'], check=True)
    image = (OUT / 'demo.bin').read_bytes() + bytes(picture)
    image += bytes(sectors * 128 - len(image))
    disk = image + bytes(720 * 128 - len(image))
    header = bytes([0x96, 0x02, len(disk) // 16 & 255, len(disk) // 16 >> 8, 128, 0]) + bytes(10)
    (OUT / 'display-demo.atr').write_bytes(header + disk)
    return palettes


def photograph():
    sys.path.insert(0, str(shared_root() / 'port/atari'))
    from harness import Atari          # the sibling project's libatari800 wrapper
    atari = Atari(OUT / 'display-demo.atr')
    atari.frame(200)
    atari.screenshot(OUT / 'display-demo.png')
    return atari


def main():
    script = sys.argv[1] if len(sys.argv) > 1 else 'boot-to-outdoors'
    mark = sys.argv[2] if len(sys.argv) > 2 else 'town'
    palettes = build(script, mark)
    photograph()
    print(f'{OUT}/display-demo.png; row palettes (C64 colour numbers): {palettes[0]} ... {palettes[-1]}')


if __name__ == '__main__':
    main()
