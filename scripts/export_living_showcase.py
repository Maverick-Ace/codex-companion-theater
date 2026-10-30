#!/usr/bin/env python3
"""Show all three batches through the production world and renderer, entirely local."""
from pathlib import Path
import argparse
import json
import sys
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from theater.world import World
from theater.render import Renderer
from theater.life import DECORATIONS


def advance(world,seconds):
    for _ in range(round(seconds*60)):world.tick(1/60)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,default=ROOT/'artifacts/living-demo.webp')
    args=p.parse_args();r=Renderer();frames=[];contacts=[];seen=[]
    def capture(w,title,seconds=2):
        for i in range(round(seconds*25)):
            w.tick(1/25);state=w.snapshot()
            im=Image.new('RGBA',(1040,210),'#211b2b')
            im.alpha_composite(r.frame(state,1040,180),(0,30))
            ImageDraw.Draw(im).text((18,6),title,font=r.font(13),fill='#dfd0ef')
            frames.append(im.convert('RGB'))
            if i==round(seconds*25)//2:contacts.append(im.convert('RGB'))
        seen.append(title)
    w=World(seed=23);w.life.clock(10);w.activity('working')
    for kind,title in (('read','第一批 · 一起读文件'),('search','第一批 · 放大镜查线索'),('command','第一批 · 小队跑命令'),('edit','第一批 · 记下修改')):
        w.work_event(kind);capture(w,title,1.4)
    w.submit('gpt-6.1-sol');advance(w,8)
    w.activity('ready');w.work_event('complete');capture(w,'第一批 · 带着礼物返航',4.4)
    for cast,title in ((['gpt','deepseek'],'第二批 · 思路图搭档'),(['claude','gemini'],'第二批 · 飞舞的灵感便签')):
        w=World(seed=31,cast=cast,density=2);advance(w,1.3);w.play.start(w,'duo')
        capture(w,title,3)
    w=World(seed=13);advance(w,1.3);w.play.start(w,'prank');w.play.active['theme']='paperball'
    capture(w,'第二批 · 谁把纸团丢过来啦',2.5)
    w.play.start(w,'finish');w.play.active['theme']='photo';capture(w,'第二批 · 收工合影',1.6)
    w=World(seed=19);w.next_scene=w.next_visit=w.play.next_social=1000
    w.life.clock(23);advance(w,61);capture(w,'第三批 · 夜晚盖好小毯子',2)
    w.pointer('move',.95,.4);w.life.spawn(w);capture(w,'第三批 · 点一下飘过的星星',1.5)
    x,y=w.life.point(w);w.pointer('down',x,y);capture(w,'第三批 · 惊喜变成一件收藏',2)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    frames[0].save(args.output,save_all=True,append_images=frames[1:],duration=40,loop=0,quality=84,method=4)
    contact=Image.new('RGB',(1040,len(contacts)*210),'#211b2b')
    for i,im in enumerate(contacts):contact.paste(im,(0,i*210))
    contact.save(ROOT/'build/living-showcase-contact.png')
    (ROOT/'build/living-showcase.json').write_text(json.dumps(dict(frames=len(frames),fps=25,scenes=seen,bytes=args.output.stat().st_size),ensure_ascii=False,indent=2))
    print(args.output)

if __name__=='__main__':main()
