import sys, collections
sys.path.insert(0, 'tools')
import oracle
o = oracle.Oracle()
def report(name):
    m = o.machine
    ram = m.ram_image()
    mode = ram[0x389]; page = ram[7]
    if mode == 0: print(name, 'text mode'); return
    # lower bitmap shows matrix at $CC00 / colour ram; upper at $0400. mode1 whole frame lower? use both
    print(f'== {name} display_mode={mode} view_page={page:02x}')
    for label, base in (('$0400', 0x400), ('$CC00', 0xCC00)):
        rows = []
        for r in range(25):
            cells = ram[base + r*40: base + r*40 + 40]
            cnt = collections.Counter(cells)
            rows.append(len(cnt))
        print(label, 'distinct matrix bytes per row:', rows)
        r = 5
        print(label, 'row5 :', bytes(ram[base+r*40: base+r*40+40]).hex())
        r = 20
        print(label, 'row20:', bytes(ram[base+r*40: base+r*40+40]).hex())
o.play(open(sys.argv[1]).read().splitlines(), pictures=False, on_mark=report)
