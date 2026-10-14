#!/usr/bin/env python3
"""Read a C64 area file: movement grid, event squares and walking routes.

An area file loads at $8200 (docs/C64-RUNTIME.md): a 16x16 grid of wall bytes,
a 16x16 state grid, 50 data bytes, then 6502 code. That code looks the party's
square up in a table and calls the square's handler when the facing matches.
Squares are (x, y) with 0,0 in the south-west corner.

Areas are named by two characters and a disk side. A handler leaves for
another area with LDA #first / LDX #second / LDY #side / JMP $0B78, where a
character code below 26 is a letter and 26 up is a digit. The data bytes hold
the four neighbouring areas (north, east, south, west) that an outdoor sector's
open edges lead to; an area that names itself has no neighbour that way.

  python3 tools/area.py FILE                    list the event squares
  python3 tools/area.py FILE X Y FACING X Y [FACING]   keys for a route
  python3 tools/area.py --world                 rewrite docs/c64-areas.json
"""
import argparse
from collections import deque
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]

BASE = 0x8200
# Facing, dx, dy, bit that blocks leaving the square that way, facing mask.
DIRECTIONS = [('N', 0, 1, 0x40, 0xc0), ('E', 1, 0, 0x10, 0x30),
              ('S', 0, -1, 0x04, 0x0c), ('W', -1, 0, 0x01, 0x03)]
TURNS = {0: '', 1: 'L', 2: 'LL', 3: 'J'}  # L turns right, J left


def area_name(first, second):
    """The file name the loader builds from an exit's two character codes."""
    char = lambda code: chr(0x30 + code - 26) if code >= 26 else chr(0x41 + code)
    return char(first) + char(second)


class Area:
    def __init__(self, data):
        self.data = data
        self.walls, self.states = data[:256], data[256:512]

    def neighbours(self):
        """[(name, side)] for north, east, south, west, from data bytes 8-19."""
        field = self.data[0x208:0x214]
        return [(area_name(field[i], field[i + 1]), 'ABCD'[field[i + 2] & 3])
                for i in range(0, 12, 3)]

    def exits(self):
        """[(name, side, (x, y, facings) or None)]: where handlers leave to."""
        events = self.events()
        out = []
        for m in re.finditer(rb'\xa9(.)\xa2(.)\xa0(.)\x4c\x78\x0b', self.data, re.S):
            address = BASE + m.start()
            owner = max((e for e in events if e[3] <= address), key=lambda e: e[3], default=None)
            out.append((area_name(m.group(1)[0], m.group(2)[0]), 'ABCD'[m.group(3)[0] & 3],
                        owner[:3] if owner else None))
        return out

    def events(self):
        """[(x, y, facings, handler address)] from the dispatcher's tables.

        One file (SE on side D) has other code at $8432 and yields no events.
        """
        code = self.data[0x232:0x332]  # the no-event path can be long (0L)
        if code[:5] != bytes([0xa5, 0x3d, 0xa2, 0x00, 0xdd]):
            return []
        word = lambda b: (b[0] | b[1] << 8) - BASE
        cells = word(code[5:7])
        masks = word(re.search(rb'\xa5\x40\x3d(..)', code, re.S).group(1))
        low, high = (word(m) for m in re.findall(rb'\xbd(..)\x8d', code, re.S)[:2])
        out = []
        for i in range(masks - cells):
            cell, mask = self.data[cells + i], self.data[masks + i]
            facings = ''.join(d[0] for d in DIRECTIONS if mask & d[4])
            out.append((cell % 16, cell // 16, facings,
                        self.data[low + i] | self.data[high + i] << 8))
        return out

    def handler(self, address):
        """Bytes of a handler, up to the next handler or the end of the file."""
        starts = sorted({h for *_, h in self.events()})
        later = [s for s in starts if s > address]
        return self.data[address - BASE:(later[0] if later else BASE + len(self.data)) - BASE]

    def route(self, start, facing, goal, final=None, avoid=()):
        """Keys (I forward, L right, J left) from start to goal, or None.

        Only the state grid's blocked bits are honoured: doors that need
        bashing or unlocking are not handled. `avoid` lists squares to skip.
        """
        previous = {start: None}
        queue = deque([start])
        while queue:
            x, y = queue.popleft()
            if (x, y) == goal:
                break
            for index, (_, dx, dy, blocked, _) in enumerate(DIRECTIONS):
                nxt = (x + dx, y + dy)
                if (0 <= nxt[0] < 16 and 0 <= nxt[1] < 16 and nxt not in previous
                        and nxt not in avoid and not self.states[y * 16 + x] & blocked):
                    previous[nxt] = ((x, y), index)
                    queue.append(nxt)
        if goal not in previous:
            return None
        steps, square = [], goal
        while previous[square]:
            square, index = previous[square]
            steps.append(index)
        heading = 'NESW'.index(facing)
        keys = ''
        for index in reversed(steps):
            keys += TURNS[(index - heading) % 4] + 'I'
            heading = index
        if final:
            keys += TURNS[('NESW'.index(final) - heading) % 4]
            heading = 'NESW'.index(final)
        return keys, 'NESW'[heading]


