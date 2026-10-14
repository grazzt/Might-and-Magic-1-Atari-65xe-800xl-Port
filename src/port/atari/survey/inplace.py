import sys, json, pickle
sys.path.insert(0, 'port/atari/zx0'); sys.path.insert(0, 'tools')
from pathlib import Path
import run as R
from zx0 import zx0_compress
d = json.load(open('docs/c64-logical-disk.json'))
side = 'B'; i = 1
L = Path(f'build/c64/original-v2-b/logical.bin').read_bytes()
items = []
for f in d[i]['files']:
    b = int(f['block'][1:],16); n = int(f['length'][1:],16); items.append((f['name'], L[b*256:b*256+n]))
for b,n in d[i]['monster_pictures']:
    b = int(b[1:],16); items.append((f'pic{b:x}', L[b*256:(b+n)*256]))
# monster records: whole, and per 256-byte block (the game reads one block at a time)
mon = L[0x165*256:0x17e*256]
items.append(('monsters-whole', mon))
perblock = [mon[k*256:(k+1)*256] for k in range(25)]
pb = [zx0_compress(x) for x in perblock]
print('monster records: whole', len(zx0_compress(mon)[0]), 'bytes; per 256-byte block total', sum(len(c) for c,_ in pb), 'bytes, padded to 128:', sum(-(-len(c)//128)*128 for c,_ in pb), ' (raw 6400)')
res = []
for name, data in items:
    c, st = zx0_compress(data)
    res.append((name, len(data), len(c), st['delta']))
pickle.dump(res, open('/tmp/opencode/survey/deltas.pkl', 'wb'))
import collections
dl = collections.Counter(r[3] for r in res)
print('items', len(res), 'delta histogram', sorted(dl.items()))
print('max delta', max(r[3] for r in res), 'items with delta>0:', sum(1 for r in res if r[3] > 0))
