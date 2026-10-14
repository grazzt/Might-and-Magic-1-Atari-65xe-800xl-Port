#!/usr/bin/env python3
"""Run the original nine effects on Atari800; check POKEY and record real PCM.

python3 port/atari/sound_check.py [--out build/atari/sound]
Subroutine calls use a temporary trampoline in unused kernel padding. It saves
registers and flags, so a return to a held key-wait branch preserves its result.
The original game's instructions and data are never patched.
"""
import argparse
import ctypes
import json
from pathlib import Path
import sys
import wave

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'tools'), str(ROOT / 'port/atari')]
import build
import c64_sound
import lockstep


def call(game, address, a=0):
    emulator, mem = game.atari, game.memory
    state = emulator.cpu()
    start = game.label['probe_scratch']
    result = start + 24
    code = bytes([0x08, 0x48, 0x8a, 0x48, 0x98, 0x48, 0xa9, a,
                  0x20, address & 255, address >> 8, 0x8d, result & 255, result >> 8, 0x68, 0xa8, 0x68,
                  0xaa, 0x68, 0x28, 0x4c, state['PC'] & 255, state['PC'] >> 8])
    assert result < 0xe000, 'No unused kernel padding for the test trampoline'
    mem[start:start + len(code)] = code
    ctypes.c_uint16.in_dll(emulator._lib, 'CPU_regPC').value = start
    game.frames(1)
    return mem[result]


def pcm_range(path):
    with wave.open(str(path), 'rb') as audio:
        raw, size = audio.readframes(audio.getnframes()), audio.getsampwidth()
    if size == 1:
        samples = list(raw)
    elif size == 2:
        import array
        samples = array.array('h', raw)
    else:
        raise AssertionError(f'Unexpected sample width {size}')
    assert samples, 'Emulator recorded no PCM samples'
    return max(samples) - min(samples)


def check(out):
    out.mkdir(parents=True, exist_ok=True)
    layout = build.build(test=True)
    game = lockstep.Game(layout, sound=True)
    game.frames(300)
    game.memory[game.label['side']] = 1     # same side-B swap as the lockstep script
    game.keys([0x0d])
    game.ready()
    emulator, mem, label = game.atari, game.memory, game.label
    audc = (ctypes.c_ubyte * 8).in_dll(emulator._lib, 'POKEY_AUDC')
    audf = (ctypes.c_ubyte * 8).in_dll(emulator._lib, 'POKEY_AUDF')
    audctl = (ctypes.c_ubyte * 2).in_dll(emulator._lib, 'POKEY_AUDCTL')
    effects = c64_sound.decode(mem)
    fixed_images = {name: (build.OUT / name).read_bytes() for name in build.SEGMENTS}
    report = {'effects': [], 'interruptions': []}

    for effect in effects:
        call(game, 0xc62f)
        emulator.audio.clear()
        call(game, 0xc557, effect['effect'])
        frames, audible, released = 0, 0, 0
        while mem[0x03a0]:
            assert frames < 1500, f"Effect {effect['effect']} did not finish"
            frequency = mem[label['fake_sid']] | mem[label['fake_sid'] + 1] << 8
            if audc[1] & 15:
                audible += 1
                assert audctl[0] == 0x50 and audc[0] == 0
                assert audf[0] | audf[1] << 8 == c64_sound.divisor(frequency), 'Wrong pitch'
                if not mem[label['fake_sid'] + 4] & 1:
                    released += 1
            game.frames(1)
            frames += 1
        assert audible, (f"Effect {effect['effect']} is silent after {frames} frames: "
                         f"SID {list(mem[label['fake_sid']:label['fake_sid'] + 7])}, "
                         f"POKEY {list(audc)}, option {mem[0x03a1]}, PC {emulator.cpu()['PC']:04x}")
        assert audc[1] & 15 == 0, 'Effect ended but POKEY is still audible'
        game.frames(24)                   # include filter settling and silence in the WAV
        path = out / f"effect-{effect['effect']}.wav"
        emulator.save_audio(path)
        amplitude = pcm_range(path)
        assert amplitude > 100, f'{path}: no audible PCM'
        assert not lockstep.kernel_changes(mem, layout['fixed'], fixed_images), 'Kernel was overwritten'
        report['effects'].append({'effect': effect['effect'], 'frames': frames,
                                  'audible_frames': audible, 'release_frames': released,
                                  'pcm_range': amplitude})
        print(f"ok: effect {effect['effect']}: {frames} frames, PCM range {amplitude}")
    assert any(e['release_frames'] for e in report['effects']), 'Gate-off release was never audible'

    # Exercise the original key reader, including the three special effects.
    for effect, key, stopped in [(3, 0x20, True), (5, 0x01, False), (5, 0x20, True),
                                 (6, 0x20, False), (6, 0x0d, True), (9, 0x0d, False)]:
        call(game, 0xc62f)
        call(game, 0xc557, effect)
        game.frames(6)
        game.keys([key])
        returned = call(game, 0xc648)
        assert bool(mem[0x03a0]) == (not stopped), f'Effect {effect}, key {key:02x}: wrong interruption'
        assert returned == (0 if effect == 5 and key == 1 else key), 'Wrong key returned by the sound exception'
        if stopped:
            assert audc[1] & 15 == 0, 'Key stopped the game effect but not POKEY'
        report['interruptions'].append({'effect': effect, 'key': key, 'stopped': stopped})
    call(game, 0xc62f)
    mem[0x03a1] = 1
    call(game, 0xc557, 3)
    assert mem[0x03a0] == 0 and audc[1] & 15 == 0, 'Sound-off option did not silence the effect'
    mem[0x03a1] = 0
    print('ok: key interruptions, effects 5/6/9 exceptions, sound-off option')
    (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=build.OUT / 'sound')
    args = parser.parse_args()
    check(args.out)


if __name__ == '__main__':
    main()