def load_world():
    """{(name, side): Area} for every file that loads at $8200 on sides B-D."""
    table = json.loads((ROOT / 'docs/c64-logical-disk.json').read_text())
    world = {}
    for side in table:
        for slot, entry in enumerate(side['files']):
            if entry['address'] == '$8200':
                path = (ROOT / f"build/c64/original-v2-{side['side'].lower()}/logical"
                        / f"{slot:02d}-{entry['name']}.bin")
                world[(entry['name'], side['side'])] = Area(path.read_bytes())
    return world


def world_route(world, area, start, facing, goal_area, goal, final=None, avoid_flagged=False):
    """Like Area.route, but also across open edges into neighbouring areas.

    Event squares other than the goal are avoided. Returns (keys, facing,
    areas passed through) or None. avoid_flagged also avoids static state-bit-7
    squares; this does not prevent all random encounters.
    """
    events = {key: {(x, y) for x, y, *_ in a.events()} for key, a in world.items()}
    if avoid_flagged:
        for key, a in world.items():
            events[key].update((i % 16, i // 16) for i, state in enumerate(a.states) if state & 0x80)
    previous = {(area, start): None}
    queue = deque([(area, start)])
    while queue:
        here, (x, y) = queue.popleft()
        if (here, (x, y)) == (goal_area, goal):
            break
        for index, (_, dx, dy, blocked, _) in enumerate(DIRECTIONS):
            if world[here].states[y * 16 + x] & blocked:
                continue
            nxt, there = (x + dx, y + dy), here
            if not (0 <= nxt[0] < 16 and 0 <= nxt[1] < 16):
                there = world[here].neighbours()[index]
                if there == here or there not in world:
                    continue
                nxt = (nxt[0] % 16, nxt[1] % 16)
            key = (there, nxt)
            if key in previous or (key != (goal_area, goal) and nxt in events[there]):
                continue
            previous[key] = ((here, (x, y)), index)
            queue.append(key)
    if (goal_area, goal) not in previous:
        return None
    steps, passed, key = [], [goal_area], (goal_area, goal)
    while previous[key]:
        key, index = previous[key]
        steps.append(index)
        if key[0] != passed[-1]:
            passed.append(key[0])
    heading = 'NESW'.index(facing)
    keys = ''
    for index in reversed(steps):
        keys += TURNS[(index - heading) % 4] + 'I'
        heading = index
    if final:
        keys += TURNS[('NESW'.index(final) - heading) % 4]
        heading = 'NESW'.index(final)
    return keys, 'NESW'[heading], passed[::-1]


def write_world():
    report = []
    for (name, side), area in sorted(load_world().items(), key=lambda kv: (kv[0][1], kv[0][0])):
        events = []
        for x, y, facings, address in area.events():
            text = re.findall(rb'[A-Z"\'][A-Z ,.!?\'":()/0-9-]{5,}', area.handler(address))
            events.append({'square': [x, y], 'facings': facings, 'handler': f'${address:04x}',
                           'text': text[0].decode() if text else None})
        report.append({
            'area': name, 'side': side, 'bytes': len(area.data),
            'neighbours': {d[0]: (None if n == (name, side) else f'{n[0]}/{n[1]}')
                           for d, n in zip(DIRECTIONS, area.neighbours())},
            'exits': [{'to': f'{to}/{to_side}', 'square': list(where[:2]) if where else None,
                       'facings': where[2] if where else None}
                      for to, to_side, where in area.exits()],
            'events': events})
    (ROOT / 'docs/c64-areas.json').write_text(json.dumps(report, indent=1) + '\n')
    print(f'{len(report)} areas; {sum(len(a["exits"]) for a in report)} exits; '
          f'{sum(len(a["events"]) for a in report)} event squares')


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('file', type=Path, nargs='?')
    parser.add_argument('route', nargs='*', help='X Y FACING X Y [FACING]')
    parser.add_argument('--world', action='store_true')
    args = parser.parse_args()
    if args.world:
        write_world()
        return
    if not args.file:
        parser.error('give an area file or --world')
    area = Area(args.file.read_bytes())
    if args.route:
        r = args.route
        print(area.route((int(r[0]), int(r[1])), r[2], (int(r[3]), int(r[4])),
                         r[5] if len(r) > 5 else None))
        return
    for x, y, facings, address in area.events():
        code = area.handler(address)
        text = [t.decode() for t in re.findall(rb'[A-Z"\'][A-Z ,.!?\'":()/0-9-]{5,}', code)]
        print(f'{x:2d},{y:2d} {facings:4} ${address:04x} {len(code):3d} bytes '
              f'{code[:10].hex(" ")}  {" / ".join(text)[:90]}')


if __name__ == '__main__':
    main()
