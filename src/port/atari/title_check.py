#!/usr/bin/env python3
"""Check the title stage of the Atari build against the C64's title program.

  python3 port/atari/title_check.py [--out build/atari/title] [--gallery]
  python3 port/atari/title_check.py --altirra [--sio]

The reference is the host oracle running the original title program: its two
title frames, its eight scenes and every write it makes to the sound chip.
The Atari build (port/atari/build.py with the title, src/title.s) runs the
same program in Atari800 and must

  show both title frames with every pixel in the colour the C64 gives it;
  play the tune: the pitch of every voice, tick for tick, on POKEY;
  show each scene as the kernel's screen copy turns the C64's screen into
    Atari rows (port/atari/colour_policy.py is the independent model), with
    the title program's own screen memory equal to the oracle's;
  come back to the title after the last scene;
  leave on Escape with the kernel exactly as assembled and memory as a disk
    without the title has it at the first prompt, and then play
    (port/atari/play_check.py's short game).

--gallery also writes docs/title/: each screen beside the C64's.
--altirra plays a shorter round in AltirraSDL; with --sio the OS ROM does
every disk transfer over the emulated serial line, as on a real machine.

Writes pictures, tune.wav and report.json to the output folder.
"""
import argparse
import ctypes
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'tools'), str(ROOT / 'port/atari')]
from c64 import shared_root            # noqa: E402
import build                            # noqa: E402
import c64_screen                       # noqa: E402
import colour_policy as policy          # noqa: E402
import lockstep                         # noqa: E402
import oracle                           # noqa: E402
import play_check                       # noqa: E402
from play_check import expect           # noqa: E402

WAIT, HOLD = 0x41ab, 0x4168             # the title program's two waits: between frames, between scenes
SCENES = range(2, 10)
SCREEN_WIDTH, SCREEN_HEIGHT = 384, 240  # Atari800's picture
BITMAP, MATRIX, COLOUR_RAM = 0xe000, 0xcc00, 0xd800
def expected_differences(label):
    """What Escape may leave different from a disk without the title, at the
    first prompt: (first, last, why). Everything else in main memory must be
    equal. Measured 2026-10-12: 105 bytes differ, all in these."""
    return [
        (0x0000, 0x0001, 'C64 CPU port: plain memory here, last written by the title program'),
        (0x0100, 0x01ff, 'stack: bytes below the stack pointer'),
        (label['idle'], label['idle'], "the kernel's count of key polls that found nothing"),
        (0xd000, 0xd7ff, 'hardware'),
        (label['zp_save'], label['zp_save'] + 127, "the OS's zero page, kept while the game has its own: its clock"),
        (label['frames'], label['dli_row'], 'frame counters and the row of the last display-list interrupt'),
        (label['row_pf0'], 0xdfff, 'row colours and colour-choice scratch: rewritten by every screen copy'),
    ]


def hooks(label):
    """What the title stage changes in the kernel while it runs: the operands
    of the key entry's and the disk read's jumps and the NMI vector's high
    byte. {address: value}."""
    return {0xffe5: label['title.title_getin'] & 255, 0xffe6: label['title.title_getin'] >> 8,
            0x9d0e: label['title.title_read'] & 255, 0x9d0f: label['title.title_read'] >> 8,
            0xfffb: label['title.title_nmi'] >> 8}


def only_hooks(memory, layout, images, label):
    """The kernel's code and tables are as assembled except for the hooks, and
    the hooks are in place."""
    wanted = hooks(label)
    changed = kernel_patches(memory, layout, images)
    return all(memory[a] == v for a, v in wanted.items()) and all(a in wanted for a in changed)


# --- the C64 side -----------------------------------------------------------------

TICKS = 1900                            # of the tune that are compared: two rounds and a bit


