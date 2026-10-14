import json, sys, time
from pathlib import Path
from zx0 import zx0_compress
d=json.load(open('docs/c64-logical-disk.json'))
side=sys.argv[1]; i='ABCD'.index(side)
L=Path(f'build/c64/original-v2-{side.lower()}/logical.bin').read_bytes()
items=[]
for f in d[i]['files']:
    b=int(f['block'][1:],16); n=int(f['length'][1:],16)
    items.append((f['name'],L[b*256:b*256+n]))
for b,n in d[i]['monster_pictures']:
    b=int(b[1:],16); items.append((f'pic{b:x}',L[b*256:(b+n)*256]))
items.append(('monsters',L[0x165*256:0x17e*256])); items.append(('table',L[0x296*256:0x298*256]))
t=time.time(); raw=comp=sect=0
for name,data in items:
    c=zx0_compress(data)[0]
    raw+=len(data); comp+=len(c); sect+=-(-len(c)//128)
print(side,'items',len(items),'raw',raw,'zx0',comp,'sectors(128, padded per item)',sect,f'of 1040 = {100*sect/1040:.0f}%', f'{time.time()-t:.0f}s')
