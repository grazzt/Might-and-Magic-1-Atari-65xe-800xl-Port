"""Temporary 64 KB title-scene palette plans, derived from original artwork.

The original title program still draws every frame/scene at runtime. These
packed pixel-role mappings replace its temporary renderer's colour-selection
work, not the game or the original bitmap artwork. All plans are discarded
before loading the game. The independent title checker validates the output.
"""
import colour_policy
import title_check

PLAN_ADDRESS = 0x1400
PLAN_LENGTH = 600


def scenes():
    reference = title_check.reference(ticks=0)
    plans = []
    for scene in title_check.SCENES:
        memory = title_check.prepared(reference['scenes'][scene]['memory'], scene)
        assert colour_policy.panel_edge(memory, 1) == 30, 'Unexpected title panel boundary'
        packed = bytearray()
        registers = [bytearray() for _ in range(4)]
        import build
        for row in range(25):
            chosen, fourth, pairs, _ = colour_policy.select(memory, 1, row)
            for target, colour in zip(registers, chosen+[fourth]):
                target.append(build.ATARI_COLOUR[colour])
            values = []
            for value in memory[0xcc00+row*40:0xcc00+(row+1)*40]:
                values.append(pairs[value >> 4] | (pairs[value & 15] << 2))
            packed.extend(a | b << 4 for a,b in zip(values[::2], values[1::2]))
        plan = b''.join(registers)+packed
        assert len(plan) == PLAN_LENGTH
        plans.append(plan)
    return plans


def nibble_table():
    table = bytearray()
    for mapping in range(16):
        roles = (0,mapping & 3,mapping >> 2,3)
        table.extend(roles[value >> 2] << 2 | roles[value & 3] for value in range(16))
    return bytes(table)
