#!/usr/bin/env python3
"""Reproduce pointer/caret interactions with the shipped World and Renderer.

Each chapter starts a seeded production World and sends the same coordinate-only
commands as the CLI/browser. No reactions, actor positions, RNG values, draft
text, or rendered production state are fabricated or overwritten.
"""
import argparse
import json
import math
from pathlib import Path
import sys

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from theater.geometry import stage_metrics, stage_position
from theater.render import Renderer
from theater.world import World

WIDTH, HEIGHT, HEADER, COMPOSER = 1040, 190, 30, 30


def point_at(world, actor_id, relative_height=.5):
    """Use the exact stage placement shared by production hit tests and drawing."""
    state = world.snapshot()
    size, floor = stage_metrics(len(state['cast']), WIDTH, HEIGHT)
    index, actor = next((i, a) for i, a in enumerate(state['cast']) if a['id'] == actor_id)
    x, _, _ = stage_position(actor, index, len(state['cast']), WIDTH, size, floor)
    return x/WIDTH, (floor-size*relative_height)/HEIGHT


def chapter_frames(renderer, world, seconds, fps, title, events, report):
    world.set_geometry(WIDTH, HEIGHT)
    frames = []
    cursor = None
    for index in range(round(seconds*fps)):
        age = index/fps
        position, caret = events(world, age, index)
        if caret is not None:
            world.activity(typing=True, cursor=caret)
            cursor = caret
        world.tick(1/fps)
        state = world.snapshot()
        for actor in state['cast']:
            reaction = actor.get('reaction')
            if reaction:
                report['reactions'].add(reaction['kind'])
            if actor.get('attention'):
                report['input_styles'].add(actor['attention']['style'])
                if actor['attention']['look_up']:
                    report['glancers'].add(actor['id'])
            if actor['gesture'] == 'run':
                report['runners'].add(actor['id'])
        if state['pointer']['caught']:
            report['caught'].add(state['pointer']['caught'])
        canvas = Image.new('RGBA', (WIDTH, HEADER+HEIGHT+COMPOSER), '#211b2b')
        canvas.alpha_composite(renderer.frame(state, WIDTH, HEIGHT), (0, HEADER))
        draw = ImageDraw.Draw(canvas)
        draw.rectangle((0,0,WIDTH,HEADER-1), fill='#2c2335')
        draw.text((18,5),title,font=renderer.font(13),fill='#e8d9f6')
        draw.text((WIDTH-168,6),'COMPANION THEATER',font=renderer.font(10),fill='#9e8fae')
        draw.line((0,HEADER+HEIGHT,WIDTH,HEADER+HEIGHT),fill='#79628c',width=1)
        draw.rectangle((0,HEADER+HEIGHT+1,WIDTH,HEADER+HEIGHT+COMPOSER),fill='#2c2335')
        draw.text((18,HEADER+HEIGHT+5),'›',font=renderer.font(16),fill='#d7b5f6')
        if caret is not None or (cursor and state['quiet']):
            caret_x=round(cursor['x']*WIDTH)
            draw.line((40,HEADER+HEIGHT+16,max(40,caret_x-7),HEADER+HEIGHT+16),fill='#51425f',width=2)
            if index%fps < fps*.65:
                draw.line((caret_x,HEADER+HEIGHT+6,caret_x,HEADER+HEIGHT+23),fill='#f4d9ff',width=2)
        else:
            draw.text((40,HEADER+HEIGHT+7),'本地演出 · 不调用模型 API',font=renderer.font(11),fill='#9e8fae')
        if position is not None:
            px,py=position[0]*WIDTH,HEADER+position[1]*HEIGHT
            draw.polygon([(px,py),(px+1,py+17),(px+5,py+13),(px+9,py+20),
                          (px+12,py+18),(px+8,py+11),(px+15,py+10)],fill='#fbf9ff',outline='#2b2035')
        frames.append(canvas.convert('RGB'))
    return frames


