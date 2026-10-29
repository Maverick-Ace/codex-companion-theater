"""Code-drawn miniature sets and short, transparent celebration effects."""
import math
from PIL import Image, ImageDraw, ImageFilter, ImageColor


def environment(canvas, name, floor, size, t, still=False):
    d=ImageDraw.Draw(canvas)
    w=canvas.width
    u=max(.65,min(1.8,size/110))
    def rect(cx,y,ww,hh,fill,outline=None,r=4):
        box=tuple(round(v) for v in (cx-ww*u/2,floor-y*u-hh*u,cx+ww*u/2,floor-y*u))
        radius=max(0,min(round(r*u),(box[2]-box[0])//2,(box[3]-box[1])//2))
        d.rounded_rectangle(box,radius=radius,fill=fill,outline=outline,width=max(1,round(u)))
    def line(points,color,width=2):
        d.line([(x,floor-y*u) for x,y in points],fill=color,width=max(1,round(width*u)))
    if name=='home':
        cx=w*.20
        # A low sofa, cushion, rug and a warm reading lamp.
        d.ellipse((cx-80*u,floor-5*u,cx+80*u,floor+1),fill='#bd9bb526')
        rect(cx,8,112,35,'#856595','#c4a0cf',9)
        rect(cx,6,123,18,'#a07cae','#d3afd9',6)
        for side in (-1,1):rect(cx+side*54*u,5,17,32,'#9971ac',r=5)
        rect(cx-25*u,26,24,17,'#e7c5b9',r=5)
        lx=w*.08
        line([(lx,4),(lx,77)],'#ba99bd',3)
        d.polygon([(lx-20*u,floor-61*u),(lx-12*u,floor-87*u),(lx+12*u,floor-87*u),(lx+20*u,floor-61*u)],fill='#e2be8f',outline='#f5d3a6')
        line([(lx-14*u,2),(lx+14*u,2)],'#b79bbf',3)
    elif name=='office':
        cx=w*.53
        # Laptop screen, desk, notebook, mug and a tiny potted plant.
        rect(cx,21,137,7,'#ad8baf','#d7bbd4',2)
        for x in (cx-56*u,cx+56*u):rect(x,1,5,21,'#8f759b',r=1)
        rect(cx,30,44,27,'#45374f','#b7a1cf',3)
        for n in range(3):line([(cx-15*u,49-n*5),(cx+(8+n%2*6)*u,49-n*5)],'#a4d5cd',1)
        rect(cx,27,55,3,'#c0a6d5',r=1)
        rect(cx-49*u,28,23,4,'#e6cb9b',r=1)
        rect(cx+45*u,28,12,12,'#b2cbdc',r=3)
        d.arc((cx+49*u,floor-38*u,cx+59*u,floor-29*u),-85,85,fill='#c1d6e3',width=2)
        px=w*.84
        rect(px,1,18,19,'#b4867e',r=3)
        for a in (-.8,0,.8):
            line([(px,19),(px+math.sin(a)*14*u,38)],'#7baa97',2)
            d.ellipse((px+math.sin(a)*14*u-6*u,floor-44*u,px+math.sin(a)*14*u+6*u,floor-30*u),fill='#83b69a')
    elif name=='dinner':
        cx=w*.5
        # Low table keeps the chibis visible; steam animates above a shared pot.
        rect(cx,13,237,8,'#bc8987','#e3b4aa',4)
        for x in (cx-99*u,cx+99*u):rect(x,1,6,14,'#96727e',r=1)
        d.ellipse((cx-23*u,floor-35*u,cx+23*u,floor-15*u),fill='#bd6f68',outline='#efc2a1',width=2)
        d.ellipse((cx-23*u,floor-36*u,cx+23*u,floor-26*u),fill='#e6b374',outline='#f6d5ab')
        for j in (-1,0,1):
            sx=cx+j*11*u
            phase=0 if still else t*2+j
            line([(sx,39),(sx+math.sin(phase)*3*u,47),(sx+math.sin(phase+.7)*4*u,55)],'#dfcfd78a',1)
        for side in (-1,1):
            x=cx+side*71*u
            d.ellipse((x-19*u,floor-26*u,x+19*u,floor-17*u),fill='#d6d2e6',outline='#bba8ca')
            for k in (-1,0,1):d.ellipse((x+k*8*u-4*u,floor-29*u,x+k*8*u+4*u,floor-23*u),fill='#c79878')
            line([(x-16*u,29),(x+16*u,32)],'#e0bd8e',2)
    elif name=='outing':
        cx=w*.18
        d.polygon([(cx-58*u,floor-1),(cx,floor-82*u),(cx+59*u,floor-1)],fill='#759caa',outline='#c0d5d6')
        d.polygon([(cx-26*u,floor-1),(cx,floor-68*u),(cx+27*u,floor-1)],fill='#364d65',outline='#9ab6c4')
        line([(cx,82),(cx+5*u,94)],'#c9bfce',2)
        d.polygon([(cx+5*u,floor-94*u),(cx+28*u,floor-88*u),(cx+5*u,floor-84*u)],fill='#e8bca0')
        mx=w*.68
        d.polygon([(mx-62*u,floor-10*u),(mx+40*u,floor-10*u),(mx+70*u,floor),(mx-40*u,floor)],fill='#b38c9c88',outline='#d4b4bd')
        for side in (-1,1):
            x=mx+side*16*u
            rect(x,9,16,14,'#ddbd8e',r=3)
        tx=w*.89
        line([(tx,1),(tx,55)],'#b39c9e',4)
        for y,ww in ((68,44),(54,57),(39,66)):
            d.polygon([(tx-ww*u/2,floor-(y-26)*u),(tx,floor-y*u),(tx+ww*u/2,floor-(y-26)*u)],fill='#78a193',outline='#9ec1aa')


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
