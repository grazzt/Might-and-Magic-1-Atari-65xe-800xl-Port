#!/usr/bin/env python3
"""Check the original animated title, eight scenes and exit on a 64 KB Atari.

Default uses the four-disk build. --single, --altirra and --sio select other
loaders. Pixel checks use the original Oracle artwork and colour policy, not
the renderer's packed plans. The intro memory must be reclaimed on Escape.
"""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'tools'), str(ROOT/'port/atari')]
import build
import lockstep
import profile65
import title_check


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--single', action='store_true')
    parser.add_argument('--altirra', action='store_true')
    parser.add_argument('--sio', action='store_true')
    parser.add_argument('--out', type=Path, default=ROOT/'build/atari65xe/title-check')
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    reference = title_check.reference(ticks=0)
    layout = (build.build if args.single else build.build_disks)(test=True,title=True,xe64=True)
    game = lockstep.Game({**layout,'title':False},altirra=args.altirra,sio_patch=not args.sio,disks=not args.single,sound=not args.altirra)
    labels, memory = game.label, game.memory
    images = {name:(build.OUT/name).read_bytes() for name in build.SEGMENTS}
    stage = lambda: memory[labels['title.stage']]
    def expected_pixels(wanted):
        if not args.altirra:
            screen = getattr(game,'title_pixels',None)
            if screen is None:
                screen = game.title_pixels = title_check.Screen(game.atari)
                if not screen.find(wanted):
                    game.atari.screenshot(args.out/'failed.png')
                    raise AssertionError('Title pixels do not match the original')
            else:
                assert not screen.differences(wanted), 'Title pixels changed from their model'
        else:
            # Exact geometry and pixel roles, using the bridge's RGB palette.
            import base64
            from io import BytesIO
            from PIL import Image
            raw = base64.b64decode(game.atari.command('SCREENSHOT')['data'])
            picture = Image.open(BytesIO(raw)).convert('RGB')
            width,height = picture.size
            # Calibrate RGB against Atari800's palette via the built-in GTIA
            # colour relation. Altirra's default tint is allowed by the separate
            # per-screen role mapping, which is injective over observed colours.
            x,y=(width-320)//2,8
            data=list(picture.get_flattened_data())
            observed=[data[(y+line)*width+x:(y+line)*width+x+320] for line in range(200)]
            mapping={}
            for want,row in zip(wanted,observed):
                for a,b in zip(want,row):
                    if a in mapping and mapping[a]!=b:
                        picture.save(args.out/'failed.png')
                        raise AssertionError('Altirra title pixel differs')
                    mapping[a]=b
            assert len(set(mapping.values()))==len(mapping), 'Altirra title palette collapsed'
    def mark(name,wanted,settle=True):
        if settle:game.frames(2)
        expected_pixels(wanted)
        game.atari.screenshot(args.out/f'{name}.png')
        print(f'{name}: pixel model equal',flush=True)
    game.until(lambda: game.at_title() and stage()==0,'original title',limit=6000)
    seen=set()
    previous=None
    still=0
    observed=[]
    for _ in range(1900 if not args.altirra else 700):
        game.frames(1)
        if not args.altirra:observed.append(title_check.pokey(game.atari))
        bitmap=bytes(memory[0xe000:0xff40])
        still=still+1 if bitmap==previous else 0
        previous=bitmap
        for index,frame in enumerate(reference['frames']):
            if still>=6 and index not in seen and bitmap==frame['memory'][0xe000:0xff40] and not memory[labels['title.passes']]:
                mark(f'frame-{index+1}',title_check.as_atari(frame['picture']),settle=False)
                seen.add(index)
        if args.altirra and len(seen)==2:break
    assert seen=={0,1}, 'Both title frames were not shown'
    music_report={}
    if not args.altirra:
        _,per_tick=title_check.tune_writes(build.title_tune(),1900)
        matched,missed=title_check.check_tune(per_tick,observed,build.title_notes(build.title_tune()))
        assert matched>1860 and missed<=8,(matched,missed)
        assert all(max(o['volume'][voice] for o in observed)>=4 for voice in range(3))
        game.atari.save_audio(args.out/'tune.wav')
        music_report={'matched_ticks':matched,'late_frames':missed,'voices':3}
        print(f'tune: {matched} ticks matched, {missed} late frames',flush=True)
    game.keys([0x20])
    scenes=[]
    for scene in title_check.SCENES:
        # SCENE advances before the old scene's fresh flag has been cleared.
        # Wait for the renderer's commit, rather than that transient overlap.
        game.until(lambda:stage()==2 and memory[labels['title.fresh']]
                   and memory[labels['title.rendered_scene']]==scene+1,
                   f'scene {scene}',limit=6000)
        original=reference['scenes'][scene]['memory']
        assert bytes(memory[0xe000:0xff40])==original[0xe000:0xff40], f'scene {scene}: bitmap differs'
        assert bytes(memory[0xcc00:0xcfe8])==original[0xcc00:0xcfe8], f'scene {scene}: colour metadata differs'
        prepared=title_check.prepared(original,scene)
        _,registers,_=title_check.policy.convert(prepared,1)
        assert bytes(memory[0x1400:0x1464])==registers, f'scene {scene}: palette bytes differ'
        wanted=title_check.scene_rows(prepared)
        mark(f'scene-{scene}',wanted)
        scenes.append(scene)
    game.until(lambda:game.at_title() and stage()==0,'title loop return',limit=6000)
    game.keys([0x5f])
    game.until(lambda:'INSERT DISK B' in '\n'.join(title_check.play_check.text(game.atari)) if not args.altirra
               else b'INSERT DISK B' in bytes(memory[0x0400:0x07e8]),'disk B prompt',limit=6000)
    game.frames(2)
    assert not lockstep.kernel_changes(game.ram(),layout['fixed'],images), 'Kernel changed after Escape'
    profile65.check_display(game,'after-title')
    game.atari.screenshot(args.out/'disk-b.png')
    game.attach('B')
    game.keys([0x0d])
    game.ready()
    game.frames(2)
    profile65.check_display(game,'options')
    game.atari.screenshot(args.out/'options.png')
    report={'emulator':'AltirraSDL' if args.altirra else 'Atari800','ram_kb':64,
            'disks':1 if args.single else 4,'serial_sio':args.sio,'frames':2,'scenes':scenes,'music':music_report,
            'game_after_title':'options menu, font/display valid, immutable kernel restored'}
    (args.out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print('OK: original frames, eight scenes, loop and Escape on 64 KB',flush=True)


if __name__=='__main__':
    main()
