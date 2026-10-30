#!/usr/bin/env python3
"""Production-engine preview of independent routes, depth and input interruption."""
from pathlib import Path
import argparse,sys
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from theater.world import World
from theater.render import Renderer


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,default=ROOT/'artifacts/roaming-demo.webp');a=p.parse_args()
    w=World(seed=31);r=Renderer();frames=[];contact=Image.new('RGB',(960,800),'#211b2b')
    w.next_scene=w.next_visit=w.play.next_social=w.life.next_treasure=1000
    for i in range(350):
        if 6<=w.t<8:w.activity(typing=True,cursor={'x':.68,'y':1.1})
        w.tick(1/25)
        title='各自找一条路线 · 自由走动' if w.t<6 else '看看你正在写什么' if w.t<9.5 else '继续散步 · 每个人有自己的节奏'
        im=Image.new('RGBA',(960,200),'#211b2b');im.alpha_composite(r.frame(w.snapshot(),960,170),(0,30))
        ImageDraw.Draw(im).text((16,6),title,font=r.font(13),fill='#d6c4e7');frames.append(im.convert('RGB'))
        if i in (0,95,195,330):contact.paste(im.convert('RGB'),(0,(0,95,195,330).index(i)*200))
    a.output.parent.mkdir(parents=True,exist_ok=True)
    frames[0].save(a.output,save_all=True,append_images=frames[1:],duration=40,loop=0,quality=85,method=4)
    contact.save(ROOT/'build/roaming-perf/contact.png');print(a.output)

if __name__=='__main__':main()
