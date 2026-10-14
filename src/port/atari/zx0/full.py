import sys, json, pickle, os
from pathlib import Path
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(HERE))
from run import run, zx0_compress
d = json.load(open(ROOT / 'docs/c64-logical-disk.json'))
side = sys.argv[1]; i = 'ABCD'.index(side)
L = (ROOT / f'build/c64/original-v2-{side.lower()}/logical.bin').read_bytes()
items = []
for f in d[i]['files']:
    b = int(f['block'][1:], 16); n = int(f['length'][1:], 16); items.append((f['name'], L[b*256:b*256+n]))
for b, n in d[i]['monster_pictures']:
    b = int(b[1:], 16); items.append((f'pic{b:x}', L[b*256:(b+n)*256]))
items.append(('monsters', L[0x165*256:0x17e*256]))
cache = f'/tmp/zx0-{side}.pkl'
comp = pickle.load(open(cache, 'rb')) if os.path.exists(cache) else None
if comp is None:
    comp = [zx0_compress(x)[0] for _, x in items]; pickle.dump(comp, open(cache, 'wb'))
bad = 0; cyc_tot = 0; worst = (0, '')
for (name, data), c in zip(items, comp):
    out, cyc = run(c, len(data))
    if out != data: bad += 1; print('BAD', name)
    else:
        cyc_tot += cyc
        if cyc > worst[0]: worst = (cyc, name, len(data))
print(side, len(items), 'items;', bad, 'bad; total', cyc_tot, 'cycles;', f'avg {cyc_tot/sum(len(x) for _,x in items):.0f}/byte; slowest', worst)
