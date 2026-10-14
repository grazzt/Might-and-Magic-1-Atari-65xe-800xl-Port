import sys, collections
sys.path.insert(0, 'tools')
import oracle
o = oracle.Oracle()
tot = collections.Counter()
def report(name):
    ram = o.machine.ram_image()
    mode = ram[0x389]
    if mode == 0: return
    ident = fit = bad = 0; detail=[]
    for r in range(25):
        upper = mode == 2 and r < 16
        mb = (0x400 if upper else 0xCC00) + r*40
        cb = 0xD800 + r*40
        hi = {ram[mb+c] >> 4 for c in range(40)}
        lo = {ram[mb+c] & 15 for c in range(40)}
        cr = {ram[cb+c] & 15 for c in range(40)}
        if len(hi) == 1 and len(lo) == 1: ident += 1          # one colour per pair: palette-only
        elif len(hi | lo) <= 2: fit += 1                      # fits PF0/PF1 but swapped between cells
        else: bad += 1
        detail.append(len(hi|lo))
    tot['ident']+=ident; tot['swap']+=fit; tot['too_many']+=bad; tot['rows']+=25
    print(f'{name:22s} mode{mode} uniform-rows={ident:2d} swap-only={fit:2d} >2colours={bad:2d}  distinct 01/10 colours per row: {detail}')
o.play(open(sys.argv[1]).read().splitlines(), pictures=False, on_mark=report)
print(dict(tot))