def produce(fps=25):
    renderer = Renderer()
    frames = []
    report = {'reactions':set(), 'input_styles':set(), 'glancers':set(),
              'runners':set(), 'caught':set(), 'chapters':[]}

    portals = World(seed=23)
    first_cast = ['qwen','mistral','minimax','hunyuan']
    def teleport(world, age, index):
        if index == 0:
            world.set_cast(first_cast)
        elif index == round(2*fps):
            world.set_cast(['gpt','deepseek','claude','gemini'])
        return None, None
    chapters = [('01  品牌传送 · 光环点亮，伙伴出现',portals,4,teleport)]

    greetings = World(seed=9)
    def greet(world, age, index):
        actor = 'gpt' if age < 1.4 else 'claude'
        x,y = point_at(world,actor,.48)
        world.pointer('move',x,y)
        if index in (round(.6*fps),round(1.8*fps)):
            world.pointer('down',x,y)
        if index in (round(.6*fps)+1,round(1.8*fps)+1):
            world.pointer('up',x,y)
        return (x,y),None
    chapters.append(('02  轻轻划过，再点一下 · 每个人的回应都不同',greetings,2.8,greet))

    catching = World(seed=3,cast=['gpt'],density=1)
    def catch(world, age, index):
        _,y = point_at(world,'gpt',1.05)
        if age < 1.2:
            x = .5+.002*math.sin(age*3)
        elif age < 2.7:
            x = .5+.16*math.sin((age-1.2)/1.5*math.pi/2)
        elif age < 3.3:
            x = .66
        elif age < 4.1:
            x = .66+.075*math.sin((age-3.3)*22)
        else:
            world.pointer('leave')
            return None,None
        world.pointer('move',x,y)
        return (x,y),None
    chapters.append(('03  从头顶逗一逗 · 抓住后，抖抖鼠标再放下',catching,5.2,catch))

    thinking = World(seed=6)
    def type_coordinates(world, age, index):
        if age >= 7.5:
            return None,None
        if age < 1.8:
            x = .18
        elif age < 3.0:
            x = .18+.48*(age-1.8)/1.2
        elif age < 5.3:
            x = .66+.018*math.sin(age*2)
        elif age < 6.2:
            x = .66-.25*(age-5.3)/.9
        else:
            x = .41+.008*math.sin(age*1.4)
        return None,{'x':x,'y':1.08}
    chapters.append(('04  输入继续 · 跑到光标旁，一起琢磨，也抬头看看',thinking,9.6,type_coordinates))

    for title,world,seconds,events in chapters:
        report['chapters'].append({'title':title,'start_frame':len(frames),'seconds':seconds})
        frames.extend(chapter_frames(renderer,world,seconds,fps,title,events,report))
    required = {'hover','click','jump','caught','land'}
    if not required <= report['reactions'] or not report['caught']:
        raise RuntimeError(f'Showcase did not exercise all real pointer states: {report}')
    if len(report['input_styles']) < 3 or not report['runners'] or not report['glancers']:
        raise RuntimeError(f'Showcase did not exercise production caret watching: {report}')
    report = {key:sorted(value) if isinstance(value,set) else value for key,value in report.items()}
    report.update({'frames':len(frames),'fps':fps,'seconds':len(frames)/fps,
                   'size':[WIDTH,HEADER+HEIGHT+COMPOSER],
                   'engine':'production World + Renderer; coordinate-only events',
                   'logo_casts':[first_cast,['gpt','deepseek','claude','gemini']]})
    return frames,report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'artifacts/pointer-demo.webp')
    parser.add_argument('--report',type=Path,default=ROOT/'build/pointer-showcase.json')
    parser.add_argument('--fps',type=int,choices=(25,30),default=25)
    args=parser.parse_args()
    frames,report=produce(args.fps)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    frames[0].save(args.output,save_all=True,append_images=frames[1:],duration=round(1000/args.fps),
                   loop=0,quality=83,method=4)
    report['bytes']=args.output.stat().st_size
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
