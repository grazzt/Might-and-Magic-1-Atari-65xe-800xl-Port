"""Presentation-only patches and reference model for the 65XE direct display.

Colour patches remove stores while keeping pointer arithmetic, register
results, loops, geometry and game logic. Small wait/pause entry wrappers
force publication without changing the original loops or input rules.
Literal original bytes are mandatory.
Indirect sites were traced with tools/atari65_colour_writes.py and read in
their routines; indexed stores include the startup stub's unused copy.
"""
from collections import defaultdict
from pathlib import Path

import disassemble
import oracle

COLOUR_STORES = {
    'res-0b00': {
        0x0e24: '99ffcb', 0x0e2a: '99d4cc', 0x0e30: '99a9cd',  # view colour copy
        0x138a: '9186',                                         # wall colour rectangle
        0x1c1a: '99ffd7', 0x1c1d: '99f9d8', 0x1c20: '99f3d9', 0x1c23: '99edda',
    },
    'res-a000': {
        0xc284: '914d', 0xc28d: '914d', 0xc2a6: '997fda', 0xc2a9: '991fdb',
        0xc2eb: '9173',                                         # picture colour, not pixels
        0xc3cd: '919e',                                         # bitmap glyph colour
    },
    'en-bcd': {0x2750: '914d'},                                  # blue encounter panel
    'go-b': {0x7328: '99ffd7', 0x732b: '99f9d8', 0x732e: '99f3d9', 0x7331: '99edda'},
    'start': {0x212c: '9900d8', 0x212f: '99ffd8', 0x2132: '99fed9', 0x2135: '99fdda'},
}

BORROWED = {
    'flip65.bin': ('res-0b00', 0x1c13, '8d89035860'),
    'copycolour65.bin': ('res-0b00', 0x0e1f, 'a0d5b9ff0399ffcbb9d40499d4ccb9a90599a9cd88d0eb60'),
    'colour65.bin': ('res-0b00', 0x1c18, 'a0fa99ffd799f9d899f3d999edda88d0f160'),
    'play65.bin': ('res-a000', 0xc276, 'a900854da9d8854ea210a01da901914d8810fba027a903914d88c01e10f918a54d6928854d9002e64ecad0dea0a0a90c997fda991fdb88d0f760'),
    'bank65.bin': ('res-a000', 0xc40d, '8d0cc4ad02dd09038d02ddad00dd29fc0d0cc4200a9d60'),
    'wait65.bin': ('res-0b00', 0x0e37, 'a90085c6'),
    'pause65.bin': ('res-a000', 0xa036, '4c55c3'),
    'delay65.bin': ('res-a000', 0xb233, '4c55c3'),
    'waitspy65.bin': ('res-a000', 0xc91a, '20180bc959f007c94ed0f5a90060a9596026'),
}


def borrowed(pc):
    return any(base <= pc < base+len(bytes.fromhex(before)) for _, base, before in BORROWED.values())


def patch_list(output_dir=None):
    modules = {m.name: m for m in disassemble.modules()}
    patches = []
    for name, sites in COLOUR_STORES.items():
        module = modules[name]
        for pc, value in sites.items():
            if borrowed(pc):
                continue
            before = bytes.fromhex(value)
            actual = module.data[pc-module.base:pc-module.base+len(before)]
            if actual != before:
                raise ValueError(f'{name} ${pc:04x}: expected colour store {before.hex()}, got {actual.hex()}')
            for side, block in module.blocks:
                offset = block*256 + pc-module.base
                for index, old in enumerate(before):
                    patches.append((side, offset+index, old, 0xea, name, pc))
    if output_dir is not None:
        for filename, (name, base, value) in BORROWED.items():
            module = modules[name]
            before = bytes.fromhex(value)
            after = (Path(output_dir)/filename).read_bytes()
            if len(after) != len(before) or module.data[base-module.base:base-module.base+len(before)] != before:
                raise ValueError(f'{filename}: borrowed presentation space differs from its contract')
            for side, block in module.blocks:
                offset = block*256+base-module.base
                for index, (old, new) in enumerate(zip(before, after)):
                    patches.append((side, offset+index, old, new, name, base))
    return patches


ENTRY_HOOKS = {'wait65.bin', 'pause65.bin', 'delay65.bin', 'flip65.bin'}


