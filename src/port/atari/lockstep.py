#!/usr/bin/env python3
"""Lockstep: play one key script on the host oracle and on the Atari build in
Atari800, and compare the two machines' memory at every mark.

  python3 port/atari/lockstep.py tools/traces/boot-to-menu.txt [-v]

The Atari build keeps the game at its C64 addresses, so the comparison is on
memory itself. What is left out is listed in IGNORED below, each with its
reason; everything else must be equal.

Part of what is left out is the Atari kernel, which the oracle has nothing to
compare with. Its code and tables are instead compared with what was assembled
(kernel_changes): a store by the game that lands there is caught at the next
mark. With --pictures each mark also checks that ANTIC is on the display list
that goes with the screen the kernel last showed.

The script is the one VICE and the oracle play. The Atari side starts at the
game's start-up stub, so steps up to the key that leaves the title are skipped.
With --title the disk starts with the C64's title program, as the one people
play does; the harness waits for its tune and gives it Escape, and everything
after that must still equal the oracle.
`press` hands a key to the kernel's test hook, which gives it to the game on
the first pass of its key wait, as the oracle does; while no key is offered the
game is held inside that first pass, so `ready` and marks see a still machine.
`pauses` sets the key the kernel gives every pause on its first poll. `restart`
starts the Atari again from the disk as the game has left it.
"""
import argparse
import atexit
import ctypes
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'port/atari'))
from c64 import shared_root            # noqa: E402
import build                            # noqa: E402
from c64_trace import quick             # noqa: E402
import oracle                           # noqa: E402

# (first, last, why) of memory that is not compared.
IGNORED = [
    (0x0000, 0x0001, 'C64 CPU port'),
    (0x00a0, 0x00a2, 'clock: the two machines do not take the same time'),
    (0x0100, 0x01ff, 'stack: interrupts leave different bytes below the stack pointer'),
    (0x0200, 0x0289, 'Atari OS variables; C64 KERNAL variables the game does not read'),
    (0x0292, 0x0333, 'Atari OS variables; C64 KERNAL variables the game does not read'),
    (0x9d00, 0x9fff, 'the disk loader: the Atari kernel is here'),
    (0xd000, 0xd7ff, 'hardware'),
    (0xd800, 0xdfff, 'C64 colour RAM and CIAs; Atari kernel under the OS'),
    (0xff4a, 0xffff, 'unused by the game; Atari stand-in registers and vectors'),
]
# Single bytes that depend on where an interrupt fell or on elapsed time.
TIMING = {0x0029: 'sound position', 0x002a: 'sound position', 0x03a0: 'sound playing',
          0xc353: 'pause target', 0xc354: 'pause target', 0xc40c: 'video bank byte',
          0xc69f: 'sound timer', 0xc6a2: 'the old interrupt vector the game keeps',
          0xc6a3: 'the old interrupt vector the game keeps'}
# Bytes that hold something of the machine itself. The combat file keeps the
# machine's NMI vector here while it has the C64's KERNAL switched out to copy
# the lower bitmap ($26C9: saved from $FFFA at $26F2, put back at $2711). On the
# Atari that is the kernel's own vector, and putting it back changes nothing.
MACHINE = {0x271e: "the NMI vector, kept by the combat file", 0x271f: "the NMI vector, kept by the combat file"}
KEY_WAIT_COUNT = 0x002d     # the Atari is held one instruction into the wait's first pass


def display_list(atari):
    """Where ANTIC is in its display list. Between frames: the list's start."""
    if not hasattr(atari, '_lib'):
        return atari.antic()['list']
    return ctypes.c_uint16.in_dll(atari._lib, 'ANTIC_dlist').value


