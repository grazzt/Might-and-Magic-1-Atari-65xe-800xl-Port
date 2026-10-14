import sys, json, hashlib
sys.path.insert(0, 'tools')
import oracle
name, region = sys.argv[1], sys.argv[2]
REG = {'bitmap_lo': (0xE000, 0xFF3F), 'matrix_lo': (0xCC00, 0xCFE7), 'bitmap_hi': (0x2000, 0x34FF)}
lo, hi = REG[region]
def play(clobber):
    o = oracle.Oracle()
    marks = []
    if clobber:
        def wrap(fn):
            def f():
                if o.machine.mem[0x389] == 0:           # text mode: the bitmaps are not shown
                    for a in range(lo, hi + 1): o.machine.store(a, 0xA5)
                fn()
            return f
        for pc, h in list(o.handlers.items()):
            if getattr(h, '__name__', '') == 'disk_read': o.handlers[pc] = wrap(h)
    def on_mark(n):
        r = o.machine.ram_image()
        marks.append((n, hashlib.sha256(r[0x0B00:0x2000] + r[0x4EA0:0x8C00] + r[0x0200:0x0400]).hexdigest()[:12]))
    o.play(open(f'tools/traces/{name}.txt').read().splitlines(), pictures=False, on_mark=on_mark)
    ev = json.dumps(oracle.comparable(o.events), sort_keys=True)
    return hashlib.sha256(ev.encode()).hexdigest()[:12], marks
a, b = play(False), play(True)
same_ev = a[0] == b[0]
diff = [x[0] for x, y in zip(a[1], b[1]) if x != y]
print(f'{name:34s} {region:10s} events {"same" if same_ev else "DIFFER"}; marks {len(a[1])}, code+data memory differs at: {diff or "none"}')
