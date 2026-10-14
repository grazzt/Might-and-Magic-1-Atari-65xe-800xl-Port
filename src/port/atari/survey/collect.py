import sys, json
sys.path.insert(0, 'tools')
import oracle
name = sys.argv[1]
o = oracle.Oracle()
calls = []
orig_read, orig_write = o.disk_read, o.disk_write
def snap(kind):
    ram = o.machine.ram_image()
    return ram
def wrap(fn, kind):
    def f():
        before = len(o.events)
        pc = o.cpu.pc
        fn()
        c = o.events[-1] if o.events and 'command' in o.events[-1] else None
        if c: calls.append(dict(c, kind=kind))
    return f
for pc, h in list(o.handlers.items()):
    if h == orig_read: o.handlers[pc] = wrap(orig_read, 'read')
    elif h == orig_write: o.handlers[pc] = wrap(orig_write, 'write')
o.play(open(f'tools/traces/{name}.txt').read().splitlines(), pictures=False)
json.dump(calls, open(f'/tmp/opencode/survey/{name}.json', 'w'))
print(name, len(calls), 'disk calls')