class Game:
    """The Atari build in Atari800 or through AltirraSDL's memory bridge."""

    def __init__(self, layout, sound=False, altirra=False, sio_patch=True, disks=False):
        sys.path.insert(0, str(shared_root() / 'port/atari'))
        from harness import Atari
        self.disks = None
        if disks:
            # four disks, as people have them: the game writes to them, so play on copies
            self.disks = [build.OUT / f'lockstep-disk{n}.atr' for n in range(1, 5)]
            for n, copy in enumerate(self.disks, 1):
                shutil.copyfile(build.DISKS_OUT / f'mm1-disk{n}.atr', copy)
            self.disk = self.disks[0]
        else:
            self.disk = build.OUT / 'lockstep.atr'      # the game writes to its disk: play on a copy
            shutil.copyfile(build.OUT / 'mm1.atr', self.disk)
        self.altirra = altirra
        self.ram_kb = layout.get('ram_kb', 128)
        self.palette65 = layout.get('palette65', [0,4,8,14])
        self.sio_patch = sio_patch
        if altirra:
            import altirra as bridge
            self.folder = build.OUT / 'lockstep-altirra/emulator'
            self.atari = bridge.Altirra(self.disk, self.folder, sio_patch=sio_patch, ram_kb=self.ram_kb)
            self.memory = bridge.Memory(self.atari)
            if self.ram_kb == 64:
                rom_font = self.atari.peek(0xe000, 1024)
            atexit.register(lambda: self.atari.close())
        else:
            self.atari = Atari(self.disk, extra_args=['-xl' if self.ram_kb == 64 else '-xe'],
                               sound=sound, sio_patch=sio_patch)
            self.memory = self.atari.memory
            actual_ram = ctypes.c_int.in_dll(self.atari._lib, 'MEMORY_ram_size').value
            if actual_ram != self.ram_kb:
                raise RuntimeError(f'Expected {self.ram_kb} KB Atari, got {actual_ram}')
            if self.ram_kb == 64:
                rom = (ctypes.c_ubyte*16384).in_dll(self.atari._lib, 'MEMORY_os')
                rom_font = bytes(rom[0x2000:0x2400])
        if self.ram_kb == 64:
            self.font65 = rom_font[768:] + rom_font[:768]
        self.label = {name: int(value[1:], 16) for name, value in layout['labels'].items()}
        if self.altirra:
            # Altirra powers on with randomized RAM. Before the kernel loads,
            # random bytes at these addresses must not look like its flags.
            for name in ('waiting', 'idle', 'script_key', 'pause_key'):
                self.memory[self.label[name]] = 0
        self.title = layout.get('title', False)
        if self.title:
            self.leave_title()

    def at_title(self):
        """The title program is showing its frames: its tune's handler is on
        the interrupt vector ($4BE0) and the title stage's own on the NMI."""
        memory = self.memory
        return (memory[0x0314], memory[0x0315]) == (0xe0, 0x4b) and memory[0xfffb] == self.label['title.title_nmi'] >> 8

    def leave_title(self):
        self.until(self.at_title, 'the title')
        self.keys([0x5f])
        self.until(lambda: not self.at_title(), 'the title to end')

    def frames(self, count):
        self.atari.frame(count)

    def until(self, condition, what, limit=3000):
        for _ in range(limit):
            if condition():
                return
            self.atari.frame(4 if self.altirra else 1)
        cpu = self.atari.cpu()
        raise SystemExit(f"Atari: gave up waiting for {what}; PC ${cpu['PC']:04x}")

    def ready(self):
        self.until(lambda: self.memory[self.label['waiting']], 'the key wait')

    def press(self, code, poll=None):
        self.ready()
        if poll is not None:
            # The ordinary wait is already held. Select the next direct call
            # before releasing it, so even a call within this frame is caught.
            self.poll_names = ('test_wait_low', 'test_wait_high', 'test_wait_stack_low', 'test_wait_stack_high')
            self.poll_original = [self.memory[self.label[name]] for name in self.poll_names]
            call = bytes(self.memory[poll:poll + 3])
            if call not in (b'\x20\xe4\xff', b'\x20\x87\xa0'):
                raise SystemExit(f'Atari: poll ${poll:04x} is not a key call')
            stack = 1 if call == b'\x20\xe4\xff' else 3
            for name, value in zip(self.poll_names, ((poll + 2) & 255, (poll + 2) >> 8, stack, stack + 1)):
                self.memory[self.label[name]] = value
        self.memory[self.label['script_key']] = code
        self.until(lambda: not self.memory[self.label['script_key']], 'the key to be taken')

    def poll(self, address, code):
        if not code:
            raise SystemExit('poll requires a nonzero key')
        if not getattr(self, 'poll_original', None):
            raise SystemExit('poll must immediately follow its triggering press')
        self.ready()
        # Restore before releasing the direct wait: the following ordinary
        # wait must be caught on its first pass too. No kernel exclusions.
        for name, value in zip(self.poll_names, self.poll_original):
            self.memory[self.label[name]] = value
        self.poll_original = None
        self.memory[self.label['script_key']] = code
        self.until(lambda: not self.memory[self.label['script_key']], 'the direct key to be taken')

    def idle(self):
        """Run until the game polls for a key and finds none (the oracle's `wait`)."""
        self.frames(2)
        self.memory[self.label['idle']] = 0
        self.until(lambda: self.memory[self.label['idle']] or self.memory[self.label['waiting']],
                   'the game to poll for a key')

    def keys(self, codes):
        for i, code in enumerate(codes):
            self.memory[0x0277 + i] = code
        self.memory[0xc6] = len(codes)

    def ram(self):
        return bytes(self.memory)

    def attach(self, side):
        """Put a side in the drive: with one big image the kernel is told which; with four
        disks the image is changed, as a player changes the disk."""
        if self.disks:
            disk = self.disks['ABCD'.index(side)]
            if self.altirra:
                self.atari.mount(disk)
            else:
                self.atari.mount_disk(disk)
        else:
            self.memory[self.label['side']] = 'ABCD'.index(side)

    def restart(self):
        """Power off and on. The emulator keeps the disk open, with what the
        game wrote to it; the boot code loads everything again from there."""
        if self.disks and not self.altirra:
            self.atari.mount_disk(self.disks[0])        # the boot disk goes back in
        if self.altirra:
            import altirra as bridge
            self.atari.close()
            self.atari = bridge.Altirra(self.disk, self.folder, sio_patch=self.sio_patch,
                                       fresh=False, ram_kb=self.ram_kb)
            self.memory = bridge.Memory(self.atari)
        else:
            self.atari._lib.Atari800_Coldstart()
        # The kernel's variables keep their old values until the boot code has
        # loaded the kernel again, about half a second later: clear the ones
        # the harness waits on, or it would take the old machine's for the new.
        for name in ('waiting', 'idle', 'script_key', 'pause_key'):
            self.memory[self.label[name]] = 0
        self.frames(2)
        if self.title:
            self.leave_title()

    def close(self):
        if self.altirra:
            import altirra as bridge
            self.atari.close()
            written = bridge.working_copy(self.disk, self.folder)
            if self.disks:      # what each disk holds now: Altirra's working copy, or the file itself
                self.written = [bridge.working_copy(d, self.folder) for d in self.disks]
                self.written = [w if w.exists() else d for w, d in zip(self.written, self.disks)]
            return written if written.exists() else self.disk
        self.atari._lib.libatari800_exit()
        return self.disk


