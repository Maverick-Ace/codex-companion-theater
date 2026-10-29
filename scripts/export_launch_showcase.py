#!/usr/bin/env python3
"""Deterministic production-engine launch preview; no model requests or draft text."""
from pathlib import Path
import argparse
import json
import sys
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from theater.world import World
from theater.render import Renderer

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'artifacts/rocket-demo.webp')
    args=parser.parse_args()
    renderer=Renderer();frames=[];phases=set()
    contact=Image.new('RGB',(1040,4*210),'#211b2b')
    for row,model in enumerate(('gpt-6.1-sol','gpt-6.1-terra','gpt-6-luna','gpt-6-astra')):
        w=World(seed=23);w.activity('working');w.submit(model)
        for i in range(200):
            w.tick(1/25);state=w.snapshot()
            im=Image.new('RGBA',(1040,210),'#211b2b')
            im.alpha_composite(renderer.frame(state,1040,180),(0,30))
            d=ImageDraw.Draw(im)
            d.text((18,6),model+' · '+(state['flight']['phase'] if state['flight'] else '继续工作'),font=renderer.font(12),fill='#dfd0ef')
            if state['flight']:phases.add(state['flight']['phase'])
            if i==125:contact.paste(im.convert('RGB'),(0,row*210))
            if row<2:frames.append(im.convert('RGB'))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    frames[0].save(args.output,save_all=True,append_images=frames[1:],duration=40,loop=0,quality=86,method=4)
    out=ROOT/'build/rocket-contact.png';contact.save(out)
    (ROOT/'build/rocket-showcase.json').write_text(json.dumps(dict(frames=len(frames),fps=25,phases=sorted(phases),bytes=args.output.stat().st_size),indent=2))
    print(args.output)

if __name__=='__main__':main()