class Reference(oracle.Oracle):
    """Original hardware model with the 65XE presentation patches.

    Patches affect loaded RAM, never logical media or recorded read hashes.
    Compare this reference's events/saves with an original Oracle separately.
    """
    def __init__(self, output_dir):
        self.entry_hooks = [(base, (Path(output_dir)/filename).read_bytes())
                            for filename, (_, base, _) in BORROWED.items() if filename in ENTRY_HOOKS]
        self.presentation_patches = defaultdict(list)
        for side, offset, old, new, _, pc in patch_list(output_dir):
            if pc not in {base for base, _ in self.entry_hooks}:
                self.presentation_patches[side].append((offset, old, new))
        super().__init__()

    def comparison_image(self):
        # The C64 executes its original wait/pause entries. Native wrappers
        # touch an Atari kernel flag at a C64 CIA address; executing them in
        # this reference would change hardware timing. Only their code bytes
        # are normalized in the captured image, then checked against the
        # assembled wrappers by kernel_changes on the native machine.
        memory = bytearray(self.machine.ram_image())
        for base, data in self.entry_hooks:
            memory[base:base+len(data)] = data
        return bytes(memory)

    def disk_read(self):
        params = self.mem[0x9d00:0x9d07]
        address = params[0] | params[1] << 8
        length = params[2] | params[3] << 8
        source = (params[5] | params[6] << 8)*256 + params[4]
        side = self.side
        super().disk_read()
        for offset, old, new in self.presentation_patches[side]:
            if source <= offset < source+length:
                destination = address+offset-source
                if self.machine.ram(destination) != old:
                    raise ValueError(f'Colour reference load differs at ${destination:04x}')
                self.machine.store(destination, new)


def allocation(layout, output_dir, segments):
    """Check the linked resident budget and record alternate buffer lifetimes."""
    labels = {k: int(v[1:], 16) for k, v in layout['labels'].items()}
    assert labels['font_end'] <= 0xa000, '65XE loader/font overflow'
    assert labels['display_end'] <= 0xe000, '65XE display overflow'
    assert 'ext.bin' not in segments and 'ext2.bin' not in segments, 'Extended segment in 64 KB image'
    resident = []
    for name, base in segments.items():
        length = (Path(output_dir)/name).stat().st_size
        assert base+length <= 65536
        assert base+length <= 0xd000 or base >= 0xd800, 'Resident code in Atari I/O hole'
        resident.append({'file': name, 'first': f'${base:04x}',
                         'last': f'${base+length-1:04x}', 'bytes': length})
    ordered = sorted(resident, key=lambda row: row['first'])
    for left, right in zip(ordered, ordered[1:]):
        assert int(left['last'][1:], 16) < int(right['first'][1:], 16), 'Overlapping resident segments'
    # Reuse only stand-in VIC bytes whose registers have no game users.
    # Inspect the complete static inventory, not just sampled play coverage.
    modules, _, _ = disassemble.analyse()
    uses = disassemble.machine_uses(modules)['VIC-II']
    for register, sites in uses.items():
        for name, pc, _ in sites:
            if name != 'title':
                offset = register & 63
                assert 0x11 <= offset <= 0x21, (name, pc, register, 'reserved 65XE VIC storage')
                module = next(m for m in modules if m.name == name)
                assert module.instructions[pc].mode == 'abs', 'Indexed VIC operand needs a bounds audit'
    budget = {'extended_ram_bytes': 0, 'resident_segments_bytes': sum(r['bytes'] for r in resident),
            'resident': resident,
            'loader_free_bytes': 0xa000-labels['font_end'],
            'display_free_bytes': 0xe000-labels['display_end'],
            'shared_buffers': [
                {'first': '$cc00', 'last': '$cfff', 'bytes': 1024,
                 'graphics': 'crossing rows 3/6/9', 'text': 'reordered OS font'},
                {'first': '$d800', 'last': '$dbff', 'bytes': 1024,
                 'graphics': 'crossing rows 12/19/22', 'text': 'completed text snapshot'},
                {'first': '$0100', 'last': '$017f', 'bytes': 128,
                 'disk': 'SIO sector staging', 'font': 'one ROM half-page; stack guard $90'}],
            'game_lifetimes': [
                {'first': '$2000', 'last': '$3f3f', 'bytes': 8000,
                 'graphics': 'upper original bitmap', 'overlay': '$2000-$34ff game module'},
                {'first': '$e000', 'last': '$ff3f', 'bytes': 8000,
                 'graphics': 'lower original bitmap', 'combat_entry': '$e000-$feff backs up $4000-$5eff'}]}
    if layout.get('title'):
        length=(Path(output_dir)/'title.bin').stat().st_size
        assert 0x8000+length <= 0x9d00, 'Temporary title overlaps loader'
        budget['startup_only'] = [
            {'first':'$1400','last':'$1bff','bytes':2048,
             'title_frames':'six crossing rows','scenes':'600-byte palette/mapping plan'},
            {'first':'$4000','last':'$4f7f','bytes':3968,'role':'original C64 title program'},
            {'first':'$5000','last':'$73ff','bytes':9216,'role':'temporary converted scene'},
            {'first':'$8000','last':f'${0x8000+length-1:04x}','bytes':length,
             'role':'temporary renderer, input hooks and title music'},
            {'first':'$a000','last':'$bbff','bytes':7168,'role':'parked boot code'}]
    return budget



