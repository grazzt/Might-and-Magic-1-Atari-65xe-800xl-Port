import sys
sys.path.insert(0, 'tools')
import oracle
o = oracle.Oracle()
tot = [0, 0]
def report(name):
    ram = o.machine.ram_image()
    mode = ram[0x389]
    if mode == 0: return
    same = cells = 0
    for r in range(25):
        upper = mode == 2 and r < 16
        mb = (0x400 if upper else 0xCC00) + r*40
        row = ram[mb:mb+40]
        same += sum(1 for i in range(1, 40) if row[i] == row[i-1]); cells += 40
    tot[0] += same; tot[1] += cells
    print(f'{name:20s} cells equal to previous cell: {same}/{cells} = {100*same/cells:.0f}%')
o.play(open(sys.argv[1]).read().splitlines(), pictures=False, on_mark=report)
print('TOTAL', f'{100*tot[0]/tot[1]:.0f}%')
