#!/usr/bin/env python3
"""Graphics checks against the frozen converter and independent colour policy.

Real native snapshots supply both the independent old kernel and its pixels.
Walking stays exact to that converter; corrected encounters use direct pixel
enumeration. Adversarial edits compare complete refreshes, not cache flags.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'tools'), str(ROOT / 'port/atari')]
import build
import mos6502
import colour_policy

BASELINE = ROOT / 'test-artifacts/graphics-profile/normal'


def execute(memory, labels, entry='refresh', stop=0x0200, x=0):
    mem = bytearray(memory)
    cpu = mos6502.CPU(mem)
    cpu.io_read = lambda address: mem[address]
    cpu.special = lambda address, value: mem.__setitem__(address, value)
    cpu.pc, cpu.s, cpu.x = labels[entry], 0xfd, x
    mem[0x1fe:0x200] = bytes([0xff, 1])
    cells, identities = Counter(), Counter()
    for address in (stop, labels['rf_cell'], labels.get('rf_identity', stop)):
        cpu.hooks[address] = 1
    def hook(pc):
        if pc == stop:
            return True
        if pc == labels['rf_cell']:
            cells[mem[labels['row']]] += 1
        if pc == labels.get('rf_identity'):
            identities[mem[labels['row']]] += 1
        return False
    cpu.on_hook = hook
    cpu.run(2_000_000)
    assert cpu.pc == stop, f'{entry} did not return'
    return mem, dict(cells=cells, identities=identities, carry=bool(cpu.p & 1))


def output(mem, labels):
    return (b''.join(mem[0x4000+r//3*1024+r%3*320:
                         0x4000+r//3*1024+r%3*320+320] for r in range(25)),
            b''.join(mem[labels[n]:labels[n]+25]
                     for n in ('row_pf0', 'row_pf1', 'row_pf2', 'row_pf3')))


def check(out):
    layout = build.build()
    new = {k: int(v[1:], 16) for k,v in layout['labels'].items()}
    old = {k: int(v[1:], 16) for k,v in json.loads((BASELINE/'report.json').read_text())['labels'].items()}
    original = (BASELINE/'01-step-before.bin').read_bytes()
    # Only extended-bank code/data move. Interrupts are not run by this host
    # check; their native equivalence is covered by lockstep and profiling.
    def kernel(mem, optimized):
        mem = bytearray(mem)
        source_labels, target_labels = (old, new) if optimized else (new, old)
        palettes = {n: bytes(mem[source_labels[n]:source_labels[n]+25])
                    for n in ('row_pf0','row_pf1','row_pf2','row_pf3')}
        for base, name in ((0x6800, 'ext.bin'), (0x7c00, 'ext2.bin')):
            mem[base:base+1024] = ((build.OUT/name).read_bytes() if optimized
                                  else original[base:base+1024])
        if optimized and 'mapping_chosen' in new:
            mem[new['mapping_chosen']:new['mapping_chosen']+3] = bytes([255]*3)
        if optimized:
            first = new['idempotent']
            mem[first:first+16] = (build.OUT/'top.bin').read_bytes()[first-0xff50:first-0xff50+16]
            first = new['rf_blank']
            mem[first:first+9] = (build.OUT/'top.bin').read_bytes()[first-0xff50:first-0xff50+9]
        for n,data in palettes.items():
            mem[target_labels[n]:target_labels[n]+25] = data
        return mem
    records = []
    for before in sorted(BASELINE.glob('*-before.bin')):
        state = before.read_bytes()
        expected = before.with_name(before.name.replace('-before', '-after')).read_bytes()
        reference, _ = execute(state, old)
        assert output(reference, old) == output(expected, old), before.name
        actual, stats = execute(kernel(state, True), new)
        wanted = colour_policy.convert(state, 1)[:2] if state[0x389] == 1 else output(expected, old)
        assert output(actual, new) == wanted, before.name
        records.append(dict(case=before.stem, cells=sum(stats['cells'].values())))

    cold = kernel(original, True)
    cold[new['shown_mode']] = 0  # populate new qualifications through real misses
    warm, _ = execute(cold, new)
    def differential(name, state, skipped=None):
        actual, stats = execute(state, new)
        expected, _ = execute(kernel(state, False), old)
        wanted = colour_policy.convert(state, 1)[:2] if state[0x389] == 1 else output(expected, old)
        assert output(actual, new) == wanted, name
        if skipped is not None:
            observed = [r for r in range(25) if not stats['cells'].get(r)]
            assert observed == skipped, (name, observed, skipped)
        records.append(dict(case=name, cells=sum(stats['cells'].values())))
        return actual
    differential('unchanged-warm', warm, list(range(16,25)))
    row, src, dst = 16, 0xe000+16*320, 0x4000+16//3*1024+16%3*320
    # Fail in both halves, at boundaries and at the last tested byte. The
    # complete output also proves pointer restoration before fallback.
    for offset in (0, 63, 64, 255, 256, 319):
        state = bytearray(warm)
        state[src+offset] ^= 0x55
        differential(f'raw-mismatch-{offset}', state, list(range(17,25)))
    state = bytearray(warm)
    state[0xcc00+row*40] ^= 0x12
    differential('matrix-changed', state)
    state = bytearray(warm)
    address = 0xcc00+row*40
    state[address:address+40] = state[address+20:address+40]+state[address:address+20]
    differential('matrix-reordered-same-histogram', state)
    state = bytearray(warm)
    state[0xd800+row*40:0xd800+(row+1)*40] = bytes(
        (value & 15) | 0xa0 for value in state[0xd800+row*40:0xd800+(row+1)*40])
    differential('ram-high-bits-only', state, list(range(16,25)))
    for name, colors in (('uniform-ram-changed', [5]*40),
                         ('varied-ram', [1]*39+[5])):
        state = bytearray(warm)
        state[0xd800+row*40:0xd800+(row+1)*40] = bytes(colors)
        differential(name, state)
    for mode in (1, 2):
        state = bytearray(warm)
        state[0x389] = mode
        differential(f'bitmap-mode-{mode}', state)
    state = bytearray(warm)
    state[0x389] = 0
    state = differential('bitmap-to-text', state)
    state[0x389] = 2
    differential('text-to-bitmap-with-old-qualifications', state, [])
    state = bytearray(warm)
    state[new['row_reuse']:new['row_reuse']+25] = bytes([1]*25)
    state[new['shown_mode']] = 0
    differential('cold-with-stale-positive-flags', state, [])

    maps = build.colour_tables()
    valid = [all(maps[i*256+maps[i*256+b]] == maps[i*256+b] for b in range(256))
             for i in range(16)]
    qualification = []
    for i in range(16):
        state = bytearray(warm)
        state[new['row']] = row
        state[0xf4:0xf6] = bytes([0, 0xcc])
        state[new['pair']:new['pair']+16] = bytes(list(range(4))*4)
        state[new['pair4']:new['pair4']+16] = bytes([v*4 for v in list(range(4))*4])
        value = (i & 3)*16+(i >> 2)
        state[0xcc00:0xcc28] = bytes([0x12]*40)
        state[0xcc00] = value  # last entry tested by the descending qualifier
        state[new['row_reuse']+row] = 0
        actual, _ = execute(state, new, 'qualify_row')
        assert bool(actual[new['row_reuse']+row]) == valid[i], i
        qualification.append(dict(table=i, idempotent=valid[i]))

    # All 256 source byte values under every lookup, plus identity interleaved
    # with changing/swapping pages. Independent generated tables are the oracle.
    patterns = [[i]*40 for i in range(16)] + [[9,6,9,4,15,0,9,2]*5]
    for index, tables in enumerate(patterns):
        state = bytearray(warm)
        state[new['pair']:new['pair']+16] = bytes(list(range(4))*4)
        state[new['pair4']:new['pair4']+16] = bytes([v*4 for v in list(range(4))*4])
        state[0xf0:0xf6] = bytes([0x80,0xe0,0x80,0x40,0,0xcc])
        raw = bytes(range(256))+bytes(range(64))
        state[0xe080:0xe1c0] = raw
        state[0xcc00:0xcc28] = bytes([(i&3)*16+(i>>2) for i in tables])
        state[new['cells']] = 40
        actual, _ = execute(state, new, 'rf_cell', stop=new['rf_next_row'])
        expected = bytes(maps[tables[b//8]*256+v] for b,v in enumerate(raw))
        assert actual[0x4080:0x41c0] == expected, index
    # Known negative: raw == old output cannot authorize a pair swap.
    assert maps[6*256+0x55] == 0xaa and not valid[6]
    state = bytearray(warm)
    state[new['cache_hit']], state[new['row_reuse']+row] = 1, 0
    state[0xf0:0xf4] = bytes([src&255,src>>8,dst&255,dst>>8])
    _, stats = execute(state, new, 'reuse_row', x=row)
    assert not stats['carry'], 'Disqualified pair swapping reused the row'
    report = dict(refresh_cases=records, qualification_tables=qualification,
                  pixel_patterns=len(patterns), pair_swap_negative=True)
    out.mkdir(parents=True, exist_ok=True)
    (out/'graphics-check.json').write_text(json.dumps(report, indent=2)+'\n')
    print(f'OK: {len(records)} differential refreshes, 16 qualification tables, '
          f'{len(patterns)} exhaustive/mixed pixel patterns and pair-swap negative')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=build.OUT/'graphics-check')
    check(parser.parse_args().out)
