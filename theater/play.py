"""Interruptible authored duets, pointer teasing and short finish celebrations."""
import math
from PIL import ImageDraw
from .geometry import stage_x,stage_metrics

DUETS={frozenset(('gpt','deepseek')):('思路图搭档','这一步，我画成图给你看。','让我把条件再拆细一点。'),
       frozenset(('claude','gemini')):('灵感便签搭档','灵感又飞出来啦！','别急，我把它们整理好。')}

class Play:
    def __init__(self):
        self.active=None;self.next_social=24.;self.next_mouse=0.;self.finish_pending=False

    def cancel(self,world):
        if self.active:
            for a in world.actors:
                if a.id in self.active['actors']:a.bubble=''
                a.play=None
        self.active=None

    def start(self,world,kind,*,wake=True):
        if kind not in ('duo','tease','finish','prank'):raise ValueError('unknown play')
        if world.flight or world.spectacle or world.t<world.typing_until or world.phase not in ('idle','ready') or world.reduced_motion or world.paused:return False
        if wake:world.life.touch(world)
        self.cancel(world)
        actors=world.actors[:]
        if not actors:return False
        if kind in ('duo','prank'):
            if len(actors)<2:return False
            pair=next((pair for pair in DUETS if pair.issubset({a.id for a in actors})),None)
            actors=[a for a in actors if a.id in pair] if pair and kind=='duo' else world.rng.sample(actors,2)
        elif kind=='tease':
            point=world.attention.point
            if point is None:return False
            actors=sorted(actors,key=lambda a:abs(a.x-point['x']))[:2]
        selected=[a.id for a in actors]
        theme=world.rng.choice(('stamp','photo','confetti','highfive')) if kind=='finish' else world.rng.choice(('book','chair','paperball')) if kind=='prank' else 'notes'
        if 'wenxin' in selected and theme=='chair':theme='paperball'
        self.active={'kind':kind,'theme':theme,'actors':selected,'start':world.t,
                     'center':max(.22,min(.78,sum(a.x for a in actors)/len(actors)+world.rng.uniform(-.1,.1))),
                     'duration':4.2 if kind=='finish' else 3.2 if kind=='tease' else 6.,'spoken':-1}
        world._clear_interactions();world._clear_entrances();world.dialogue=[]
        self.next_social=world.t+world.rng.uniform(24,42)
        return True

    def pointer(self,world,kind):
        if kind!='move' or world.t<self.next_mouse or self.active or world.phase not in ('idle','ready'):return
        p=world.attention.point
        if (not p or not .08<p['x']<.92 or not -.1<p['y']<.45
                or any(a.reaction and a.reaction['kind'] in ('jump','caught','land') for a in world.actors)):return
        self.next_mouse=world.t+10
        if world.rng.random()<.3:self.start(world,'tease')

    def step(self,world):
        for a in world.actors:a.play=None
        blocked=(world.flight or world.spectacle or world.t<world.typing_until or world.phase in ('waiting','blocked') or world.life.sleeping or world.reduced_motion)
        if blocked:
            self.cancel(world);return
        station=world.workshop.snapshot(world)
        delivery_busy=station and (not station['returning'] or station['return_age']<3)
        if self.finish_pending and world.phase in ('idle','ready') and not delivery_busy:
            self.finish_pending=False;self.start(world,'finish',wake=False)
        if not self.active and world.phase in ('idle','ready') and world.scene=='roam' and world.t>=self.next_social:
            self.start(world,world.rng.choice(('duo','prank')),wake=False)
            self.next_social=world.t+world.rng.uniform(24,42)
        event=self.active
        if not event:return
        age=world.t-event['start']
        if age>=event['duration']:
            self.cancel(world);return
        actors=[a for a in world.actors if a.id in event['actors']]
        if len(actors)!=len(event['actors']):self.cancel(world);return
        if event['kind'] in ('duo','prank'):
            cue=0 if .8<age<3 else 1 if 3.2<age<5.5 else -1
            if cue>=0 and cue!=event['spoken']:
                lines=DUETS.get(frozenset(event['actors']),('一起琢磨','你看，我发现一个小线索。','嗯嗯，我们一起试试。'))
                actor=actors[cue%len(actors)]
                personal={'gpt':'这一步，我画成图给你看。','deepseek':'让我把条件再拆细一点。','claude':'别急，我把便签整理好。','gemini':'灵感又飞出来啦！'}
                text=personal.get(actor.id,lines[cue+1]) if event['kind']=='duo' else ('借我看一眼嘛。' if cue==0 else '刚才什么都没发生哦。')
                world.say(world.actors.index(actor),text,2.0)
                event['spoken']=cue
        size,_=stage_metrics(len(world.actors),world.attention.width,world.attention.height)
        for index,a in enumerate(actors):
            if a.reaction or a.attention:continue
            center=event['center']
            target=center+(index-.5)*.14 if event['kind'] in ('duo','prank') else center+(index-(len(actors)-1)/2)*.16
            if event['kind']=='finish' and event['theme']=='highfive':
                target=center+(index-.5)*.075 if index<2 else center+.20+(index-2)*.12
            gesture='nod' if index%2 else 'think'
            if event['kind']=='tease':
                point=world.attention.point
                if not point:self.cancel(world);return
                target=stage_x(point['x']*world.attention.width+(index-.5)*size*.5,world.attention.width,size)
                gesture='peek' if age<2.3 else 'rest'
            elif event['kind']=='finish':gesture='clap' if event['theme']!='photo' else 'peek'
            elif event['kind']=='prank':gesture='peek' if age>3 else 'reach'
            a.job=None
            a.depth_target=actors[0].depth
            a.target=max(.07,min(.93,target))
            a.play={'kind':event['kind'],'theme':event['theme'],'gesture':gesture,'age':age,'role':index,
                    'bob':0 if a.id=='wenxin' else max(0,math.sin(age*5+index))*3 if event['kind']=='tease' else 0}
            if event['kind'] in ('duo','prank'):a.facing=1 if index==0 else -1

    def snapshot(self,world):
        if not self.active:return None
        return {k:v for k,v in self.active.items() if k not in ('start','spoken')}|{'age':world.t-self.active['start']}