def display_rows(memory, labels, palette=(0,4,8,14)):
    """Independent 320x200 pixel model from the game's bytes, without ANTIC tables."""
    mode = memory[labels['shown_mode']]
    pixels = []
    if mode == 0:
        for row in range(25):
            for line in range(8):
                output = bytearray()
                for value in memory[0x0400+row*40:0x0400+(row+1)*40]:
                    glyph = memory[0xcc00+(value & 127)*8+line]
                    if value & 128:
                        glyph ^= 255
                    output.extend(14 if glyph & (128 >> bit) else 0 for bit in range(8))
                pixels.append(bytes(output))
    else:
        for row in range(25):
            address = (0x2000 if mode == 2 and row < 16 else 0xe000)+row*320
            for line in range(8):
                output = bytearray()
                for column in range(40):
                    value = memory[address+column*8+line]
                    for shift in (6, 4, 2, 0):
                        output.extend([palette[(value >> shift) & 3]]*2)
                pixels.append(bytes(output))
    return pixels


def check_display(game, name):
    """Verify pixels and presentation storage while the game is held at a mark."""
    memory, labels = game.ram(), game.label
    if game.altirra and not getattr(game, 'memory65_checked', False):
        # Probe actual hardware behavior with emulation paused. A 64 KB XL
        # aliases this window when bit 4 changes; a 130XE has a separate bank.
        emulator = game.atari
        port = emulator.peek(0xd301)[0]
        original = emulator.peek(0x4000, 2)
        try:
            emulator.poke(0x4000, 0x5a)
            emulator.poke(0x4001, 0xa5)
            emulator.poke(0xd301, port & 0xef)
            assert emulator.peek(0xd301)[0] == port & 0xef, 'Bridge did not write PORTB'
            emulator.poke(0x4000, 0x3c)
            emulator.poke(0x4001, 0xc3)
            emulator.poke(0xd301, port)
            assert emulator.peek(0x4000, 2) == b'\x3c\xc3', 'Emulator has extended RAM'
        finally:
            emulator.poke(0xd301, port)
            for index, value in enumerate(original):
                emulator.poke(0x4000+index, value)
        game.memory65_checked = True
    if memory[labels['font_failed']]:
        raise AssertionError(f'{name}: unsafe stack depth during font reconstruction')
    # All scripted CTRL keys have been released by settled marks. GO $78A2
    # consumed the flag before release; party/game RAM and events are compared.
    assert memory[0x028e] == 0, f'{name}: released CTRL flag remains set'
    mode = memory[labels['shown_mode']]
    if not memory[labels['frame_ready']] & 1:
        raise AssertionError(f'{name}: frame publication did not complete')
    if mode == 0:
        assert memory[0xcc00:0xd000] == game.font65, f'{name}: text font differs from reordered OS ROM'
        assert memory[0xd800:0xdbe8] == memory[0x0400:0x07e8], f'{name}: stale text snapshot'
    else:
        for row, destination in zip((3, 6, 9, 12, 19, 22), (0xcc00, 0xcd40, 0xce80, 0xd800, 0xd940, 0xda80)):
            address = (0x2000 if mode == 2 and row < 16 else 0xe000)+row*320
            assert memory[destination:destination+320] == memory[address:address+320], f'{name}: crossing row {row}'
    from title_check import Screen
    wanted = display_rows(memory, labels, game.palette65)
    frame = game.atari
    if game.altirra:
        # The SDL renderer's RGB palette differs from Atari800's. Normalize
        # its ordered monochrome levels to the compiled logical palette, then
        # compare every pixel's position/role, not absolute RGB calibration.
        import base64
        from io import BytesIO
        from types import SimpleNamespace
        from PIL import Image
        raw = base64.b64decode(game.atari.command('SCREENSHOT')['data'])
        picture = Image.open(BytesIO(raw)).convert('RGB')
        width, height = picture.size
        assert 320 <= width <= 384 and 200 <= height <= 240, (name, picture.size)
        colours = sorted(set(picture.getdata()), key=sum)
        roles = sorted({v for row in wanted for v in row}, key=lambda v: v & 15)
        if len(colours) != len(roles):
            picture.save(game.folder/'display65-failed.png')
            raise AssertionError((name, len(colours), colours[:12], roles))
        encoding = dict(zip(colours, roles))
        pixels = bytearray(384*240)
        raw_pixels = list(picture.getdata())
        x, y = (384-width)//2, (240-height)//2
        for line in range(height):
            start = (y+line)*384+x
            pixels[start:start+width] = bytes(encoding[v] for v in raw_pixels[line*width:(line+1)*width])
        pixels = bytes(pixels)
        frame = SimpleNamespace(screen=lambda: pixels)
    if not hasattr(game, 'display65'):
        game.display65 = Screen(frame)
        assert game.display65.find(wanted), f'{name}: native pixels do not match direct-display model'
    else:
        game.display65.atari = frame
        differences = game.display65.differences(wanted)
        assert not differences, f'{name}: {differences} native pixels differ from the direct-display model'