def reference(ticks=TICKS):
    """The oracle's title: two frames, eight scenes, the tune's writes."""
    player = oracle.Oracle()
    machine = player.machine
    machine.sid_trace = []
    out = {'frames': [], 'scenes': {}}

    def state():
        memory = bytearray(machine.ram_image())
        memory[COLOUR_RAM:COLOUR_RAM + 0x400] = machine.color
        return {'picture': player.picture(), 'memory': bytes(memory)}

    player.play([f'until ${WAIT:04x}'])
    for _ in range(2):
        player.cpu.run(10)
        player.play([f'until ${WAIT:04x}'])
        out['frames'].append(state())
    # Let the tune play on. The player runs off the KERNAL's 60 Hz timer.
    while machine.sid_trace[-1]['cycle'] - machine.sid_trace[0]['cycle'] < (ticks + 60) * (machine.cia_latch + 1):
        player.cpu.run(200000)
    # Registers 30 and 31 are not the tune: when the title program moves a
    # picture's colours it also writes the two bytes below colour RAM, $D7FE
    # and $D7FF, which on a C64 are the sound chip's unused last registers.
    out['sid'] = [(w['register'], w['value']) for w in machine.sid_trace if w['register'] < 25]
    out['below_colour_ram'] = sum(w['register'] >= 30 for w in machine.sid_trace)
    machine.sid_trace = None
    player.play([f'until ${WAIT:04x}', 'key 20'])
    for scene in SCENES:
        player.play([f'until ${HOLD:04x}'])
        out['scenes'][scene] = state()
        for _ in range(6):                  # the six parts of the wait
            player.cpu.run(10)
            if _ < 5:
                player.play([f'until ${HOLD:04x}'])
    return out


def tune_writes(tune, ticks):
    """Every SID write the player makes in `ticks` interrupts, from the decoded
    tune: the model the pitch table is built on. Compared with the oracle's."""
    writes = list(enumerate(tune['registers']))
    position, left = [0, 0, 0], [1, 1, 1]
    per_tick = []                           # per tick: [(frequency, gate) or None] * 3
    current = [None, None, None]
    for _ in range(ticks):
        for voice in range(3):
            left[voice] -= 1
            if left[voice]:
                continue
            notes = tune['voices'][voice]
            if position[voice] == len(notes):       # the end mark: all three start again
                position, left = [0, 0, 0], [1, 1, 1]
                continue
            frequency, length, gate = notes[position[voice]]
            position[voice] += 1
            left[voice] = length
            writes += [(7 * voice, frequency & 255), (7 * voice + 1, frequency >> 8),
                       (7 * voice + 4, gate | tune['waveforms'][voice])]
            current[voice] = (frequency, gate)
        per_tick.append(tuple(current))
    return writes, per_tick


def prepared(memory, scene):
    """The colour matrix as src/title.s `portraits` leaves it for the scenes
    with two pictures in a frame (3, 5, 7, 9), written independently here:
    a colour a cell does not draw becomes the frame's or, in the rows of the
    pictures, the commonest other colour drawn there."""
    memory = bytearray(memory)
    if scene % 2 == 0:
        return memory

    def drawn(row, col):
        cell = memory[BITMAP + row * 320 + col * 8:][:8]
        pairs = {byte >> shift & 3 for byte in cell for shift in (6, 4, 2, 0)}
        return 1 in pairs, 2 in pairs

    first = memory[BITMAP]
    high = any((first >> shift & 3) == 1 for shift in (6, 4, 2, 0))
    frame = memory[MATRIX] >> 4 if high else memory[MATRIX] & 15
    count = [0] * 16
    for row in range(1, 14):
        for col in range(40):
            value = memory[MATRIX + row * 40 + col]
            for used, colour in zip(drawn(row, col), (value >> 4, value & 15)):
                count[colour] = min(255, count[colour] + used)
    other, most = frame, 0
    for colour in range(15, 0, -1):
        if colour != frame and count[colour] > most:
            other, most = colour, count[colour]
    for row in range(25):
        low = other if 1 <= row < 14 else frame
        for col in range(40):
            value = memory[MATRIX + row * 40 + col]
            first_drawn, second_drawn = drawn(row, col)
            high_nibble = value >> 4 if first_drawn else frame
            low_nibble = value & 15 if second_drawn else low
            memory[MATRIX + row * 40 + col] = high_nibble << 4 | low_nibble
    return memory


def as_atari(rows):
    """200 rows of 320 C64 colour numbers as the Atari colour values that
    stand in for them."""
    table = bytes(build.ATARI_COLOUR) + bytes(240)
    return [bytes(row).translate(table) for row in rows]


