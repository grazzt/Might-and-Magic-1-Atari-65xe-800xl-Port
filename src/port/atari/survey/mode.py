import sys, json, collections
sys.path.insert(0, 'tools')
import oracle
name = sys.argv[1]
o = oracle.Oracle()
rows = []
def wrap(fn):
    def f():
        mode = o.machine.mem[0x389]
        fn()
        c = o.events[-1]
        rows.append((c['side'], c['kind'] if 'kind' in c else c['name'], mode, c['address'], c['length']))
    return f
for pc, h in list(o.handlers.items()):
    if getattr(h, '__name__', '') in ('disk_read', 'disk_write'): o.handlers[pc] = wrap(h)
o.play(open(f'tools/traces/{name}.txt').read().splitlines(), pictures=False)
json.dump(rows, open(f'/tmp/opencode/survey/mode-{name}.json', 'w'))
