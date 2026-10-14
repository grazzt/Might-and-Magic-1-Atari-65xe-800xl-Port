#!/usr/bin/env python3
"""Make a demo video of the Atari build from the recorded sessions.

  python3 port/atari/demo_video.py [--out build/atari/video] [--only NAME ...]

Every segment plays part of one of tools/traces/*.txt on the four-disk build
(docs/DISKS.md) in Atari800, with the disk changed under the running machine
as the scripts' `attach` steps say. Each frame the emulator draws, and the
sound it makes, is recorded. Nothing is staged: the screens are the Atari's
own, and the keys are the ones the oracle and the Atari were checked with.
The machine runs on for a moment at the script's marks and after each key, so
that a viewer can look at what it has drawn. Captions say what is happening.

Each segment is recorded in its own process (libatari800 is one machine per
process), losslessly at the Atari's 384x240; a second pass scales it, adds the
captions and the sound, and the last joins the segments with title cards.
Needs ffmpeg with drawtext.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'port/atari'))
import build                            # noqa: E402
import lockstep                         # noqa: E402

FPS = 59.9227                           # NTSC
WIDTH, HEIGHT = 384, 240
FONT = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'

# name: (script, first mark recorded from (None: from the start), last mark, the dwell at marks in seconds,
#        {mark: caption}, seconds after each key)
SEGMENTS = {
    'intro': dict(
        card='The title, and the first disk swap',
        script='boot-to-new-character', start='insert-b', stop='menu', title=True,
        captions={'insert-b': 'The game asks for disk B: swap the disk, press RETURN'},
        hold={'insert-b': 4.0, 'menu': 0.02}, key=0.4),
    'create': dict(
        card='Making a character',
        script='boot-to-new-character', start='menu', stop='menu-again', title=False,
        captions={'menu': 'Options menu: create a character', 'rolled': 'Roll the dice for the attributes',
                  'class': 'Choose a class', 'name': 'Name them', 'save-prompt': 'Save to the disk',
                  'saved': 'The roster is written to disk B', 'menu-again': 'Back to the options'},
        hold={'menu': 2.0, 'rolled': 2.5, 'class': 2.5, 'name': 2.5, 'save-prompt': 2.0, 'saved': 2.0,
              'menu-again': 2.0}, key=0.5),
    'town': dict(
        card='Sorpigal: the inn and the shops',
        script='boot-to-town-services', start='menu', stop='done', title=False,
        captions={'menu': 'Pick the town and the party', 'inn': 'The Inn of Sorpigal: add the party',
                  'party': 'Six characters', 'town': 'Out into the town',
                  'blacksmith-door': 'The blacksmith', 'blacksmith': 'Buy weapons and armour, sell what you carry',
                  'food-door': 'The food shop', 'food': 'Supplies', 'temple-door': 'The temple',
                  'temple': 'Healing and blessings', 'training-door': 'The training hall',
                  'training': 'Train to a new level', 'tavern-door': 'The tavern', 'tavern': 'Rumours and a drink',
                  'character': 'A character sheet', 'location': 'Where in the world', 'done': ''},
        hold={'blacksmith': 3.0, 'food': 3.0, 'temple': 3.0, 'training': 3.0, 'tavern': 3.0, 'character': 3.0},
        key=0.25, fast=4),
    'dungeon': dict(
        card='Under the town: a dungeon and a fight',
        script='boot-to-fight-and-save', start='town', stop='saved', title=False,
        inject={'dungeon': [0x23, 0x36, 0x43, 0x31, 0x36, 0x0d]},      # # 6 (Wizz Bane) C 1 6 RETURN: Light
        inject_dwell=1.0, inject_say=('Wizz Bane casts Light: # 6, then C 1 6', 'Light: now the dungeon can be seen'),
        captions={'town': 'Walk to the stairs in the south-east corner', 'stairs-down': 'Down the stairs',
                  'dungeon': 'Down the stairs: the dungeon is pitch dark', 'arena': 'The arena',
                  'fight': 'A fight', 'won': 'The fight is won: back in the arena', 'stairs-up': 'Back up the stairs',
                  'town-again': 'Back in town', 'innkeeper': 'The innkeeper', 'saved': 'Signing in saves the game to disk B'},
        hold={'dungeon': 2.5, 'fight': 2.5, 'won': 2.5, 'saved': 3.0}, key=0.15, fast=4),
    'spells': dict(
        card='Magic and missiles',
        script='boot-to-combat-actions', start='encounter', stop='positions-exchanged', title=False,
        captions={'encounter': 'An encounter: gremlins', 'fight': 'Combat: every character chooses an action',
                  'spell-cast': 'Wizz Bane casts a spell, then Zenon shoots', 'bow-fired': 'An arrow finds its mark',
                  'positions-exchanged': 'Swapping places in the party'},
        hold={'encounter': 2.5, 'spell-cast': 2.5, 'bow-fired': 3.0, 'positions-exchanged': 2.5}, key=0.5, press=0.8),
    'chest': dict(
        card='A treasure chest',
        script='boot-to-chest-traps', start='chest', stop='trap-removed', title=False,
        captions={'chest': 'A chest: it may be trapped', 'trap-detected': 'Detect the trap',
                  'trap-removed': 'The thief removes it and opens the chest'},
        hold={'chest': 3.0, 'trap-detected': 3.0, 'trap-removed': 3.5}, key=0.4, press=0.5),
    'outside': dict(
        card='Beyond the gate: disk C, and the open country',
        script='boot-to-wilderness-travel', start='town', stop='forest-after-battle', title=False,
        captions={'town': 'Walk to the town gate', 'gate': 'The gate',
                  'insert-c': 'Disk C: the world outside is on the next disk',
                  'outdoors': 'The outdoors', 'sector-ej': 'Another sector', 'sector-bb': 'On through the wilderness',
                  'travel-encounter-1': 'An encounter in the wild', 'travel-victory-1': 'Won',
                  'forest-after-battle': 'On into the forest'},
        hold={'insert-c': 4.0, 'outdoors': 3.0, 'travel-encounter-1': 3.0, 'travel-victory-1': 2.5,
              'forest-after-battle': 3.0}, key=0.12, fast=4),
    'portal': dict(
        card='A castle, and disk D',
        script='boot-to-direct-if', start='ak', stop='if-direct-key', title=False,
        captions={'ak': 'A castle: the test script jumped the party here',
                  'if-entered': 'Disk D is in: the game loads the castle from it',
                  'if-direct-key': 'Inside Castle Blackridge, loaded from disk D'},
        hold={'ak': 3.0, 'if-entered': 4.0, 'if-direct-key': 4.0}, key=0.6, press=0.6),
}


class Recorder:
    """Frames and sound out of a running Atari800, only while `on`."""

    def __init__(self, atari, path):
        self.atari = atari
        self.on = False
        self.every = 1                  # record one frame in this many (a time-lapse, silent)
        self.count = 0
        self.frames = 0
        self.captions = []              # (first frame, last frame, text)
        self.audio = bytearray()
        self.seen = 0                   # audio taken so far
        palette = atari.palette()
        import numpy
        self.numpy = numpy
        self.palette = numpy.array([list(p) for p in palette], dtype='uint8')
        self.video = subprocess.Popen(
            ['ffmpeg', '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{WIDTH}x{HEIGHT}',
             '-framerate', str(FPS), '-i', '-', '-c:v', 'libx264', '-crf', '0', '-preset', 'ultrafast',
             '-pix_fmt', 'yuv444p', str(path)], stdin=subprocess.PIPE)
        atari.on_frame = self.capture
        self.caption = None

    def capture(self):
        audio = self.atari.audio
        if self.on and self.every > 1:
            self.count += 1
            if self.count % self.every:
                self.seen = len(audio)
                return
            self.audio += bytes(len(audio) - self.seen)
        elif self.on:
            self.audio += audio[self.seen:]
        if self.on:
            pixels = self.numpy.frombuffer(self.atari.screen(), dtype='uint8')
            self.video.stdin.write(self.palette[pixels].tobytes())
            self.frames += 1
        self.seen = len(audio)

    def say(self, text):
        """Caption from now on (empty: none)."""
        if self.caption and self.on:
            self.captions.append((self.caption[0], self.frames, self.caption[1]))
        self.caption = (self.frames, text) if text else None

    def finish(self, wav, report):
        self.say('')
        self.atari.on_frame = None
        self.video.stdin.close()
        self.video.wait()
        import wave
        lib = self.atari._lib
        with wave.open(str(wav), 'wb') as w:
            w.setnchannels(lib.libatari800_get_num_sound_channels())
            w.setsampwidth(lib.libatari800_get_sound_sample_size())
            w.setframerate(lib.libatari800_get_sound_frequency())
            w.writeframes(bytes(self.audio))
        report.write_text(json.dumps({'frames': self.frames, 'captions': self.captions}))


def still(game, out, name):
    """The screen as it is, scaled 3x, to out/stills/NAME.png."""
    from PIL import Image
    folder = out / 'stills'
    folder.mkdir(exist_ok=True)
    game.atari.screenshot(folder / '_.png')
    picture = Image.open(folder / '_.png')
    picture.resize((WIDTH * 3, HEIGHT * 3), Image.NEAREST).save(folder / f'{name}.png')
    (folder / '_.png').unlink()


def record(name, out):
    spec = SEGMENTS[name]
    layout = json.loads((build.OUT / 'layout-disks.json').read_text())
    game = lockstep.Game(dict(layout, title=False), sound=True, disks=True)
    game.title = layout['title']
    rec = Recorder(game.atari, out / f'{name}.mkv')
    seconds = lambda s: int(round(s * FPS))
    fast = spec.get('fast', 1)

    def dwell(frames):
        """Run on at normal speed and with sound, for the viewer to look."""
        rec.every = 1
        game.frames(frames)
        rec.every = fast
    if spec.get('title'):
        # the title: the C64's own program, its two frames, its tune, its scenes
        game.until(game.at_title, 'the title')
        rec.on = True
        rec.say('The title: the C64 original, running on an Atari 130XE')
        game.frames(seconds(5))
        still(game, out, 'intro-title')
        game.frames(seconds(5))
        rec.say('Space shows the title scenes')
        game.keys([0x20])
        game.frames(seconds(17))
        rec.say('Escape starts the game, which loads from disk 1')
        game.keys([0x5f])
        game.until(lambda: not game.at_title(), 'the end of the title')
        rec.on = False
    elif game.title:
        game.leave_title()
    lines = (ROOT / f"tools/traces/{spec['script']}.txt").read_text().splitlines()
    steps = lockstep.atari_steps(lines)
    recording = spec['start'] is None and not spec.get('title')
    key = seconds(spec['key'])
    label = game.label
    if spec['start'] is None:
        recording = True
        rec.on = True
        rec.every = fast
    for index, words in enumerate(steps):
        op, values = words[0], words[1:]
        if op == 'press':
            following = steps[index + 1] if index + 1 < len(steps) else []
            poll = int(following[1].lstrip('$'), 16) if following and following[0] == 'poll' else None
            game.press(int(values[0], 16), poll=poll)
            if recording and spec.get('press'):
                dwell(seconds(spec['press']))
        elif op == 'poll':
            game.poll(int(values[0].lstrip('$'), 16), int(values[1], 16))
        elif op == 'ready':
            game.ready()
            game.frames(key)
        elif op == 'wait':
            game.idle()
        elif op == 'key':
            game.keys([int(v, 16) for v in values])
        elif op == 'attach':
            if recording:
                rec.say(f'Disk {"ABCD".index(values[0]) + 1} goes into the drive')
                dwell(seconds(2.5))
            game.attach(values[0])
        elif op == 'pauses':
            game.ready()
            game.memory[label['pause_key']] = 0 if values[0] == 'off' else int(values[0], 16)
        elif op == 'restart':
            game.restart()
        elif op == 'poke':
            for i, value in enumerate(values[1:]):
                address, value = int(values[0], 16) + i, int(value, 16)
                if address == lockstep.KEY_WAIT_COUNT:
                    value = value + 1 & 255
                game.memory[address] = value
        elif op == 'skip':
            pass
        elif op == 'mark':
            mark = values[0]
            if mark == spec['start']:
                recording = True
                rec.on = True
                rec.every = fast
            if recording:
                if mark in spec['captions']:
                    rec.say(spec['captions'][mark])
                dwell(seconds(spec['hold'].get(mark, 1.0)))
                if spec['captions'].get(mark):
                    still(game, out, f'{name}-{mark}')
            if recording and mark in spec.get('inject', {}):
                rec.say(spec['inject_say'][0])
                for code in spec['inject'][mark]:
                    game.press(code)
                    dwell(seconds(spec.get('inject_dwell', 0.8)))
                game.ready()
                rec.say(spec['inject_say'][1])
                dwell(seconds(spec.get('inject_dwell', 0.8)))
                still(game, out, f'{name}-{mark}-lit')
            if mark == spec['stop']:
                break
        else:
            raise SystemExit(f'step not supported: {words}')
    rec.finish(out / f'{name}.wav', out / f'{name}.json')
    game.close()


def card(text, seconds, path, sub=''):
    """A title card: white on black, silent."""
    filters = (f"drawtext=fontfile={FONT}:text='{text}':fontcolor=white:fontsize=64:x=(w-text_w)/2:y=(h-text_h)/2-20,"
               f"drawtext=fontfile={FONT}:text='{sub}':fontcolor=0xaaaaaa:fontsize=34:x=(w-text_w)/2:y=(h/2)+60")
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'lavfi', '-i', f'color=c=black:s=1152x720:r=60:d={seconds}',
                    '-f', 'lavfi', '-i', f'anullsrc=r=44100:cl=mono:d={seconds}', '-vf', filters, '-c:v', 'libx264',
                    '-crf', '18', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-shortest', str(path)], check=True)


def finish(name, out):
    """Scale, caption and add the sound to a recorded segment."""
    report = json.loads((out / f'{name}.json').read_text())
    filters = ['scale=1152:720:flags=neighbor']
    for first, last, text in report['captions']:
        t0, t1 = first / FPS, last / FPS
        safe = text.replace('\\', '\\\\').replace("'", "’").replace(':', '\\:').replace('%', '\\%')
        filters.append(f"drawtext=fontfile={FONT}:text='{safe}':fontcolor=white:fontsize=34:box=1:boxcolor=0x000000b0:"
                       f"boxborderw=14:x=(w-text_w)/2:y=h-70:enable='between(t,{t0:.3f},{t1:.3f})'")
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', str(out / f'{name}.mkv'), '-i', str(out / f'{name}.wav'),
                    '-vf', ','.join(filters), '-r', '60', '-c:v', 'libx264', '-crf', '18', '-preset', 'medium',
                    '-pix_fmt', 'yuv420p', '-af', 'aresample=44100,volume=1.5', '-ac', '1', '-c:a', 'aac', '-b:a', '160k',
                    '-shortest', str(out / f'{name}.mp4')], check=True)
    return report['frames'] / FPS


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--out', type=Path, default=build.OUT / 'video')
    parser.add_argument('--only', nargs='*', help='segments to make (default: all)')
    parser.add_argument('--record', help=argparse.SUPPRESS)
    parser.add_argument('--no-build', action='store_true')
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    if args.record:
        record(args.record, args.out)
        return
    if not args.no_build:
        build.build_disks(test=True, title=True)
    names = args.only or list(SEGMENTS)
    lengths = {}
    for name in names:
        subprocess.run([sys.executable, __file__, '--record', name, '--out', str(args.out), '--no-build'], check=True)
        lengths[name] = finish(name, args.out)
        print(f'{name}: {lengths[name]:.1f} s', flush=True)
    parts = []
    card('Might and Magic I', 4, args.out / 'card-0.mp4', 'on the Atari 130XE')
    parts.append('card-0.mp4')
    for number, name in enumerate(names, 1):
        card(SEGMENTS[name]['card'], 2.5, args.out / f'card-{number}.mp4')
        parts += [f'card-{number}.mp4', f'{name}.mp4']
    listing = args.out / 'parts.txt'
    listing.write_text(''.join(f"file '{p}'\n" for p in parts))
    final = args.out / 'might-and-magic-atari-demo.mp4'
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'concat', '-safe', '0', '-i', str(listing), '-c', 'copy',
                    str(final)], check=True)
    print(f'{final}: {sum(lengths.values()) + 4 + 2.5 * len(names):.0f} s')


if __name__ == '__main__':
    main()
