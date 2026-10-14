"""Independent host reference for row colour selection and full conversion.

The production selector is 6502 assembly. This model enumerates actual pixel
pairs directly and never reads the assembly's lookup/distance/cache tables.
"""
from collections import Counter
from math import dist

import c64_screen


def distance(a, b):
    return min(255, round(dist(c64_screen.PALETTE[a], c64_screen.PALETTE[b]) / 1.75))


def addresses(mode, row):
    upper = mode == 2 and row < 16
    return ((0x2000 if upper else 0xe000) + row * 320,
            (0x400 if upper else 0xcc00) + row * 40, 0xd800 + row * 40)


def panel_edge(memory, mode, corrected=True):
    # EN $2742 paints 18 blue colour-RAM cells from $D816. Mode 1 also
    # occurs at ordinary doors, where the command panel still starts at 30.
    return 22 if corrected and mode == 1 and memory[0xd816] & 15 == 14 else 30


def select(memory, mode, row, corrected=True, inputs=None):
    source, matrix, cram = addresses(mode, row) if inputs is None else inputs
    edge = panel_edge(memory, mode, corrected)
    used, ram, panel = Counter(), Counter(), Counter()
    for col in range(40):
        value = memory[matrix + col]
        colours = (value >> 4, value & 15)
        if corrected and mode == 1 and edge == 22 and row < 16:
            present = {byte >> shift & 3 for byte in memory[source + col*8:source + col*8 + 8]
                       for shift in (6, 4, 2, 0)}
            for pair, colour in enumerate(colours, 1):
                if pair in present:
                    used[colour] += 1
        else:
            used.update(colours)
        ((panel if row < 16 and col >= edge else ram))[memory[cram + col] & 15] += 1
    common = lambda counts, fallback: max(counts, key=lambda c: (counts[c], c)) if counts else fallback
    third = common(ram, 1)
    fourth = common(panel, third)
    used.pop(0, None)
    used.pop(third, None)
    chosen = []
    for _ in range(2):
        colour = common(used, third)
        chosen.append(colour)
        used.pop(colour, None)
    chosen.append(third)
    mapping = [min(range(4), key=lambda p: distance(c, ([0]+chosen)[p])) for c in range(16)]
    return chosen, fourth, mapping, edge


def convert(memory, mode, corrected=True):
    """8000 encoded bytes, 100 register bytes, and per-row logical palettes."""
    encoded, registers, palettes = bytearray(), [bytearray() for _ in range(4)], []
    # Register values are generated independently by the build's measured
    # Atari/C64 palette mapping; callers compare logical selections separately.
    import build
    for row in range(25):
        source, matrix, _ = addresses(mode, row)
        chosen, panel, pairs, edge = select(memory, mode, row, corrected)
        palettes.append(chosen + [panel])
        for i, colour in enumerate(chosen+[panel]):
            registers[i].append(build.ATARI_COLOUR[colour])
        for col in range(40):
            value = memory[matrix+col]
            mapping = (0, pairs[value >> 4], pairs[value & 15], 3)
            for byte in memory[source+col*8:source+col*8+8]:
                out = 0
                for shift in (6,4,2,0):
                    out |= mapping[byte >> shift & 3] << shift
                encoded.append(out)
    return bytes(encoded), b''.join(registers), palettes


def picture(encoded, palettes, edge=30):
    rows = [bytearray(320) for _ in range(200)]
    for row in range(25):
        colours = [0]+palettes[row][:3]
        for col in range(40):
            for line in range(8):
                byte = encoded[row*320+col*8+line]
                for pair in range(4):
                    value = byte >> (6-pair*2) & 3
                    colour = palettes[row][3] if value==3 and row<16 and col>=edge else colours[value]
                    x=col*8+pair*2
                    rows[row*8+line][x:x+2] = bytes([colour])*2
    return rows