def scene_rows(memory):
    """A scene as the kernel's screen copy shows it: 200 rows of Atari colours."""
    encoded, _, palettes = policy.convert(memory, 1)
    return as_atari(policy.picture(encoded, palettes, policy.panel_edge(memory, 1)))


# --- the Atari side ---------------------------------------------------------------

class Screen:
    """Atari800's display, and where in it the 320 x 200 picture is."""

    def __init__(self, atari):
        self.atari, self.origin = atari, None

    def rows(self, origin=None):
        x, y = origin or self.origin
        pixels = self.atari.screen()
        return [pixels[(y + line) * SCREEN_WIDTH + x:(y + line) * SCREEN_WIDTH + x + 320] for line in range(200)]

    def find(self, wanted):
        """Set the origin to where `wanted` is shown exactly; False if nowhere."""
        pixels = self.atari.screen()
        for y in range(SCREEN_HEIGHT - 200 + 1):
            for x in range(SCREEN_WIDTH - 320 + 1):
                if all(pixels[(y + line) * SCREEN_WIDTH + x:(y + line) * SCREEN_WIDTH + x + 320] == wanted[line]
                       for line in (100, 20, 180)) and self.rows((x, y)) == wanted:
                    self.origin = (x, y)
                    return True
        return False

    def differences(self, wanted):
        return sum(a != b for mine, theirs in zip(self.rows(), wanted) for a, b in zip(mine, theirs))


def write_png(path, rows, atari):
    """A picture of Atari colour values, in Atari800's palette."""
    palette = atari.palette()
    c64_screen.write_png(path, rows, [tuple(c) for c in palette])


def pokey(atari):
    lib = atari._lib
    audf = (ctypes.c_ubyte * 8).in_dll(lib, 'POKEY_AUDF')
    audc = (ctypes.c_ubyte * 8).in_dll(lib, 'POKEY_AUDC')
    audctl = (ctypes.c_ubyte * 2).in_dll(lib, 'POKEY_AUDCTL')
    return {'wide': audf[0] | audf[1] << 8, 'narrow': (audf[2], audf[3]),
            'volume': (audc[1] & 15, audc[2] & 15, audc[3] & 15), 'silent': audc[0] & 15, 'control': audctl[0],
            'pure': all(audc[i] >> 4 == 0xa for i in (1, 2, 3))}


def kernel_patches(memory, layout, images):
    """Addresses of the kernel's code and tables that are not as assembled."""
    return sorted(address for address, _, _ in lockstep.kernel_changes(memory, layout['fixed'], images))


def check_tune(expected, observed, notes):
    """Align what POKEY held each frame with the tune's ticks. A tick is one
    frame, except that a frame can pass without one (the title program had
    interrupts masked); those are counted. Returns (ticks matched, frames
    without a tick)."""
    wide = {frequency: divider for frequency, _, divider, _ in notes}
    narrow = {frequency: divider for frequency, _, _, divider in notes}

    def wanted(tick):
        out = []
        for voice, state in enumerate(expected[tick]):
            if state is None or state[0] not in wide:
                out.append(None)            # a rest: silent, the divider is whatever it was
            else:
                out.append((wide if voice == 0 else narrow)[state[0]])
        return out

    def agrees(frame, tick):
        heard = [observed[frame]['wide'], *observed[frame]['narrow']]
        for voice, divider in enumerate(wanted(tick)):
            if divider is None:
                if observed[frame]['volume'][voice]:
                    return False
            elif heard[voice] != divider:
                return False
        return True

    # The tune began before the first frame recorded here: line the two up at
    # the first change of pitch in voice 1.
    change = next(t for t in range(1, len(expected)) if wanted(t)[0] != wanted(t - 1)[0])
    heard = next((f for f in range(1, len(observed)) if observed[f]['wide'] != observed[f - 1]['wide']), None)
    if heard is None or heard > change or not all(agrees(heard - i, change - i) for i in range(1, heard + 1)):
        raise SystemExit('FAILED: the start of the tune was not found on POKEY')
    frame, tick, missed = heard, change, 0
    while frame < len(observed) and tick < len(expected):
        if agrees(frame, tick):
            tick += 1
        elif tick and agrees(frame, tick - 1):
            missed += 1                     # a frame without a tick
        else:
            heard = [observed[frame]['wide'], *observed[frame]['narrow'], observed[frame]['volume']]
            raise SystemExit(f'FAILED: tune differs at frame {frame}, tick {tick}: POKEY {heard}, wanted {wanted(tick)}')
        frame += 1
    return tick, missed


