"""Code-drawn miniature sets and short, transparent celebration effects."""
import math
from PIL import Image, ImageDraw, ImageFilter, ImageColor


from functools import lru_cache
from .props import prop_layout


class _SetPainter:
    def __init__(self, canvas, name, floor, size, factor=1):
        self.draw=ImageDraw.Draw(canvas)
        self.factor=factor
        self.floor=floor*factor
        self.unit=max(.65,min(1.8,size/110))*factor
        self.anchors=prop_layout(name,canvas.width//factor,floor,size)

    def point(self, prop, x, y):
        return self.anchors[prop]['x']*self.factor+x*self.unit,self.floor-y*self.unit

    def polygon(self, prop, points, fill, outline=None):
        self.draw.polygon([self.point(prop,*p) for p in points],fill=fill,outline=outline)

    def line(self, prop, points, color, width=1):
        self.draw.line([self.point(prop,*p) for p in points],fill=color,width=max(1,round(width*self.unit)),joint='curve')

    def rect(self, prop, x, y, width, height, fill, outline=None, radius=3):
        x0,y0=self.point(prop,x-width/2,y+height)
        x1,y1=self.point(prop,x+width/2,y)
        box=tuple(round(v) for v in (x0,y0,x1,y1))
        r=max(0,min(round(radius*self.unit),(box[2]-box[0])//2,(box[3]-box[1])//2))
        self.draw.rounded_rectangle(box,radius=r,fill=fill,outline=outline,width=max(1,round(self.unit)))

    def ellipse(self, prop, x, y, rx, ry, fill, outline=None, width=1):
        x0,y0=self.point(prop,x-rx,y+ry)
        x1,y1=self.point(prop,x+rx,y-ry)
        self.draw.ellipse((x0,y0,x1,y1),fill=fill,outline=outline,width=max(1,round(width*self.unit)))

    def arc(self, prop, x, y, rx, ry, start, end, color, width=1):
        x0,y0=self.point(prop,x-rx,y+ry)
        x1,y1=self.point(prop,x+rx,y-ry)
        self.draw.arc((x0,y0,x1,y1),start,end,fill=color,width=max(1,round(width*self.unit)))


def _cup(p, prop='teacup', y=39):
    p.ellipse(prop,0,y-12,12,2,'#65526128')
    p.ellipse(prop,8,y-3,5,5,None,'#c1c7d3',1.5)
    p.rect(prop,0,y-10,14,12,'#a3bec8','#d7dbe2',3)
    p.ellipse(prop,0,y+2,7,2.5,'#e6d5bc','#e5e1d8')
    p.ellipse(prop,0,y+2,5,1.5,'#ad8066')
    p.line(prop,[(-4,y-3),(-4,y-7)],'#d4e1e0')
    p.ellipse(prop,0,y-12,11,2,'#b8a3b7')


def _book(p, prop='book', y=44):
    p.polygon(prop,[(-17,y+4),(-2,y+1),(0,y-3),(2,y+1),(17,y+4),(17,y-8),(1,y-12),(-17,y-8)],'#887898','#c0aeca')
    p.polygon(prop,[(-15,y+5),(-1,y+1),(-1,y-10),(-15,y-6)],'#ddd3bd')
    p.polygon(prop,[(1,y+1),(15,y+5),(15,y-6),(1,y-10)],'#f0dfc5')
    p.line(prop,[(0,y+1),(0,y-11)],'#a995a4')
    for side in (-1,1):
        for row in range(3):
            p.line(prop,[(side*4,y-1-row*2),(side*12,y+1-row*2)],'#b7a9aa',.5)
    p.polygon(prop,[(8,y-7),(11,y-6),(11,y-14),(9,y-12),(8,y-13)],'#bb8b91')


@lru_cache(maxsize=16)
def _set_art(name,width,height,floor,size,variants):
    """Only scene/geometry/held-object changes rebuild the two-times artwork."""
    canvas=Image.new('RGBA',(width*2,height*2))
    p=_SetPainter(canvas,name,floor,size,2)
    taken=set(variants)
    if name=='home':
        p.ellipse('sofa',0,3,82,5,'#aa8ba124')
        # Upholstered back, box depth, front bevel and separate seat cushions.
        p.rect('sofa',0,15,121,40,'#806b8a','#b69ac2',8)
        p.rect('sofa',0,24,107,28,'#a08aab','#c3accb',7)
        p.line('sofa',[(-48,46),(48,46)],'#c2acc9',.6)
        for x in (-20,20):p.line('sofa',[(x,28),(x,47)],'#8c7599',.7)
        p.rect('sofa',0,8,121,15,'#806789','#b198b8',3)
        press=1.5 if 'sofa_pressed' in taken else 0
        for x in (-27,27):
            p.rect('sofa',x,19-press,50,7,'#b19abb','#ccb4d1',3)
            p.line('sofa',[(x-19,20-press),(x+19,20-press)],'#947c9d',.6)
        for side in (-1,1):
            p.rect('sofa',side*57,8,15,29,'#a48aad','#c3aacd',5)
            p.line('sofa',[(side*59,12),(side*59,31)],'#bd9ec6',.7)
            p.rect('sofa',side*47,1,6,7,'#655369',radius=1)
        # A small paw-print cushion makes the lounge identifiable at CLI scale.
        p.rect('sofa',-25,28,22,20,'#d4b3ac','#e6cdc0',5)
        p.ellipse('sofa',-25,36,4,3,'#b88891')
        for x,y in ((-30,41),(-26,43),(-22,42),(-19,39)):
            p.ellipse('sofa',x,y,1.5,1.8,'#b88891')
        p.ellipse('lamp',0,2,14,3,'#a592aa')
        p.line('lamp',[(0,4),(0,69)],'#8b7c91',3)
        p.line('lamp',[(1,8),(1,67)],'#c1a7b6',.7)
        p.polygon('lamp',[(-22,65),(-14,86),(12,86),(21,65)],'#d6b991','#ead6b5')
        p.ellipse('lamp',0,65,21,3,'#ead5b4','#e8ccaa')
        for x in (-10,0,10):p.line('lamp',[(x*.55,84),(x,67)],'#c4a787',.7)
        p.line('lamp',[(12,65),(12,57)],'#ad9095',.7)
        p.ellipse('lamp',12,56,1,1.5,'#c7a17f')
        # A little reading stool and a separate tea table leave room to move.
        p.rect('book',0,4,5,29,'#94818c',radius=1)
        p.ellipse('book',0,34,22,4,'#bd9b97','#ddbeb2')
        if 'book' not in taken:_book(p)
        p.rect('side_table',0,3,5,22,'#927d8a',radius=1)
        p.ellipse('side_table',0,2,17,3,'#89727e')
        p.ellipse('side_table',0,28,27,5,'#b18e94','#d9b8b6')
        p.arc('side_table',0,28,22,3,0,175,'#e2c7bd',.7)
        if 'teacup' not in taken:_cup(p)
    elif name=='office':
        # Desk top has perspective and thickness, with inset legs and a drawer.
        p.ellipse('desk',0,2,103,5,'#6b5c7222')
        for x in (-76,76):p.rect('desk',x,1,6,39,'#7c7089','#b6a2bb',1)
        p.polygon('desk',[(-90,43),(87,43),(96,37),(-98,37)],'#c4a6af','#dfc4c8')
        p.polygon('desk',[(-98,37),(96,37),(96,32),(-98,32)],'#987b92','#b89baa')
        p.line('desk',[(-92,41),(81,41)],'#e1c5c7',.7)
        p.rect('desk',40,22,42,10,'#8b718a','#ac91a7',2)
        p.line('desk',[(33,27),(45,27)],'#d2b8bc',1)
        # A screen inset, bottom bevel, trackpad, and three rows of tiny keys.
        p.rect('laptop',0,46,49,34,'#51465e','#ad9fbb',3)
        p.rect('laptop',0,49,43,27,'#37394a','#6b6d83',1)
        p.ellipse('laptop',0,78,1,1,'#b8b0c3')
        for n,length in enumerate((23,31,18)):
            p.line('laptop',[(-16,70-n*6),(-16+length,70-n*6)],('#8fbdb1','#bfafcc','#92acc6')[n],1)
        p.polygon('laptop',[(-25,46),(25,46),(31,39),(-31,39)],'#b1a2bf','#d0c1d8')
        p.line('laptop',[(-31,38),(31,38)],'#72687f',2)
        for row in range(3):
            for col in range(7):p.line('laptop',[(-19+col*6,44-row*1.4),(-16+col*6,44-row*1.4)],'#726a87',.6)
        p.rect('laptop',0,39.3,11,1.8,'#d2c5dc',radius=.5)
        p.polygon('notebook',[(-17,44),(12,47),(18,41),(-13,37)],'#b7937e','#dfbca1')
        p.polygon('notebook',[(-15,45),(11,47),(16,42),(-13,39)],'#e7d7b9','#f0e1c9')
        for n in range(3):p.line('notebook',[(-9+n*2,43-n*.8),(10+n,45-n*.8)],'#b5a3a3',.5)
        p.line('notebook',[(16,48),(25,41)],'#a2c3c0',2)
        p.ellipse('plant',0,2,18,3,'#71656c22')
        p.polygon('plant',[(-12,22),(12,22),(9,2),(-8,2)],'#a47f7e','#d2aca0')
        p.ellipse('plant',0,22,13,3,'#c8a39b','#e0bbb0')
        p.ellipse('plant',0,22,9,1.8,'#6f6066')
        for x,y,rx,ry in ((-12,43,8,5),(11,49,8,6),(-5,60,7,7),(18,35,8,5),(-15,32,8,5)):
            p.line('plant',[(0,23),(x,y)],'#73958a',1.3)
            p.ellipse('plant',x,y,rx,ry,'#83a796','#a2b8a2')
            p.line('plant',[(x-rx*.6,y-ry*.4),(x+rx*.5,y+ry*.3)],'#bbccaf',.6)
    elif name=='dinner':
        p.ellipse('table',0,2,138,5,'#8f6b7722')
        for x in (-106,106):p.rect('table',x,1,7,15,'#8f717e',radius=1)
        p.polygon('table',[(-116,21),(117,21),(133,14),(-131,14)],'#c29899','#e2b9ac')
        p.rect('table',1,10,264,5,'#9d777f','#ba9094',1)
        p.line('table',[(-116,19),(113,19)],'#e2bba9',.7)
        # Pot ears, thick rim, curved belly, little feet, soup and ingredients.
        for side in (-1,1):p.ellipse('hotpot',side*28,29,7,5,None,'#bca7ab',2.5)
        p.ellipse('hotpot',0,19,23,4,'#886e74')
        p.rect('hotpot',0,18,47,16,'#aa7778','#ddada0',6)
        p.arc('hotpot',-2,26,20,6,0,150,'#d99f91',1)
        p.ellipse('hotpot',0,34,26,7,'#bd9a95','#ead1b8',1.7)
        p.ellipse('hotpot',0,34,22,4.5,'#c89663','#f1d3a1')
        for x,y,color in ((-12,35,'#83a179'),(-5,32,'#e2cf9f'),(7,35,'#c78975'),(14,32,'#d7b585'),(0,36,'#91aa82')):
            p.ellipse('hotpot',x,y,3,1.4,color)
        # A plate of dumplings, bowl, chopstick rest and a patterned napkin.
        p.ellipse('dish',0,19,23,5,'#b2a2bf','#dfd3df')
        p.ellipse('dish',0,20,18,3,'#e3d7dd')
        for x in (-10,0,10):
            p.ellipse('dish',x,23,6,3.2,'#d9bb9a','#b6998e')
            for dx in (-2,0,2):p.line('dish',[(x+dx,23),(x+dx+1,25)],'#ab8c7d',.5)
        p.line('dish',[(-24,31),(21,27)],'#d6b48a',1)
        p.line('dish',[(-24,34),(21,30)],'#d6b48a',1)
        p.rect('dish',-20,26,10,2,'#c8bdc8',radius=1)
        p.rect('teacup',0,20,28,3,'#c69d9b','#dfbcb0',1)
        if 'teacup' not in taken:_cup(p)
    elif name=='outing':
        p.ellipse('tent',0,2,76,4,'#66847722')
        # Distinct outer fly, shaded side, open doorway, seams and guy ropes.
        p.polygon('tent',[(-60,3),(-3,84),(55,3)],'#7b9fa2','#b6cdbe')
        p.polygon('tent',[(-3,84),(26,75),(72,3),(55,3)],'#5e8490','#9eb9b6')
        p.polygon('tent',[(-27,4),(-3,66),(25,4)],'#344d61','#abc1bb')
        p.polygon('tent',[(-27,4),(-3,66),(-15,14)],'#91b0ac','#bdd0bb')
        p.line('tent',[(-3,78),(-48,8)],'#b6cdbd',.7)
        p.line('tent',[(-58,7),(-75,1)],'#a4b7a9',.7)
        p.line('tent',[(49,10),(82,1)],'#a4b7a9',.7)
        for x in (-75,82):p.line('tent',[(x-2,0),(x+1,5)],'#b8a894',1.4)
        p.line('tent',[(-3,84),(-3,93)],'#d1bfa8',1)
        p.polygon('tent',[(-3,93),(20,87),(-3,83)],'#d2a9a0','#e2c6ad')
        # The checked blanket keeps perspective, not a floating flat rectangle.
        p.polygon('picnic',[(-65,10),(42,10),(71,1),(-43,1)],'#b08f9c9a','#c9adb4')
        for n in range(1,7):
            x=-65+n*107/7
            p.line('picnic',[(x,10),(x+22,1)],'#dbc0bd8a',1.3)
        for n in range(1,4):
            y=1+n*9/4
            p.line('picnic',[(-43-(y-1)*22/9,y),(71-(y-1)*29/9,y)],'#e0c6bc8a',.9)
        # Woven basket with alternating reeds, bound rim and curved handle.
        p.polygon('basket',[(-19,22),(19,22),(16,3),(-16,3)],'#b19170','#ddbb90')
        for n in range(5):p.line('basket',[(-16,5+n*3),(16,5+n*3)],'#d7b48b',.7)
        for x in (-12,-6,0,6,12):p.line('basket',[(x,4),(x*1.1,21)],'#8c745f',.7)
        p.rect('basket',0,20,40,3,'#d3b28a','#e1c39c',1)
        p.arc('basket',0,25,12,12,180,360,'#d1b087',2)
        if 'basket_lid' not in taken:
            p.polygon('basket',[(-19,24),(18,24),(22,20),(-21,20)],'#b89d7b','#ddc196')
            p.line('basket',[(-16,22),(17,22)],'#e3c9a1',.7)
        # A thermos and its removable drinking cup sit beside the blanket.
        p.rect('teacup',0,5,14,25,'#829fa4','#b5c5c1',3)
        p.line('teacup',[(-4,9),(-4,26)],'#c7d5cd',1)
        if 'teacup' not in taken:_cup(p,y=39)
        p.rect('tree',0,1,6,47,'#8d8980',radius=1)
        p.line('tree',[(0,11),(7,22)],'#9c9687',1)
        for y,branch_width in ((75,39),(58,54),(40,67)):
            p.polygon('tree',[(-branch_width/2,y-26),(0,y),(branch_width/2,y-26)],'#70978b','#9cbaa2')
            p.line('tree',[(-branch_width*.30,y-22),(0,y-4),(branch_width*.15,y-15)],'#86aa96',.6)
    return canvas.resize((width,height),Image.Resampling.LANCZOS)


def _responses(canvas,name,floor,size,t,still,active):
    layer=Image.new('RGBA',canvas.size)
    p=_SetPainter(layer,name,floor,size)
    if name=='dinner':
        # Steam is low-contrast and settles completely in quiet/reduced mode.
        for j in (-1,0,1):
            phase=0 if still else t*1.6+j
            x=j*11
            p.line('hotpot',[(x,42),(x+math.sin(phase)*2,49),(x+math.sin(phase+.7)*3,55)],'#e7d6d268',.7)
    if not still:
        for interaction in active:
            prop,action=interaction['prop'],interaction['action']
            if name=='office' and prop=='laptop' and action=='type':
                if int(t*3)%2==0:p.line('laptop',[(5,56),(5,60)],'#c7e0d0',1.2)
                p.line('laptop',[(-12+(int(t*6)%5)*5,41),(-9+(int(t*6)%5)*5,41)],'#ddd3e5',1)
            elif name=='office' and prop=='plant' and action=='water':
                for j in range(4):
                    progress=(t*1.1+j*.25)%1
                    x=-18+progress*13
                    y=56-progress*19
                    p.line('plant',[(x,y+1.5),(x+.5,y-1)],'#9ccbd0b0',1)
                p.arc('plant',0,22,9,2,0,160,'#d2c9b4',.7)
            elif name=='dinner' and prop=='hotpot' and action=='stir':
                for j in range(2):
                    r=4+((t*8+j*8)%16)
                    p.arc('hotpot',0,34,r,r*.19,15,310,'#f5d4a6b0',.8)
            elif name=='outing' and prop=='basket' and action=='unpack':
                progress=interaction.get('progress',.5)
                opening=max(0,min(1,progress*5,(1-progress)*5))
                p.polygon('basket',[(-19,24),(18,24),(18,24+opening*17),(-19,24+opening*13)],'#b89d7b','#ddc196')
                p.line('basket',[(-15,26+opening*4),(14,26+opening*7)],'#dfc19b',.7)
            elif name=='outing' and prop=='tent' and action=='inspect':
                sway=math.sin(t*2)*2
                p.line('tent',[(-3,66),(14+sway,14)],'#c2d1bb',1.2)
    canvas.alpha_composite(layer)


def environment(canvas, name, floor, size, t, still=False, state=None):
    """Draw a quiet miniature set, with responses only to active contacts."""
    if name not in ('home','office','dinner','outing'):
        return
    active=[]
    if not still:
        active=[a['interaction'] for a in (state or {}).get('cast',[])
                if a.get('interaction') and a['interaction'].get('active')]
    variants=[]
    for interaction in active:
        prop,action=interaction['prop'],interaction['action']
        if action in ('sip','read'):variants.append(prop)
        elif action=='unpack':variants.append('basket_lid')
        elif action=='sit':variants.append('sofa_pressed')
    art=_set_art(name,canvas.width,canvas.height,floor,size,tuple(sorted(set(variants))))
    canvas.alpha_composite(art)
    _responses(canvas,name,floor,size,t,still,active)


def power_backdrop(canvas, state, floor, size, positions):
    effect=state.get('spectacle')
    if not effect or state['quiet'] or state['reduced_motion']:
        return
    age,duration=effect['age'],effect['duration']
    strength=min(1,age/.6,max(0,(duration-age)/1.1))
    ultra=effect['kind']=='ultra'
    w,h=canvas.size
    glow_scale=3
    layer=Image.new('RGBA',(max(1,w//glow_scale),max(1,h//glow_scale)))
    d=ImageDraw.Draw(layer)
    palette=[(173,139,255),(117,209,232),(255,195,128),(237,153,204)]
    accents=[ImageColor.getrgb(a.get('accent','#c7b7ff')) for a in state['cast']]
    # Soft light is composed as an overlay, preserving terminal transparency.
    for i,(x,y,_) in enumerate(positions):
        color=accents[i]
        r=size*(.72 if ultra else 1.2)
        box=tuple(v/glow_scale for v in (x-r,y-size*.8-r*.3,x+r,y+8))
        d.ellipse(box,fill=(*color,int(42*strength)))
    glow=layer.filter(ImageFilter.GaussianBlur(max(1,size*.10/glow_scale)))
    canvas.alpha_composite(glow.resize(canvas.size,Image.Resampling.BILINEAR))
    d=ImageDraw.Draw(canvas)
    if ultra:
        # Three fireworks above the ensemble, plus drifting golden confetti.
        for j in range(3):
            cx=w*(.22+j*.28);cy=h*.25+math.sin(j)*8
            cycle=(age*.44+j*.31)%1
            radius=(.13+cycle*.75)*min(h,w*.18)
            for n in range(16):
                a=n*math.tau/16+j
                color=palette[(j+n)%4]
                alpha=int((1-cycle)*220*strength)
                d.line((cx+math.cos(a)*radius*.63,cy+math.sin(a)*radius*.63,cx+math.cos(a)*radius,cy+math.sin(a)*radius),fill=(*color,alpha),width=2)
        for n in range(64):
            x=(n*.618033*w+age*(9+(n%7)*3))%w
            y=((n*37+age*(15+n%13))%(h+24))-12
            color=palette[n%4]
            d.line((x,y,x+3*math.sin(age*4+n),y+4),fill=(*color,int(210*strength)),width=2)
    for i,(x,y,actor_size) in enumerate(positions):
        r=actor_size*(.40+.04*math.sin(age*4+i))
        color=accents[i]
        d.ellipse((x-r,y-5,x+r,y+3),outline=(*color,int(230*strength)),width=2)
        if not ultra:
            # Orbiting diamonds and an arcing constellation for the active cast.
            for n in range(7):
                a=age*1.8+n*math.tau/7+i
                px=x+math.cos(a)*r;py=y-actor_size*.5+math.sin(a)*actor_size*.43
                rr=2+int(n%3==0)
                d.polygon([(px,py-rr),(px+rr,py),(px,py+rr),(px-rr,py)],fill=(*color,int(230*strength)))
            d.arc((x-r*1.15,y-actor_size*1.12,x+r*1.15,y-actor_size*.12),180+age*70,325+age*70,fill=(*color,int(150*strength)),width=2)


def power_foreground(canvas,state):
    effect=state.get('spectacle')
    if not effect or state['quiet'] or state['reduced_motion']:return
    # A brief opening starburst, never a flashing opaque screen.
    age=effect['age']
    if age>.9:return
    overlay=Image.new('RGBA',canvas.size)
    d=ImageDraw.Draw(overlay)
    w,h=canvas.size
    fade=(1-age/.9)*180
    for n in range(14):
        a=n*math.tau/14
        r=h*(.3+age*.8)
        d.line((w*.5+math.cos(a)*r*.75,h*.48+math.sin(a)*r*.75,w*.5+math.cos(a)*r,h*.48+math.sin(a)*r),fill=(237,212,255,int(fade)),width=2)
    canvas.alpha_composite(overlay)


def scene_details(canvas, state, floor, size):
    """Small scene-specific cues, kept clear of the input surface."""
    name=state['scene']
    if name not in ('highfive','photo','stargaze'):return
    still=state['quiet'] or state['reduced_motion']
    age=0 if still else state['scene_age']
    w,h=canvas.size
    layer=Image.new('RGBA',canvas.size)
    d=ImageDraw.Draw(layer)
    if name=='stargaze':
        for n in range(19):
            x=(n*.618033*w)%w;y=9+(n*29)%max(12,int(h*.32))
            r=1.4+.7*math.sin(age*1.7+n)
            d.line((x-r,y,x+r,y),fill='#e8dbedb0')
            d.line((x,y-r,x,y+r),fill='#e8dbedb0')
        if not still:
            cycle=age%6
            if cycle<1.5:
                x=w*(.25+cycle*.18);y=h*.12+cycle*12
                d.line((x-28,y-8,x,y),fill='#d3c9eb90',width=2)
                d.ellipse((x-2,y-2,x+2,y+2),fill='#efdcff')
    elif name=='photo':
        cx=w*.88;cy=floor-size*.42
        d.line((cx,cy+6,cx-10,floor),fill='#a698b7',width=2)
        d.line((cx,cy+6,cx+10,floor),fill='#a698b7',width=2)
        d.rounded_rectangle((cx-16,cy-10,cx+16,cy+9),radius=4,fill='#7e6e99',outline='#d6c3e6')
        d.ellipse((cx-6,cy-7,cx+6,cy+5),fill='#c4d7ec',outline='#f2e5fa',width=2)
        if not still and 1.9<age%4<2.25:
            d.line((cx-23,cy-15,cx-12,cy-27),fill='#f8dfb7',width=3)
            d.line((cx-17,cy-21,cx-29,cy-25),fill='#f8dfb7',width=2)
    elif not still:
        for n in range(3):
            x=w*.44+(n-1)*13;y=max(10,floor-size-4)-abs(math.sin(age*3+n))*9
            d.line((x-3,y,x+3,y),fill='#edca9a',width=2)
            d.line((x,y-3,x,y+3),fill='#edca9a',width=2)
    canvas.alpha_composite(layer)
