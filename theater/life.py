"""Idle rest and a small persistent collection of stage decorations."""
from datetime import datetime
import fcntl
import json
import math
import os
from pathlib import Path
import tempfile
from PIL import Image,ImageDraw
from .gifts import decoration,floating,place

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

def draw_decorations(canvas,state,floor):
    life=state.get('life')
    if not life or not life['selected']:return
    w,h=canvas.size;side=max(30,min(66,round(h*.43)))
    tile=decoration(life['selected'],side)
    place(canvas,tile,max(side*.6,w*.08),floor-side/2)

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
        side=max(28,min(38,round(h*.20)))
        tile=floating(t['kind'],side).rotate(math.sin(t['age']*1.8)*6,resample=Image.Resampling.BICUBIC,expand=True)
        fade=min(1,t['age']/.3,max(0,(12-t['age'])/.5))
        if fade<1:
            tile=tile.copy();tile.putalpha(tile.getchannel('A').point(lambda a:round(a*fade)))
        place(canvas,tile,x,y)
    if life['notice']:
        text=life['notice'];f=font(max(10,round(h*.07)));b=d.textbbox((0,0),text,font=f)
        d.text(((w-b[2]+b[0])/2,2),text,font=f,fill='#e5c4de')