def boot(disk, sound=False):
    sys.path.insert(0, str(shared_root() / 'port/atari'))
    from harness import Atari
    return Atari(disk, extra_args=['-xe'], sound=sound)


def text_at_prompt(atari):
    return any('INSERT DISK B' in line for line in play_check.text(atari))


def settle_prompt(atari):
    """Compare title/plain startup at the same clock tick, without exclusions.

    The first prompt polls GETIN directly and never advances the game's dice
    counters. Frame/layout changes can otherwise leave its jiffy one tick
    different even though both machines reached precisely the same state.
    """
    atari.frame(30)
    for _ in range(300):
        if bytes(atari.memory[0xa0:0xa3]) == b'\0\0\x80':
            return
        atari.frame(1)
    raise SystemExit('The first prompt did not reach the comparison clock tick')


def plain_ram(path):
    """Main memory of the disk without the title, at the first prompt."""
    build.build(test=False, title=False)
    disk = build.OUT / 'title-check-plain.atr'
    shutil.copyfile(build.OUT / 'mm1.atr', disk)
    atari = boot(disk)
    for _ in range(3000):
        if text_at_prompt(atari):
            break
        atari.frame(1)
    else:
        raise SystemExit('The disk without the title did not reach the first prompt')
    settle_prompt(atari)
    Path(path).write_bytes(bytes(atari.memory))