def atari_steps(lines):
    """The script as the Atari plays it: (op, args, name of the line for messages)."""
    steps, started = [], False
    for raw in lines:
        words = raw.split('#')[0].split()
        if not words:
            continue
        if words == ['restart']:        # and again after every restart
            steps.append(words)
            started = False
            continue
        if not started:                 # the Atari build starts after the title
            started = words[:2] == ['key', '5f']
            continue
        steps.append(words)
    # A CTRL flag poked at the instant the game tests it (press, until, poke on
    # the C64) has to be set before the key here: nothing stops in mid-flight.
    # The C64's KERNAL clears the flag again; here the step after the key does.
    # A mark that follows another `until` sits in mid-flight too and is skipped.
    out, i = [], 0
    while i < len(steps):
        if (steps[i][0] == 'press' and i + 2 < len(steps) and steps[i + 1][0] == 'until'
                and steps[i + 2][0] == 'poke'):
            out += [steps[i + 2], steps[i], ['poke', steps[i + 2][1]] + ['00'] * (len(steps[i + 2]) - 2)]
            i += 3
        elif steps[i][0] == 'until':
            if i + 1 < len(steps) and steps[i + 1][0] == 'mark':
                out.append(['skip', steps[i + 1][1]])
                i += 1
            i += 1
        else:
            out.append(steps[i])
            i += 1
    return out


