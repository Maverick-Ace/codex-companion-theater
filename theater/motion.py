"""Continuous, weighted puppet joints over the original transparent artwork.

The inverse mesh samples one continuous surface, so limbs do not detach and
transparent pixels never wrap. Joint positions can be tuned per character.
"""
import json
import math
from pathlib import Path
from PIL import Image

PROFILES = json.loads((Path(__file__).resolve().parents[1] / 'config/rigs.json').read_text())


def joint_motion(actor, t):
    """Return joint displacement/rotation, in normalized artwork coordinates."""
    profile = PROFILES.get(actor['id'], {})
    phase = t * float(actor.get('tempo', 1)) * 2.8
    gesture = actor.get('gesture', 'sway')
    walking = actor['pose'].startswith('walk')
    gait = actor.get('travel', 0) * 65 if walking else phase * .38
    facing = actor.get('facing', 1)
    lift = .025 if gesture in ('wave', 'clap', 'reach') else .008
    if gesture == 'type':
        lift = .012
    joints = [
        # name, pivot x/y, radius x/y, angle radians, translation x/y
        ('head', .50, .43, .24, .31, math.sin(phase*.53)*.018, 0, math.sin(phase*.64)*.002),
        ('hair_left', .23, .30, .16, .37, math.sin(phase*.83+.7)*.035, math.sin(phase*.9)*.005, 0),
        ('hair_right', .77, .30, .16, .37, math.sin(phase*.83+2)*.035, math.sin(phase*.9+1)*.005, 0),
        ('arm_left', .31, .50, .16, .22, math.sin(gait+math.pi)*(.12 if walking else .045), 0, -max(0,math.sin(phase))*lift),
        ('arm_right', .69, .50, .16, .22, math.sin(gait)*(.12 if walking else .045), 0, -max(0,math.sin(phase+1))*lift),
        ('hem', .50, .70, .36, .14, math.sin(gait)*.024, math.sin(gait)*.004, 0),
        ('foot_left', .42, .83, .12, .14, math.sin(gait)*.08 if walking else 0, math.sin(gait)*.008 if walking else 0, -max(0,math.sin(gait))*.010 if walking else 0),
        ('foot_right', .58, .83, .12, .14, -math.sin(gait)*.08 if walking else 0, -math.sin(gait)*.008 if walking else 0, -max(0,-math.sin(gait))*.010 if walking else 0),
    ]
    if gesture in ('nod', 'think', 'peek'):
        name,x,y,rx,ry,angle,dx,dy=joints[0]
        joints[0]=(name,x,y,rx,ry,angle+math.sin(phase*1.3)*.035*facing,dx,dy+.006*math.sin(phase*1.3))
    result=[]
    for name,x,y,rx,ry,angle,dx,dy in joints:
        side = 1 if name == 'arm_left' else -1
        if name in ('arm_left', 'arm_right'):
            if gesture == 'clap':
                dx += side * (.012 + .013 * math.sin(phase * 2))
                dy -= .014
            elif gesture == 'type':
                dy += math.sin(phase * 4 + side) * .006
                dx += side * .008
            elif gesture in ('water','stir','serve','unpack','write'):
                if side == -facing:
                    dx += .018*facing
                    dy += .01 + math.sin(phase*(1.7 if gesture=='write' else .8))*.008
                    angle += math.sin(phase*1.4)*.045
            elif gesture in ('sip','read'):
                dx += side*.014
                dy -= .008 + max(0,math.sin(phase*.65))*.009
            elif gesture == 'reach':
                dx -= side * .014 * (.7 + .3 * math.sin(phase))
            elif gesture == 'wave' and side == -1:
                angle += math.sin(phase * 2) * .15
                dy -= .024
        override=profile.get(name,{})
        if override.get('locked'):
            continue
        gain=override.get('gain',1)
        result.append((override.get('x',x),override.get('y',y),rx,ry,angle*gain,dx*gain,dy*gain))
    return result


class PuppetRig:
    """An eight-joint soft rig evaluated at elapsed time, independent of FPS."""
    def __init__(self):
        self.grids={}

    def animate(self, sprite, actor, t, still=False):
        if still:
            return sprite
        w,h=sprite.size
        pad=max(3,round(h*.055))
        base=Image.new('RGBA',(w+pad*2,h+pad*2))
        base.alpha_composite(sprite,(pad,pad))
        key=(actor['id'],base.size)
        joints=joint_motion(actor,t)
        if key not in self.grids:
            xs=[round(i*base.width/8) for i in range(9)]
            ys=[round(i*base.height/10) for i in range(11)]
            vertices=[(x,y) for y in ys for x in xs]
            weighted=[]
            for px,py in vertices:
                x,y=(px-pad)/w,(py-pad)/h
                terms=[]
                for jx,jy,rx,ry,_,_,_ in joints:
                    vx,vy=x-jx,y-jy
                    weight=math.exp(-2*((vx/rx)**2+(vy/ry)**2))
                    terms.append((-vy*weight*w,weight*w,vx*weight*h,weight*h))
                weighted.append((px,py,terms))
            cells=[]
            for j in range(10):
                for i in range(8):
                    cells.append(((xs[i],ys[j],xs[i+1],ys[j+1]),
                                  (j*9+i,(j+1)*9+i,(j+1)*9+i+1,j*9+i+1)))
            self.grids[key]=(weighted,cells)
        weighted,cells=self.grids[key]
        transforms=[(angle,tx,ty) for _,_,_,_,angle,tx,ty in joints]
        points=[]
        for px,py,terms in weighted:
            dx=dy=0
            for (ax,wx,ay,wy),(angle,tx,ty) in zip(terms,transforms):
                dx+=ax*angle+wx*tx
                dy+=ay*angle+wy*ty
            points.append((px-dx,py-dy))
        mesh=[(box,tuple(c for index in indices for c in points[index])) for box,indices in cells]
        return base.transform(base.size,Image.Transform.MESH,mesh,Image.Resampling.BICUBIC)
