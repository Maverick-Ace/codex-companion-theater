"""Task metadata becomes tiny crew jobs and one bounded return delivery."""
import math
from PIL import Image,ImageDraw
from .launch import _planet, _rocket, _paste, destination, ease

KINDS={'think','read','search','command','edit','tool','complete','interrupted','failed','idle'}

class Workshop:
    def __init__(self):
        self.kind='idle';self.changed=-10.;self.mission=None

    def submit(self, world):
        self.kind='think';self.changed=world.t
        self.mission={'destination':destination(world.model),'model':world.model,'start':world.t,
                      'complete':False,'return_start':None}

    def event(self, world, kind):
        if kind not in KINDS:raise ValueError('unknown work activity')
        self.kind,self.changed=kind,world.t
        if self.mission:
            if kind=='complete':self.mission['complete']=True
            elif kind in ('failed','interrupted'):self.mission=None

    def step(self, world):
        m=self.mission
        if m and m['complete'] and not world.flight and m['return_start'] is None:
            m['return_start']=world.t
        if m and m['return_start'] is not None and world.t-m['return_start']>6:
            self.mission=None
        for index,a in enumerate(world.actors):
            a.job=None
            if (world.phase!='working' or world.flight or world.spectacle or world.reduced_motion
                    or world.t<world.typing_until or a.reaction or a.attention):continue
            # Distinct roles rotate per actual activity; idle CPU never invents tool work.
            kind=self.kind if world.t-self.changed<6 else 'think'
            a.job={'kind':kind,'role':index%3,'age':world.t-self.changed}

    def snapshot(self, world):
        m=self.mission
        if not m:return None
        return dict(destination=dict(m['destination']), age=world.t-m['start'],
                    returning=m['return_start'] is not None,
                    return_age=None if m['return_start'] is None else world.t-m['return_start'])

def draw_jobs(canvas,state,positions):
    if state['quiet'] or state['reduced_motion'] or state.get('flight'):return
    d=ImageDraw.Draw(canvas);t=state['time']
    for a,(x,floor,size) in zip(state['cast'],positions):
        job=a.get('job')
        if not job:continue
        y=floor-size*.35;u=size/100;role=job['role'];kind=job['kind']
        if kind in ('read','search'):
            d.polygon([(x-13*u,y),(x,y-4*u),(x+13*u,y),(x+13*u,y+15*u),(x,y+12*u),(x-13*u,y+15*u)],fill='#e8d9b9',outline='#9e86b1')
            d.line((x,y-3*u,x,y+12*u),fill='#b9a3b1',width=1)
            if role==1:
                d.ellipse((x+8*u,y-8*u,x+21*u,y+5*u),outline='#acd5ec',width=2)
                d.line((x+19*u,y+4*u,x+25*u,y+11*u),fill='#c6bfd9',width=2)
            else:
                for n in range(3):d.line((x-10*u,y+3*u+n*3*u,x-3*u,y+2*u+n*3*u),fill='#bca588')
        elif kind in ('command','tool'):
            d.rounded_rectangle(tuple(round(v) for v in (x-17*u,y-1*u,x+17*u,y+16*u)),radius=3,fill='#384058',outline='#b9b5db')
            for n in range(3):d.line((x-12*u,y+3*u+n*4*u,x+(4+5*math.sin(t*3+n))*u,y+3*u+n*4*u),fill='#96ddc9')
            if role==1:
                gy=floor-size*.65
                d.rounded_rectangle(tuple(round(v) for v in (x-12*u,gy,x+12*u,gy+7*u)),radius=2,outline='#b8d9eb',width=1)
        elif kind=='edit':
            d.rectangle((x-12*u,y-2*u,x+12*u,y+16*u),fill='#e4dbec',outline='#a697ba')
            px=x+7*u+math.sin(t*4)*3*u
            d.line((px,y-5*u,px-7*u,y+9*u),fill='#edb97f',width=2)
        elif role==0:
            for n in range(3):
                dy=math.sin(t*2+n)*2
                d.ellipse((x+13*u+n*4*u,y-40*u+dy,x+15*u+n*4*u,y-38*u+dy),fill='#c9b7dc90')

def draw_station(canvas,state,floor,font):
    station=state.get('station')
    if not station or state.get('flight') or state['quiet']:return
    w,h=canvas.size;target=station['destination'];cx=w*.88;cy=h*.24
    reduced=state['reduced_motion'];d=ImageDraw.Draw(canvas)
    _paste(canvas,_planet(target['kind'],target['color'],target['light'],max(10,round(h*.17))),cx,cy)
    age=station['return_age']
    if not station['returning']:
        # A small tracking telescope and one discrete beacon.
        d.line((w*.91,floor,w*.93,floor-h*.2),fill='#9ba4bd',width=2)
        d.line((w*.93,floor-h*.2,w*.97,floor-h*.29),fill='#c4c7dd',width=4)
        theta=0 if reduced else station['age']*1.4
        _paste(canvas,_rocket(h*.10,target['color']),cx+math.cos(theta)*h*.25,cy+math.sin(theta)*h*.12)
        return
    progress=ease(age/2.7)
    x=cx+(w*.54-cx)*progress;y=cy+(floor-h*.12-cy)*progress-math.sin(progress*math.pi)*h*.15
    if age<2.7:
        _paste(canvas,_rocket(h*.15,target['color']).rotate(160,expand=True),x,y)
    else:
        x=w*.54;y=floor-h*.12
        d.rounded_rectangle(tuple(round(v) for v in (x-11,y-7,x+11,y+9)),radius=2,fill='#e7b1ad',outline='#ffe0b8')
        d.line((x,y-7,x,y+9),fill='#ffedba',width=2)
        d.line((x-11,y,x+11,y),fill='#ffedba',width=2)
        if not reduced:
            for n in range(7):
                angle=n*2.399;radius=h*.2*ease((age-2.7)/.7)
                px=x+math.cos(angle)*radius;py=y-12+math.sin(angle)*radius*.6
                d.ellipse((px-1,py-1,px+1,py+1),fill=target['light'])
        label='返航礼物到啦'
        f=font(max(9,round(h*.065)));box=d.textbbox((0,0),label,font=f)
        d.text((x-(box[2]-box[0])/2,max(0,y-h*.23)),label,font=f,fill='#efd5d3')