def compare(atari, reference, patched, waiting, presentation_ranges=()):
    """[(address, atari byte, oracle byte)] outside what is ignored."""
    skip = bytearray(65536)
    for first, last, _ in IGNORED:
        skip[first:last + 1] = b'\1' * (last - first + 1)
    for piece in presentation_ranges:
        first, last = int(piece['first'][1:], 16), int(piece['last'][1:], 16)
        skip[first:last+1] = b'\1'*(last-first+1)
    for address in list(TIMING) + list(MACHINE) + list(patched):
        skip[address] = 1
    out = []
    for address in range(65536):
        if skip[address]:
            continue
        want = reference[address]
        if address == KEY_WAIT_COUNT and waiting:
            want = want + 1 & 255
        if atari[address] != want:
            out.append((address, atari[address], reference[address]))
    return out


def kernel_changes(memory, fixed, images):
    """[(address, byte now, byte as assembled)] in the kernel's code and tables.

    fixed is build.py's list of the pieces that never change; images holds the
    assembled segment each is in, by file name.
    """
    out = []
    for piece in fixed:
        base, image = int(piece['base'][1:], 16), images[piece['file']]
        for address in range(int(piece['first'][1:], 16), int(piece['last'][1:], 16) + 1):
            if memory[address] != image[address - base]:
                out.append((address, memory[address], image[address - base]))
    return out


def whole_kernel():
    """Every byte of the kernel's segments in main memory, as a list like build.py's `fixed`."""
    return [{'file': name, 'base': f'${base:04x}', 'first': f'${base:04x}',
             'last': f'${base + (build.OUT / name).stat().st_size - 1:04x}'} for name, base in build.SEGMENTS.items()]


def runs(differences):
    out = []
    for address, mine, theirs in differences:
        if out and out[-1][1] == address - 1:
            out[-1][1] = address
            out[-1][2].append((mine, theirs))
        else:
            out.append([address, address, [(mine, theirs)]])
    return out


