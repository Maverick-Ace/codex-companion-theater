#!/usr/bin/env python3
"""Export the actual renderer's deterministic Max/Ultra and everyday showcase."""
import argparse
from pathlib import Path
import sys
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from theater.world import World
from theater.render import Renderer


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'artifacts/ensemble-demo.webp')
    args=parser.parse_args()
    world=World(seed=23)
    renderer=Renderer()
    frames=[]
    for action,value,seconds in [('effort','max',3.2),('effort','ultra',3.7),
                                  ('scene','home',2),('scene','office',2),
                                  ('scene','dinner',2.5),('scene','outing',2.5),
                                  ('scene','photo',2.5),('scene','stargaze',2.5)]:
        if action=='effort':world.set_effort(value)
        else:world.start_scene(value)
        for _ in range(round(seconds*25)):
            world.tick(1/25)
            image=renderer.frame(world.snapshot(),960,200)
            # One transparent source frame per runtime update, on preview backdrop.
            backdrop=Image.new('RGBA',image.size,'#211b2b')
            backdrop.alpha_composite(image)
            frames.append(backdrop.convert('RGB'))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    frames[0].save(args.output,save_all=True,append_images=frames[1:],duration=40,loop=0,quality=82,method=4)
    print(f'{args.output}: {len(frames)} frames, 25 FPS export; live renderer targets 30 FPS')


if __name__=='__main__':main()
