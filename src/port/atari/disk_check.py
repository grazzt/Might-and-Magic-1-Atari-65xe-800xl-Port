#!/usr/bin/env python3
"""Measure disk waits with first-poll keys; patched SIO or standard serial.

python3 port/atari/disk_check.py --out build/atari/disk-atari800
python3 port/atari/disk_check.py --emulator altirra --sio --out build/atari/disk-serial
--existing uses the current build without rebuilding (baseline capture).
"""
import argparse
import hashlib
import json
import shutil
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'tools'), str(ROOT / 'port/atari')]
import altirra
import build
import lockstep
from speed_check import Runner

class DiskRunner(Runner):
    def __init__(self, layout, name, out, serial):
        self.serial = serial
        if name == 'altirra':
            self.label = {k: int(v[1:], 16) for k,v in layout['labels'].items()}
            self.name, self.frames = name, 0
            self.disk = out/'input.atr'
            shutil.copyfile(build.OUT/'mm1.atr', self.disk)
            self.emulator = altirra.Altirra(self.disk, out/'emulator', sio_patch=not serial)
            # Startup can run a variable number of frames before the bridge
            # pauses. Reset after configuring SIO, then count from frame zero.
            self.emulator.command('COLD_RESET')
        else:
            assert not serial, 'Serial measurement uses Altirra'
            super().__init__(layout, name, out)

    def wait(self, condition):
        start = self.frames
        # Serial runs poll in ten-frame chunks to avoid thousands of bridge
        # round trips. The report states this resolution explicitly.
        if self.name == 'altirra' and self.serial:
            while not condition():
                assert self.frames-start < 12000, 'Disk wait timed out'
                self.emulator.frame(10)
                self.frames += 10
        else:
            self.until(condition, limit=12000)
        return self.frames-start

    def key(self, code):
        self.until(lambda: self.read(self.label['waiting'])[0])
        self.write(self.label['script_key'], code)
        start = self.frames
        self.wait(lambda: not self.read(self.label['script_key'])[0])
        self.wait(lambda: self.read(self.label['waiting'])[0])
        return self.frames-start


def check(name, out, serial=False, existing=False):
    out.mkdir(parents=True, exist_ok=True)
    layout = json.loads((build.OUT/'layout.json').read_text()) if existing else build.build(test=True)
    assert layout['test_mode'], 'Measurements need the first-poll test build'
    r = DiskRunner(layout, name, out, serial)
    results = []
    def record(action, frames):
        # A wait can be entered before ANTIC publishes the completed buffer.
        # Capture after two VBIs; they are outside the measured wait interval.
        r.emulator.frame(2)
        r.frames += 2
        r.emulator.screenshot(out/f'{action}.png')
        item = dict(action=action, frames=frames, milliseconds=round(frames*1000/59.923,1))
        results.append(item)
        print(f'{action}: {frames} frames ({item["milliseconds"]} ms)', flush=True)
    try:
        record('boot', r.wait(lambda: b'INSERT DISK B' in r.read(0x400,1000)
                             and r.read(r.label['idle'])[0]))
        r.write(r.label['side'],1)
        r.write(0x277,13)
        r.write(0xc6,1)
        record('options',r.wait(lambda: r.read(r.label['waiting'])[0]))
        record('inn',r.key(0x31))
        for key in range(1,7):
            r.write(0x28e,4)
            r.key(key)
            r.write(0x28e,0)
        record('enter-town',r.key(0x58))
        # Direct inn-return route from the existing town-services script.
        # Walk out of the inn door, turn round, and walk back to sign-in.
        for code in (0x49,0x4a,0x4a,0x49):
            r.key(code)
        assert r.read(0x3b,2) == bytes((8,3)), 'Expected innkeeper square'
        record('save',r.key(0x59))
        images = {k:(build.OUT/k).read_bytes() for k in build.SEGMENTS}
        if name == 'altirra':
            port = r.read(0xd301)[0]
            r.write(0xd301,0xd2)
            memory = r.read(0,65536)
            r.write(0xd301,port)
        else:
            memory = r.game.ram()
        assert not lockstep.kernel_changes(memory,layout['fixed'],images)
        if name == 'atari800':
            r.emulator._lib.libatari800_exit()  # flush saves before hashing the disk
        disk = altirra.working_copy(r.disk,out/'emulator') if name=='altirra' else r.game.disk
        report = dict(emulator=name, sio='standard serial' if serial else 'patched',
                      timing='NTSC, first-poll keys', resolution_frames=10 if serial else 1, actions=results,
                      disk_sha256=hashlib.sha256(disk.read_bytes()).hexdigest(), layout=layout)
        (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
        return report
    finally:
        if name=='altirra':
            r.emulator.close()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--emulator',choices=['atari800','altirra'],default='atari800')
    p.add_argument('--sio',action='store_true')
    p.add_argument('--existing',action='store_true')
    p.add_argument('--out',type=Path,default=build.OUT/'disk-check')
    a=p.parse_args()
    try:
        check(a.emulator,a.out,a.sio,a.existing)
    finally:
        if not a.existing:
            build.build(test=False)

if __name__=='__main__':
    main()