def compare_disks(game, layout, player):
    """Four disks, as the game left them: every item of every disk, read the way the
    kernel reads it (the index, then a stored copy or a ZX02 stream), must be the
    oracle's bytes. Returns the number of items that are not."""
    import disks
    failed = 0
    for number, side in enumerate('ABCD'):
        body = getattr(game, 'written', game.disks)[number].read_bytes()[16:]
        index = disks.index_of(body)
        # the whole logical side, as the oracle's game left it, with the stand-in operands patched
        expected = bytearray(player.logical(side))
        for patch in layout['patches']:
            if patch['side'] == side:
                expected[patch['offset']] = patch['new']
        bad, checked = [], 0
        for key, item in layout['disks'][number]['items'].items():
            block, length = int(key[1:], 16), item['length']
            if side == 'A' and block >= disks.IMAGE_BLOCK:
                continue            # pieces of the boot image: the memory at the start, not a side
            checked += 1
            if disks.read_item(body, index, block, 0, length) != bytes(expected[block * 256:block * 256 + length]):
                bad.append(f"{item['name']} (${block:03x})")
        written = sum(a != b for a, b in zip(body, (build.DISKS_OUT / f'mm1-disk{number + 1}.atr').read_bytes()[16:]))
        if bad:
            failed += len(bad)
            print(f'disk {number + 1} (side {side}): {len(bad)} of {checked} items differ from the oracle: '
                  + ', '.join(bad[:6]))
        else:
            print(f"disk {number + 1} (side {side}): all {checked} items equal the oracle's"
                  + (f'; {written} bytes written' if written else ''))
    return failed


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('script', type=Path)
    parser.add_argument('-v', '--verbose', action='store_true', help='list every differing run')
    parser.add_argument('--pictures', action='store_true',
                        help='photograph the Atari at every mark: build/atari/lockstep/NAME.png')
    parser.add_argument('--quick', action='store_true',
                        help='a key ends every pause, as with oracle.py --quick')
    parser.add_argument('--kernel-writes', action='store_true',
                        help='list, by label, every byte of the kernel seen changed from what was assembled')
    parser.add_argument('--title', action='store_true',
                        help="start with the C64's title program and leave it with Escape")
    parser.add_argument('--altirra', action='store_true', help='run the same memory and disk comparisons in AltirraSDL')
    parser.add_argument('--sio', action='store_true',
                        help='with --altirra, --disks or --65xe: use OS serial transfers')
    parser.add_argument('--disks', action='store_true',
                        help='the four-disk build (docs/DISKS.md): the disk is changed at every `attach`')
    parser.add_argument('--65xe', dest='xe64', action='store_true', help='test the direct display on exactly 64 KB')
    parser.add_argument('--colour', action='store_true', help='with --65xe: check the fixed warm palette')
    args = parser.parse_args()
    if args.colour and not args.xe64:
        parser.error('--colour requires --65xe')
    if args.sio and not (args.altirra or args.disks or args.xe64):
        parser.error('--sio requires --altirra, --disks or --65xe')
    lines = args.script.read_text().splitlines()
    if args.quick:
        lines = quick(lines)
    layout = (build.build_disks(test=True, title=args.title, xe64=args.xe64, colour65=args.colour) if args.disks
              else build.build(test=True, title=args.title, xe64=args.xe64, colour65=args.colour))
    patched = set()
    for patch in layout['patches']:
        if patch['module'].startswith('res-') or patch['module'] == 'start':
            patched.update((int(patch['pc'][1:], 16) + 1, int(patch['pc'][1:], 16) + 2))

    reference = {}
    if args.xe64:
        import profile65
        player = profile65.Reference(build.OUT)
        original = oracle.Oracle()
        original.play(lines, pictures=False)
    else:
        player = oracle.Oracle()
    player.play(lines, on_mark=lambda name: reference.__setitem__(name,
                player.comparison_image() if args.xe64 else player.machine.ram_image()))
    if args.xe64 and oracle.comparable(player.events) != oracle.comparable(original.events):
        raise RuntimeError('The colour-store removals changed original gameplay events')

    game = Game(layout, altirra=args.altirra, sio_patch=not args.sio, disks=args.disks)
    images = {name: (build.OUT / name).read_bytes() for name in build.SEGMENTS}
    written = set()             # for --kernel-writes
    waiting, failed, compared, damaged, failed_lists = False, 0, 0, 0, 0
    steps = atari_steps(lines)
    for index, words in enumerate(steps):
        op, values = words[0], words[1:]
        if op == 'press':
            following = steps[index + 1] if index + 1 < len(steps) else []
            poll = int(following[1].lstrip('$'), 16) if following and following[0] == 'poll' else None
            game.press(int(values[0], 16), poll=poll)
            waiting = False
        elif op == 'poll':
            game.poll(int(values[0].lstrip('$'), 16), int(values[1], 16))
            waiting = False
        elif op == 'ready':
            game.ready()
            waiting = True
        elif op == 'wait':
            game.idle()
            waiting = False
        elif op == 'key':
            game.keys([int(v, 16) for v in values])
            waiting = False
        elif op == 'attach':
            game.attach(values[0])
        elif op == 'pauses':
            game.ready()                # the script has it after `ready`; held, nothing can slip past
            game.memory[game.label['pause_key']] = 0 if values[0] == 'off' else int(values[0], 16)
        elif op == 'restart':
            game.restart()
            waiting = False
        elif op == 'poke':
            for i, value in enumerate(values[1:]):
                address, value = int(values[0], 16) + i, int(value, 16)
                if address == KEY_WAIT_COUNT and waiting:
                    value = value + 1 & 255     # held one instruction past where the oracle pokes
                game.memory[address] = value
        elif op == 'skip':
            print(f'{values[0]}: not compared (taken in mid-flight on the C64)')
        elif op == 'mark':
            if args.xe64 and not args.pictures:
                game.frames(2)
            if args.pictures:
                folder = build.OUT / 'lockstep'
                folder.mkdir(exist_ok=True)
                game.frames(2)          # the game is held or polling: memory does not move
                game.atari.screenshot(folder / f'{values[0]}.png')
                play = game.memory[game.label['shown_mode']]
                wanted, shown = game.label['bitmap_list' if play else 'text_list'], display_list(game.atari)
                if shown != wanted:
                    failed_lists += 1
                    print(f"{values[0]}: ANTIC's display list is at ${shown:04x}, not at ${wanted:04x} "
                          f"for {'the play screen' if play else 'text'}")
            differences = compare(game.ram(), reference[values[0]], patched, waiting,
                                  layout.get('presentation_ranges', ()))
            damage = kernel_changes(game.ram(), layout['fixed'], images)
            if args.xe64:
                profile65.check_display(game, values[0])
            if args.kernel_writes:
                written.update(address for address, _, _ in kernel_changes(game.ram(), whole_kernel(), images))
            compared += 1
            if damage:
                damaged += 1
                shown = ', '.join(f'${a:04x} {mine:02x} (assembled {built:02x})' for a, mine, built in damage[:8])
                print(f'{values[0]}: {len(damage)} bytes of the kernel are not as assembled: {shown}')
            if differences:
                failed += 1
                grouped = runs(differences)
                print(f'{values[0]}: {len(differences)} bytes differ in {len(grouped)} runs')
                for first, last, pairs in grouped[:None if args.verbose else 12]:
                    shown = ' '.join(f'{a:02x}/{b:02x}' for a, b in pairs[:8])
                    print(f'    ${first:04x}' + (f'-${last:04x}' if last > first else '') + f'  atari/oracle {shown}')
            elif not damage:
                print(f'{values[0]}: equal')
        else:
            raise SystemExit(f'Step not supported on the Atari: {" ".join(words)}')
    if args.kernel_writes:
        names = sorted((address, name) for name, address in game.label.items())
        groups = {}
        for address in sorted(written):
            groups.setdefault(max(n for n in names if n[0] <= address), []).append(address)
        for (_, name), where in sorted(groups.items()):
            print(f'kernel bytes changed: {name:15s} ${where[0]:04x}-${where[-1]:04x}, {len(where)}')
    game.frames(3)
    game.atari.screenshot(build.OUT / 'lockstep.png')
    # What the game wrote to disk must be what the oracle's game wrote. The
    # emulator buffers its writes; leaving it flushes them.
    disk = game.close()
    if args.disks:
        failed += compare_disks(game, layout, player)
        disk = None
    else:
        start = 16 + layout['boot_sectors'] * 128
        size = layout['sectors_per_side'] * 128
        written = disk.read_bytes()
        built = (build.OUT / 'mm1.atr').read_bytes()
    for index, side in enumerate('ABCD' if disk else ''):
        mine = written[start + index * size:start + (index + 1) * size]
        expected = bytearray(player.logical(side))          # as the oracle's game left it
        for patch in layout['patches']:
            if patch['side'] == side:
                expected[patch['offset']] = patch['new']
        changed = sum(a != b for a, b in zip(mine, built[start + index * size:start + (index + 1) * size]))
        if mine != bytes(expected):
            failed += 1
            where = [i for i, (a, b) in enumerate(zip(mine, expected)) if a != b]
            print(f"side {side}: the disk differs from the oracle's in {len(where)} bytes, first at block "
                  f'${where[0] // 256:03x} offset ${where[0] % 256:02x}: {mine[where[0]]:02x}, oracle {expected[where[0]]:02x}')
        elif changed:
            print(f"side {side}: {changed} bytes written, equal to the oracle's disk")
    if failed or damaged or failed_lists:
        raise SystemExit(f'{failed} of {compared} marks differ; the kernel was changed at {damaged}; '
                         f'the wrong display list at {failed_lists}')
    print(f'OK: memory equal at all {compared} marks')


if __name__ == '__main__':
    main()