def check(out, gallery=False):
    out.mkdir(parents=True, exist_ok=True)
    report = {}
    c64 = reference()
    tune = build.title_tune()
    notes = build.title_notes(tune)
    ticks = TICKS
    writes, per_tick = tune_writes(tune, ticks)
    expect(c64['sid'][:len(writes)] == writes and len(writes) > 700,
           f"the decoded tune predicts all {len(writes)} writes the C64 makes to the sound chip in {ticks} ticks")
    lengths = [sum(length for _, length, _ in voice) for voice in tune['voices']]
    report['tune'] = {'notes': [len(v) for v in tune['voices']], 'ticks': lengths, 'pitches': len(notes),
                      'seconds_per_round': round(min(lengths) / 60, 1)}

    layout = build.build(test=False, title=True)
    label = {name: int(value[1:], 16) for name, value in layout['labels'].items()}
    images = {name: (build.OUT / name).read_bytes() for name in build.SEGMENTS}
    disk = out / 'title-check.atr'
    shutil.copyfile(build.OUT / 'mm1.atr', disk)
    atari = boot(disk, sound=True)
    memory = atari.memory
    screen = Screen(atari)
    stage = lambda: memory[label['title.stage']]
    title_list, kernel_list = label['title.list'], label['bitmap_list']
    at_title = lambda: ((memory[0x0314], memory[0x0315]) == (0xe0, 0x4b)
                        and memory[0xfffb] == label['title.title_nmi'] >> 8 and stage() == 0)

    def until(condition, what, limit=6000):
        start = atari.frames
        while not condition():
            if atari.frames - start >= limit:
                atari.screenshot(out / 'failed.png')
                raise SystemExit(f"FAILED: {what} (not after {limit} frames; PC ${atari.cpu()['PC']:04x})")
            atari.frame(1)
        return atari.frames - start

    # --- the tune and the two frames ---
    report['frames_to_title'] = until(at_title, 'the title')
    expect(True, f"the title program runs and starts its tune ({report['frames_to_title']} frames after power-on)")
    expect(only_hooks(memory, layout, images, label),
           "during the title the kernel's code differs only in the three hooks: disk read, key, NMI")
    # A frame is complete when the title program is waiting: its bitmap has
    # stopped changing and the stage has copied its six rows once more.
    observed, settled, previous, still, looked = [], {0: [], 1: []}, None, 0, False
    waiting, lists = [], set()
    for _ in range(ticks):
        atari.frame(1)
        observed.append(pokey(atari))
        now = bytes(memory[BITMAP:BITMAP + 8000])
        still = still + 1 if now == previous else 0
        previous = now
        looked = looked and still > 0
        waiting.append(not memory[label['title.passes']])
        if still >= 6 and not memory[label['title.passes']] and not looked:
            looked = True
            for index, frame in enumerate(c64['frames']):
                if now == frame['memory'][BITMAP:BITMAP + 8000]:
                    wanted = as_atari(frame['picture'])
                    if screen.origin is None:
                        expect(screen.find(wanted), 'a title frame is on screen, pixel for pixel')
                    if not settled[index]:
                        atari.screenshot(out / f'frame-{index + 1}.png')
                    settled[index].append(screen.differences(wanted))
                    lists.add(lockstep.display_list(atari))
    expect(min(len(settled[0]), len(settled[1])) >= 10 and not any(settled[0] + settled[1]),
           f'both title frames are shown with all 64,000 pixels as on the C64, {len(settled[0])} and '
           f'{len(settled[1])} times (picture at {screen.origin})')
    expect(lists == {title_list}, "ANTIC is on the title's display list")
    matched, missed = check_tune(per_tick, observed, notes)
    expect(matched > ticks - 40 and missed <= 8,
           f'the tune: {matched} ticks on POKEY with the right pitch in all three voices, {missed} frames late')
    expect(all(o['control'] == 0x50 and o['silent'] == 0 and o['pure'] for o in observed),
           'POKEY: channels 1+2 joined at 1.79 MHz, 3 and 4 at 64 kHz, pure tones')
    expect(max(o['volume'][0] for o in observed) >= 8 and all(max(o['volume'][v] for o in observed) >= 4 for v in (1, 2)),
           'all three voices are audible')
    atari.save_audio(out / 'tune.wav')
    runs, length = [], 0
    for value, following in zip(waiting, waiting[1:] + [None]):
        length += 1
        if following != value:
            runs.append((value, length))
            length = 0
    waits = sorted(n for value, n in runs[1:-1] if value)
    draws = sorted(n for value, n in runs[1:-1] if not value)
    report['rhythm'] = {'frames_waiting': waits[len(waits) // 2], 'frames_drawing': draws[len(draws) // 2],
                        'c64_cycles_per_change': 658000}
    report['tune'].update(ticks_checked=matched, frames_without_tick=missed)

    # --- the scenes ---
    until(lambda: still_title(memory, c64), 'a complete title frame', 600)
    atari.type(' ')
    report['scenes'] = {}
    start = atari.frames
    for scene in SCENES:
        memory[label['title.fresh']] = memory[label['title.fresh']]     # (read only; the stage clears it itself)
        until(lambda: stage() == 2 and memory[label['title.fresh']] and memory[0x4938] == scene + 1,
              f'scene {scene}')
        atari.frame(2)
        wanted_memory = prepared(c64['scenes'][scene]['memory'], scene)
        mine = bytes(memory)
        same = (mine[BITMAP:BITMAP + 8000] == wanted_memory[BITMAP:BITMAP + 8000]
                and mine[MATRIX:MATRIX + 1000] == wanted_memory[MATRIX:MATRIX + 1000]
                and all(a & 15 == b & 15 for a, b in zip(mine[COLOUR_RAM:COLOUR_RAM + 1000],
                                                          wanted_memory[COLOUR_RAM:COLOUR_RAM + 1000])))
        wrong = screen.differences(scene_rows(wanted_memory))
        atari.screenshot(out / f'scene-{scene}.png')
        expect(same and not wrong and lockstep.display_list(atari) == kernel_list,
               f"scene {scene}: the title program's screen equals the C64's and the kernel shows it as its "
               f'model does ({wrong} pixels differ)')
        report['scenes'][scene] = {'frames': atari.frames - start}
        start = atari.frames
    expect(all(o == 0 for o in pokey(atari)['volume']), 'the scenes are silent')
    report['frames_back_to_title'] = until(at_title, 'the title again after the last scene')
    until(lambda: still_title(memory, c64) and not memory[label['title.passes']], 'a complete title frame', 900)
    atari.frame(3)
    which = [i for i, f in enumerate(c64['frames']) if bytes(memory[BITMAP:BITMAP + 8000]) == f['memory'][BITMAP:BITMAP + 8000]]
    expect(which and not screen.differences(as_atari(c64['frames'][which[0]]['picture'])),
           'after the last scene the title frames are back, pixel for pixel')
    loudest = 0
    for _ in range(60):                     # a note of the tune may be between two soundings
        atari.frame(1)
        loudest = max(loudest, *pokey(atari)['volume'])
    expect(loudest > 0, 'and the tune plays again')
    until(lambda: still_title(memory, c64), 'a complete title frame', 600)

    # --- Escape ---
    atari.type('\x1b')
    report['frames_escape_to_prompt'] = until(lambda: text_at_prompt(atari), 'the first prompt after Escape')
    settle_prompt(atari)
    expect(not kernel_patches(memory, layout, images) and lockstep.display_list(atari) == label['text_list'],
           'Escape: the first prompt, the kernel as assembled, ANTIC on the text display list')
    expect(all(v == 0 for v in pokey(atari)['volume']) and pokey(atari)['control'] == 0x50, 'POKEY is silent')
    after = bytes(memory)
    (out / 'escape-ram.bin').write_bytes(after)
    plain = out / 'plain-ram.bin'
    run = subprocess.run([sys.executable, __file__, '--plain-ram', str(plain)], capture_output=True, text=True)
    if run.returncode:
        raise SystemExit(run.stdout[-600:] + run.stderr[-600:])
    reference_ram = plain.read_bytes()
    skip = bytearray(65536)
    allowed = expected_differences(label)
    for first, last, _ in allowed:
        skip[first:last + 1] = b'\1' * (last - first + 1)
    unexpected = [a for a in range(65536) if not skip[a] and after[a] != reference_ram[a]]
    expect(not unexpected, 'memory is as a disk without the title has it at this prompt, outside '
           f'{len(allowed)} listed places' + (f': differs at ${unexpected[0]:04x}' if unexpected else ''))
    report['differences_from_plain'] = sum(after[a] != reference_ram[a] for a in range(65536))

    # --- and the game plays ---
    layout = json.loads((build.OUT / 'layout.json').read_text())    # the plain build's; the kernel is the same
    play_check.play(atari, {name: int(value[1:], 16) for name, value in layout['labels'].items()}, out)
    (out / 'report.json').write_text(json.dumps(report, indent=1) + '\n')
    if gallery:
        write_gallery(out, c64)
    return report


def still_title(memory, c64):
    now = bytes(memory[BITMAP:BITMAP + 8000])
    return any(now == frame['memory'][BITMAP:BITMAP + 8000] for frame in c64['frames'])


def write_gallery(out, c64):
    """docs/title/: the Atari's screens from this run beside the oracle's."""
    folder = ROOT / 'docs/title'
    folder.mkdir(parents=True, exist_ok=True)
    for old in folder.glob('*.png'):
        old.unlink()
    for index, frame in enumerate(c64['frames']):
        shutil.copyfile(out / f'frame-{index + 1}.png', folder / f'frame-{index + 1}-atari.png')
        c64_screen.write_png(folder / f'frame-{index + 1}-c64.png', frame['picture'])
    for scene in SCENES:
        shutil.copyfile(out / f'scene-{scene}.png', folder / f'scene-{scene}-atari.png')
        c64_screen.write_png(folder / f'scene-{scene}-c64.png', c64['scenes'][scene]['picture'])
    print(f'{2 * (2 + len(SCENES))} pictures in {folder}')


# --- AltirraSDL -------------------------------------------------------------------

def check_altirra(out, sio):
    import altirra
    if not altirra.program():
        raise SystemExit('AltirraSDL is not installed (~/.local/bin/altirra, or set $ALTIRRA)')
    out.mkdir(parents=True, exist_ok=True)
    layout = build.build(test=False, title=True)
    label = {name: int(value[1:], 16) for name, value in layout['labels'].items()}
    images = {name: (build.OUT / name).read_bytes() for name in build.SEGMENTS}
    emulator = altirra.Altirra(build.OUT / 'mm1.atr', out, sio_patch=not sio)
    suffix = '-sio' if sio else ''
    frames = [0]
    peek = lambda address: emulator.peek(address)[0]
    stage = lambda: peek(label['title.stage'])
    at_title = lambda: (emulator.peek(0x0314, 2) == b'\xe0\x4b' and peek(0xfffb) == label['title.title_nmi'] >> 8
                        and stage() == 0)

    def until(condition, what, limit, step=10):
        start = frames[0]
        while not condition():
            if frames[0] - start >= limit:
                emulator.screenshot(out / 'failed.png')
                raise SystemExit(f"FAILED: {what} (not after {limit} frames; PC ${emulator.registers()['PC']:04x})")
            emulator.frame(step)
            frames[0] += step
        print(f'ok: {what} (after {frames[0] - start} frames)')

    def kernel_memory():
        memory = bytearray(65536)
        for base, image in ((build.SEGMENTS[file], images[file]) for file in images):
            memory[base:base + len(image)] = emulator.peek(base, len(image))
        return memory

    kernel = lambda: kernel_patches(kernel_memory(), layout, images)

    try:
        until(at_title, 'the title program runs and starts its tune', 9000)
        emulator.frame(120)
        expect(emulator.antic()['list'] == label['title.list'], "ANTIC is on the title's display list")
        expect(only_hooks(kernel_memory(), layout, images, label), "the kernel's code differs only in the three hooks")
        sound = emulator.pokey()
        expect(sound['AUDCTL'] == 0x50 and sound['AUDC1'] & 15 == 0
               and max(sound[f'AUDC{channel}'] & 15 for channel in (2, 3, 4)) > 0, 'the tune is on POKEY')
        emulator.screenshot(out / f'title{suffix}.png')
        emulator.press('SPACE', hold=60)        # the title program looks for keys between two frames only
        until(lambda: stage() == 2 and peek(label['title.fresh']) and peek(0x4938) == 3, 'SPACE: the first scene', 6000)
        emulator.frame(4)
        expect(emulator.antic()['list'] == label['bitmap_list'], "ANTIC is on the kernel's play-screen list")
        expect(all(emulator.pokey()[f'AUDC{channel}'] & 15 == 0 for channel in (1, 2, 3, 4)), 'the scenes are silent')
        emulator.screenshot(out / f'scene-2{suffix}.png')
        until(lambda: stage() == 2 and peek(label['title.fresh']) and peek(0x4938) == 4, 'the second scene', 6000)
        emulator.frame(4)
        emulator.screenshot(out / f'scene-3{suffix}.png')
        emulator.press('ESC', hold=8)
        seen = lambda: any('INSERT DISK B' in line for line in altirra_text(emulator))
        until(seen, 'Escape: the first prompt', 9000)
        emulator.frame(30)
        expect(not kernel() and emulator.antic()['list'] == label['text_list'],
               'the kernel is as assembled and ANTIC on the text display list')
        sound = emulator.pokey()
        expect(sound['AUDCTL'] == 0x50 and sound['SKCTL'] == 3
               and all(sound[f'AUDC{channel}'] & 15 == 0 for channel in (1, 2, 3, 4)), 'POKEY is silent, keyboard on')
        emulator.screenshot(out / f'prompt{suffix}.png')
        emulator.press('RETURN')
        until(lambda: any('OPTIONS' in line for line in altirra_text(emulator)), 'RETURN: the options menu', 9000)
    finally:
        emulator.close()


def altirra_text(emulator):
    screen = emulator.peek(0x0400, 1000)
    return [''.join(chr(c & 0x7f) if 32 <= c & 0x7f < 96 else ' ' for c in screen[row * 40:row * 40 + 40])
            for row in range(25)]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--out', type=Path, default=build.OUT / 'title')
    parser.add_argument('--gallery', action='store_true', help='also write docs/title/')
    parser.add_argument('--altirra', action='store_true', help='a shorter round in AltirraSDL')
    parser.add_argument('--sio', action='store_true', help='with --altirra: the OS does the serial transfers')
    parser.add_argument('--plain-ram', type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.plain_ram:
        plain_ram(args.plain_ram)
    elif args.altirra:
        check_altirra(args.out / 'altirra', args.sio)
    else:
        check(args.out, args.gallery)


if __name__ == '__main__':
    main()
