"""Local day/night ambience, rest, and a small persistent decoration collection."""
from datetime import datetime
from functools import lru_cache
import fcntl
import json
import math
import os
from pathlib import Path
import tempfile
from PIL import Image,ImageDraw,ImageFilter
from .celestial import ambience

DECORATIONS={'star_lamp':'星球灯','paper_plane':'纸飞机挂饰','plant':'小花盆','moon_cushion':'月亮抱枕','star_map':'星图挂画'}

class CollectionStore:
    def __init__(self,path=None):
        self.path=Path(path) if path else Path(os.getenv('XDG_DATA_HOME',str(Path.home()/'.local/share')))/'codex-companion-theater/collection.json'

    def load(self):
        try:
            data=json.loads(self.path.read_text())
            if not isinstance(data,dict) or not isinstance(data.get('owned',[]),list):return [],None
            owned=sorted(set(data.get('owned',[]))&DECORATIONS.keys())
            return owned,data.get('selected') if data.get('selected') in owned else (owned[0] if owned else None)
        except (OSError,ValueError,TypeError):return [],None

    def save(self,owned,selected):
        self.path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        # Multiple terminal windows merge discoveries instead of overwriting them.
        with (self.path.parent/'collection.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            old,_=self.load();items=sorted((set(old)|set(owned))&DECORATIONS.keys())
            data={'v':1,'owned':items,'selected':selected if selected in items else (items[0] if items else None)}
            fd,name=tempfile.mkstemp(dir=self.path.parent,prefix='.collection-')
            try:
                with os.fdopen(fd,'w') as file:json.dump(data,file);file.flush();os.fsync(file.fileno())
                os.replace(name,self.path)
            finally:
                if os.path.exists(name):os.unlink(name)
        return data['owned'],data['selected']

class Life:
    def __init__(self):
        self.hour=datetime.now().hour;self.manual_hour=False
        self.last_touch=0.;self.sleeping=False;self.next_treasure=22.
        self.treasure=None;self.owned=[];self.selected=None;self.notice=None

    def clock(self,hour=None):
        if hour is None:self.manual_hour=False;self.hour=datetime.now().hour
        else:
            if isinstance(hour,bool) or not isinstance(hour,int) or not 0<=hour<24:raise ValueError('hour must be 0..23')
            self.manual_hour=True;self.hour=hour

    def touch(self,world):self.last_touch=world.t;self.sleeping=False

    def spawn(self,world):
        if self.treasure is None:
            self.treasure={'start':world.t,'kind':world.rng.choice(('star','plane','box'))}
            self.next_treasure=world.t+world.rng.uniform(65,100)

    def point(self,world):
        if not self.treasure:return None
        u=max(0,min(1,(world.t-self.treasure['start'])/12))
        return .09+.82*u,.13+.1*math.sin(u*math.pi)

    def pointer(self,world,kind,x,y):
        self.touch(world)
        if kind!='down' or not self.treasure or world.reduced_motion or world.paused:return False
        if world.flight or world.spectacle or world.t<world.typing_until or world.phase not in ('idle','ready') or any(a.reaction and a.reaction['kind'] in ('jump','caught','land') for a in world.actors):return False
        point=self.point(world)
        if abs(x-point[0])*world.attention.width>14 or abs(y-point[1])*world.attention.height>14:return False
        available=[k for k in DECORATIONS if k not in self.owned]
        if available:
            chosen=world.rng.choice(available);self.owned.append(chosen);self.selected=chosen
            self.notice={'text':'发现了 '+DECORATIONS[chosen],'until':world.t+2.8}
        else:self.notice={'text':'星星向你眨了眨眼','until':world.t+2.8}
        self.treasure=None
        return True

    def select(self,key):
        if key not in self.owned:raise ValueError('decoration not collected')
        self.selected=key

    def step(self,world):
        if self.notice and world.t>self.notice['until']:self.notice=None
        if self.treasure and world.t-self.treasure['start']>12:self.treasure=None
        blocked=(world.flight or world.spectacle or world.t<world.typing_until or world.phase not in ('idle','ready'))
        if blocked:self.treasure=None;self.sleeping=False;self.last_touch=world.t;return
        self.sleeping=world.t-self.last_touch>60 and world.scene in ('roam','home','tea')
        if world.t>=self.next_treasure and not world.reduced_motion and not self.sleeping:self.spawn(world)

    def snapshot(self,world):
        treasure=None
        if self.treasure:
            x,y=self.point(world);treasure={'kind':self.treasure['kind'],'x':x,'y':y,'age':world.t-self.treasure['start']}
        return {'hour':self.hour,'period':'day' if 7<=self.hour<18 else 'dusk' if 18<=self.hour<22 else 'night',
                'sleeping':self.sleeping,'treasure':treasure,'owned':sorted(self.owned),'selected':self.selected,
                'notice':self.notice['text'] if self.notice else None,'catalog':DECORATIONS}

def draw_ambience(canvas,state,floor):
    life=state.get('life')
    if not life:return
    d=ImageDraw.Draw(canvas);w,h=canvas.size
    # Keep the weather readable and local even in an extra-wide terminal.
    x,y=10,5;size=min(44,max(30,round(h*.22)))
    if life['period']=='day':
        beam=_sunbeam(size)
        canvas.alpha_composite(beam,(x,y))
    canvas.alpha_composite(ambience(life['period'],size),(x,y))
    if life['selected']:
        key=life['selected'];cx=w*.08;cy=floor-h*.12
        if key=='plant':
            d.polygon(((cx-6,cy),(cx+6,cy),(cx+4,cy+12),(cx-4,cy+12)),fill='#ae8f9f')
            d.line((cx,cy,cx,cy-14),fill='#7cac8e',width=2)
            d.ellipse((cx-9,cy-13,cx,cy-7),fill='#9cbd99');d.ellipse((cx,cy-18,cx+8,cy-12),fill='#9cbd99')
        elif key=='paper_plane':
            d.line((cx,0,cx,h*.25),fill='#c5b3cf55')
            d.polygon(((cx-13,h*.25),(cx+14,h*.25-5),(cx+1,h*.25+9)),fill='#d8d4e7',outline='#a79bbd')
        elif key=='moon_cushion':
            d.rounded_rectangle((cx-13,cy-4,cx+13,cy+12),radius=5,fill='#b5a4c9',outline='#d4c3e2')
            d.arc((cx-5,cy-1,cx+5,cy+9),60,300,fill='#f4ddb1',width=2)
        elif key=='star_map':
            d.rectangle((cx-17,10,cx+17,34),fill='#514663',outline='#9c87b0')
            d.line((cx-10,27,cx,17,cx+8,26,cx+12,15),fill='#b6b5d8',width=1)
        else:
            d.line((cx,cy-8,cx,cy+12),fill='#a596ad',width=2)
            d.ellipse((cx-8,cy-22,cx+8,cy-6),fill='#dcca9f',outline='#f1d6a0')

@lru_cache(maxsize=16)
def _sunbeam(size):
    """A short feathered highlight; never a translucent panel across the stage."""
    beam=Image.new('RGBA',(size*3,size*2));d=ImageDraw.Draw(beam)
    d.polygon(((size*.5,size*.5),(size,size*.5),(size*2.55,size*1.55),(size*1.7,size*1.55)),fill=(241,210,153,9))
    return beam.filter(ImageFilter.GaussianBlur(max(3,size*.16)))

def draw_life(canvas,state,positions,font):
    life=state.get('life')
    if not life:return
    d=ImageDraw.Draw(canvas);w,h=canvas.size
    if life['sleeping'] and not state['quiet']:
        for index,(a,(x,floor,size)) in enumerate(zip(state['cast'],positions)):
            if index%2:continue
            d.rounded_rectangle(tuple(round(v) for v in (x-size*.26,floor-size*.3,x+size*.26,floor-2)),radius=6,fill='#b6a9cdcc',outline='#d5c5e3')
            d.text((x+size*.25,max(1,floor-size*.76)),'z',font=font(max(10,round(size*.12))),fill='#bcb2cf')
    if state['quiet'] or state['reduced_motion'] or state.get('flight') or state['phase'] not in ('idle','ready'):return
    t=life['treasure']
    if t:
        x,y=t['x']*w,t['y']*h
        if t['kind']=='plane':d.polygon(((x-9,y-4),(x+11,y),(x-5,y+7),(x-2,y)),fill='#d6cdeb',outline='#a3b2d5')
        elif t['kind']=='box':
            d.rectangle((x-6,y-6,x+6,y+6),fill='#d6a6b4',outline='#f3d6b0');d.line((x,y-6,x,y+6),fill='#f3d6b0',width=2)
        else:
            points=[]
            for n in range(10):
                a=n*math.pi/5-math.pi/2;r=8 if n%2==0 else 3.5
                points.append((x+math.cos(a)*r,y+math.sin(a)*r))
            d.polygon(points,fill='#efd59d',outline='#fff0c5')
    if life['notice']:
        text=life['notice'];f=font(max(10,round(h*.07)));b=d.textbbox((0,0),text,font=f)
        d.text(((w-b[2]+b[0])/2,2),text,font=f,fill='#e5c4de')
