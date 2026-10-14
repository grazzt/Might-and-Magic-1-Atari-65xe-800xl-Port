"""Drive AltirraSDL from Python through its bridge: boot a disk, press keys,
read memory and ANTIC's registers, take pictures.

AltirraSDL (https://github.com/ilmenit/AltirraSDL) is started headless with
--bridge and takes one-line commands over a local socket; every reply is one
line of JSON. The emulator runs only while a FRAME command is being served, so
a script sees a still machine between commands.

The launcher is ~/.local/bin/altirra, or the program named by $ALTIRRA. The
emulator's settings are kept in the folder given, apart from the owner's own.

AltirraSDL never writes to the disk image it is given. What the Atari writes
goes to a working copy among the emulator's settings, found by the image's
SHA-256 (working_copy below), and the next start with the same image and
settings carries on from that copy.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import time


def program():
    """The AltirraSDL launcher, or None when it is not installed."""
    named = os.environ.get('ALTIRRA') or shutil.which('altirra') or str(Path.home() / '.local/bin/altirra')
    return named if Path(named).exists() else None


def working_copy(disk, folder):
    """The file that holds the image as the Atari has left it."""
    name = hashlib.sha256(Path(disk).read_bytes()).hexdigest()
    return Path(folder) / 'config/altirra/disk_state' / name / 'disk.atr'


class Altirra:
    """A 130XE with 128 KB, Altirra's own XL OS, BASIC off, NTSC, booted from `disk`.

    fresh: forget what earlier runs wrote to their working copies of disks.
    """

    def __init__(self, disk, folder, sio_patch=True, fresh=True, options=(), ram_kb=128):
        folder = Path(folder)
        (folder / 'config').mkdir(parents=True, exist_ok=True)
        if fresh:
            shutil.rmtree(folder / 'config/altirra/disk_state', ignore_errors=True)
        self.log = folder / 'altirra.log'
        # The plain SDL renderer: headless, the default one took eight times as long
        # for the same frames (measured 2026-10-11). Its pictures have the same
        # pixels with every colour one level darker.
        if ram_kb not in (64, 128):
            raise ValueError('Supported Atari profiles have 64 or 128 KB')
        arguments = [program(), '--headless', '--renderer', 'sdlrenderer',
                     '--hardware', '800xl' if ram_kb == 64 else '130xe', '--memsize', f'{ram_kb}K',
                     '--kernel', 'llexl', '--nobasic', '--ntsc',
                     *(['--artifact', 'none'] if ram_kb == 64 else []),
                     '--bridge=tcp:127.0.0.1:0', *options,
                     '--bootrw', str(disk)]
        with self.log.open('w') as log:
            self.process = subprocess.Popen(arguments, stdout=log, stderr=log, start_new_session=True,
                                            env={**os.environ, 'XDG_CONFIG_HOME': str(folder / 'config')})
        token_file = Path(f'/tmp/altirra-bridge-{self.process.pid}.token')
        deadline = time.monotonic() + 40
        while not token_file.exists() or len(token_file.read_text().splitlines()) < 2:
            if self.process.poll() is not None or time.monotonic() > deadline:
                self.process.kill()
                raise SystemExit(f'AltirraSDL did not open its bridge; see {self.log}')
            time.sleep(0.1)
        address, token = token_file.read_text().splitlines()[:2]
        _, host, port = address.split(':')
        self.socket = socket.create_connection((host, int(port)), timeout=60)
        self.channel = self.socket.makefile('rwb')
        self.command('HELLO ' + token)
        self.command('PAUSE')
        self.command('CONFIG siopatch ' + ('on' if sio_patch else 'off'))

    def command(self, line):
        self.channel.write((line + '\n').encode())
        self.channel.flush()
        reply = json.loads(self.channel.readline())
        if not reply.get('ok'):
            raise RuntimeError(f'{line.split()[0]}: {reply}')
        return reply

    def frame(self, count=1):
        self.command(f'FRAME {count}')
        self.command('PING')            # answered only when the frames have run

    def peek(self, address, length=1):
        """Memory as the CPU sees it at this instant."""
        out = b''
        while length:
            part = min(length, 16384)
            out += bytes.fromhex(self.command(f'PEEK ${address:04x} {part}')['data'])
            address, length = address + part, length - part
        return out

    def poke(self, address, value):
        self.command(f'POKE ${address:04x} ${value:02x}')

    def press(self, name, hold=3, gap=3, ctrl=False):
        """Hold a key down in the keyboard matrix for `hold` frames, as a finger does."""
        self.command(f'KEYRAW {name} down' + (' ctrl' if ctrl else ''))
        self.frame(hold)
        self.command('KEYRAW all up')
        self.frame(gap)

    def mount(self, path, drive=0):
        """Change the disk in a drive (0 is D1, which the machine boots from), as a person does:
        the OS and the game see a new disk."""
        self.command(f'MOUNT {drive} {path}')

    def antic(self):
        """ANTIC's registers as numbers; 'list' is the display list's start as last written."""
        reply = self.command('ANTIC')
        out = {name: int(value[1:], 16) for name, value in reply.items() if isinstance(value, str)}
        out['list'] = out['DLISTL'] | out['DLISTH'] << 8
        return out

    def registers(self):
        reply = self.command('REGS')
        return {name: int(reply[name][1:], 16) for name in ('PC', 'A', 'X', 'Y', 'S', 'P')}

    cpu = registers

    def pokey(self):
        """Write-side POKEY registers; ordinary memory reads cannot recover these."""
        reply = self.command('POKEY')
        return {name: int(value[1:], 16) for name, value in reply.items() if isinstance(value, str)}

    def screenshot(self, path):
        Path(path).write_bytes(base64.b64decode(self.command('SCREENSHOT')['data']))

    def close(self):
        try:
            self.command('QUIT')
        except (RuntimeError, OSError, ValueError):
            pass
        try:
            self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.process.kill()


class Memory:
    """Byte/slice access for the shared lockstep driver; bulk reads stay bulk."""

    def __init__(self, emulator):
        self.emulator = emulator

    def __bytes__(self):
        return self.emulator.peek(0, 65536)

    def __getitem__(self, address):
        if isinstance(address, slice):
            start, stop, step = address.indices(65536)
            if step != 1:
                raise ValueError('Memory slices must be contiguous')
            return self.emulator.peek(start, stop - start)
        return self.emulator.peek(address)[0]

    def __setitem__(self, address, value):
        if isinstance(address, slice):
            start, stop, step = address.indices(65536)
            if step != 1 or len(value) != stop - start:
                raise ValueError('Memory slice assignment must preserve its length')
            for offset, byte in enumerate(value):
                self.emulator.poke(start + offset, byte)
        else:
            self.emulator.poke(address, value)
