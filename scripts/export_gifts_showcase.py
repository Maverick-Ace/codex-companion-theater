#!/usr/bin/env python3
"""Local production-engine preview of the parcel and five collectible props."""
from pathlib import Path
import argparse,sys
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from theater.world import World
from theater.render import Renderer
from theater.gifts import decoration,parcel,place
from theater.life import DECORATIONS


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,default=ROOT/'artifacts/gifts-demo.webp')
    args=p.parse_args();r=Renderer();w=World(seed=23);frames=[]
    w.next_scene=w.next_visit=w.play.next_social=1000
    def capture(title,seconds):
        for _ in range(round(seconds*25)):
            w.tick(1/25)
            im=Image.new('RGBA',(960,200),'#211b2b');im.alpha_composite(r.frame(w.snapshot(),960,170),(0,30))
            ImageDraw.Draw(im).text((16,7),title,font=r.font(13),fill='#d5c4e5')
            frames.append(im.convert('RGB'))
    for _ in range(5):
        w.life.spawn(w);w.life.treasure['kind']='box'
        capture('飘来一份小惊喜',1.2)
        x,y=w.life.point(w);w.pointer('down',x,y)
        capture('收集到 '+DECORATIONS[w.life.selected],1.6)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    frames[0].save(args.output,save_all=True,append_images=frames[1:],duration=40,loop=0,quality=85,method=4)
    contact=Image.new('RGBA',(960,430),'#211b2b');d=ImageDraw.Draw(contact)
    for i,opened in enumerate((0,.5,1)):
        place(contact,parcel(96,opened),90+i*150,90)
    for i,(key,label) in enumerate(DECORATIONS.items()):
        place(contact,decoration(key,96),90+i*185,270)
        d.text((52+i*185,335),label,font=r.font(13),fill='#d6c5e6')
    d.text((28,172),'立体礼盒 · 缎带、蝴蝶结和可打开的盒盖',font=r.font(14),fill='#d6c5e6')
    contact.convert('RGB').save(ROOT/'artifacts/gift-preview.png')
    print(args.output)

if __name__=='__main__':main()
