#!/usr/bin/env python3
"""Analysis steps of the disk-read survey (REALHARDWARE.md), kept as sections.

Run from the repo root, after the collectors have written their output:
  python3 port/atari/survey/runall.sh        (clobber experiment, slow, see notes)
  for t in tools/traces/boot-*.txt ...:  collect.py NAME, mode.py NAME, touch.py NAME
The collectors write to /tmp/opencode/survey/ (collect: NAME.json, mode:
mode-NAME.json, touch: touch-NAME.bin, clobber: cl/NAME.REGION.txt).
  python3 port/atari/survey/analyze.py reads|touched|sizes
Needs /tmp/zx0-?.pkl or /tmp/opencode/zx/?.pkl (compressed items) for `sizes`;
port/atari/zx0/full.py writes /tmp/zx0-SIDE.pkl.
"""
import collections, glob, json, sys, pickle
S = '/tmp/opencode/survey/'
d = json.load(open('docs/c64-logical-disk.json'))


def items(i):
    m = {}
    for f in d[i]['files']:
        m[int(f['block'][1:], 16)] = ('file', f['name'], int(f['length'][1:], 16))
    for b, n in d[i]['monster_pictures']:
        b = int(b[1:], 16); m[b] = ('picture', f'pic{b:x}', n * 256)
    m[0x165] = ('monsters', 'monsters', 0x19 * 256); m[0x296] = ('table', 'table', 512)
    return m


def reads():
    """Classify every disk call: whole item, prefix of an item, or not an item start."""
    IT = {s: items('ABCD'.index(s)) for s in 'BCD'}
    kinds = collections.Counter(); multi = collections.defaultdict(set)
    for f in sorted(glob.glob(S + 'boot-*.json')) + [S + 'title-scenes.json']:
        for c in json.load(open(f)):
            side, blk = c['side'], int(c['block'][1:], 16)
            off, ln, addr = (int(c[k][1:], 16) for k in ('offset', 'length', 'address'))
            if c['kind'] == 'write': kinds['write'] += 1; continue
            if side in IT and blk in IT[side]:
                k, n, l = IT[side][blk]
                kinds[(k, 'whole' if off == 0 and ln == l else 'prefix' if off == 0 and ln < l else 'other')] += 1
            else:
                kinds[(side, 'not-an-item-start')] += 1
            if side in 'BCD': multi[(side, blk)].add((off, ln, hex(addr)))
    for k, v in sorted(kinds.items(), key=str): print(k, v)
    print('blocks read with more than one (offset, length, destination):')
    for k, v in sorted(multi.items(), key=str):
        if len(v) > 1: print(' ', k, sorted(v))


def touched():
    """Memory the game never reads, writes or executes in any recorded session."""
    T = bytearray(65536)
    for f in glob.glob(S + 'touch-*.bin'):
        b = open(f, 'rb').read()
        for i in range(65536): T[i] |= b[i]
    s = None; total = 0
    for a in range(0x0200, 0xD001):
        ok = a < 0xD000 and T[a] == 0
        if ok and s is None: s = a
        if not ok and s is not None:
            if a - s >= 64: print(f'${s:04X}-${a-1:04X} {a-s:5d}'); total += a - s
            s = None
    print('total', total)


def sizes():
    """Sectors per side: ZX0 per item (raw: monster records, file table, RO), 128-byte sectors."""
    sec = lambda n: -(-n // 128)
    for s in 'BCD':
        i = 'ABCD'.index(s)
        try: comp = pickle.load(open(f'/tmp/zx0-{s}.pkl', 'rb'))
        except FileNotFoundError: comp = pickle.load(open(f'/tmp/opencode/zx/{s}.pkl', 'rb'))
        names = [f['name'] for f in d[i]['files']] + [f'pic{int(b[1:], 16):x}' for b, _ in d[i]['monster_pictures']] + ['monsters']
        total = 6; big = (0, '')
        for n, c in zip(names, comp):
            if n == 'monsters': total += 50; continue
            if n == 'RO': total += sec([int(f['length'][1:], 16) for f in d[i]['files'] if f['name'] == n][0]); continue
            total += sec(len(c)); big = max(big, (len(c), n))
        print(s, total, 'sectors of 1040', f'{100*total/1040:.0f}%', 'largest item', big)


if __name__ == '__main__':
    {'reads': reads, 'touched': touched, 'sizes': sizes}[sys.argv[1]]()