def draw_play(canvas,state,positions,font):
    event=state.get('play')
    if not event or state['quiet'] or state['reduced_motion']:return
    d=ImageDraw.Draw(canvas);age=event['age'];w,h=canvas.size
    pair=[(a,p) for a,p in zip(state['cast'],positions) if a['id'] in event['actors']]
    if not pair:return
    center=sum(p[0] for a,p in pair)/len(pair);floor=positions[0][1];u=h/160
    if event['kind']=='duo':
        for a,(x,f,size) in pair:
            y=f-size*.35
            if a['id']=='deepseek':
                d.ellipse((x+7*u,y-5*u,x+21*u,y+9*u),outline='#b7d6ed',width=2)
                d.line((x+19*u,y+7*u,x+26*u,y+15*u),fill='#acbedb',width=2)
            else:
                d.rectangle((x-16*u,y-3*u,x+16*u,y+15*u),fill='#eee4c8',outline='#c2aed6')
                d.line((x-10*u,y+3*u,x+2*u,y+3*u,x+8*u,y+9*u),fill='#a28eb8',width=1)
        if any(a['id']=='gemini' for a,p in pair):
            for n in range(3):
                x=center+math.sin(age*1.8+n)*30*u;y=floor-h*.7+math.cos(age+n)*7*u
                d.rectangle((x-4,y-3,x+4,y+3),fill=('#e5b8c8','#b8dcca','#d0c5e8')[n])
    elif event['kind']=='prank':
        theme=event['theme'];y=floor-h*.3
        if theme=='paperball':
            x=center+math.sin(age*3)*h*.23;py=y-abs(math.sin(age*3))*h*.25
            d.ellipse((x-5,py-5,x+5,py+5),fill='#eee5f6',outline='#a89ab8')
        elif theme=='chair':
            d.rounded_rectangle((center-18,y+6,center+18,y+12),radius=3,fill='#a28caf',outline='#cfb7df')
            d.line((center-12,y+12,center-12,floor),fill='#8a7597',width=2)
            d.line((center+12,y+12,center+12,floor),fill='#8a7597',width=2)
        else:
            x=pair[0][1][0]+(12 if age<3 else -12)
            d.polygon(((x-10,y),(x,y-3),(x+10,y),(x+10,y+14),(x,y+10),(x-10,y+14)),fill='#d5b99e',outline='#e8d7c3')
    elif event['kind']=='tease' and len(pair)>1 and abs(pair[0][1][0]-pair[1][1][0])<h*.7 and age>1.3:
        y=floor-h*.82
        d.line((center-4,y-5,center+4,y+5),fill='#ffd8a3',width=2)
        d.line((center+4,y-5,center-4,y+5),fill='#ffd8a3',width=2)
    elif event['kind']=='finish':
        theme=event['theme'];y=floor-h*.75
        if theme=='stamp':
            d.ellipse((center-22,y-16,center+22,y+16),outline='#d5b8a8',width=2)
            d.text((center-12,y-9),'完成',font=font(max(9,round(h*.075))),fill='#efd3bb')
        elif theme=='photo':
            x=w*.86;cy=floor-h*.3
            d.rounded_rectangle((x-13,cy-9,x+13,cy+8),radius=3,fill='#a09bb9',outline='#d6c9ec')
            d.ellipse((x-5,cy-5,x+5,cy+5),fill='#8db7cc',outline='#e9e1f1')
            if 1<age<1.2:d.line((x-20,cy-15,x-28,cy-24),fill='#ffe8bd',width=3)
        elif theme=='highfive' and len(pair)>1:
            mid=(pair[0][1][0]+pair[1][1][0])/2
            d.arc((mid-10,y-5,mid+10,y+12),190,350,fill='#f5d7ac',width=2)
            for n in range(3):
                x=mid+(n-1)*9;dy=math.sin(age*4+n)*2
                d.line((x,y-8+dy,x,y-13+dy),fill='#e6c7ef',width=2)
        else:
            for n in range(12):
                x=center+math.sin(n*2.4)*h*.8;p=y+(age*.22+n*.12)%1*h*.3
                d.rectangle((x,p,x+2,p+3),fill=('#d6b3ef','#eac596','#a9d8cc')[n%3])
