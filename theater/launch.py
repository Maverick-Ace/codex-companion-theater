"""A local, finite launch ceremony. Destinations are playful model-name motifs."""
from functools import lru_cache
import hashlib
import math
import re
from PIL import Image, ImageDraw, ImageFilter
from .celestial import icon as celestial_icon

DURATION = 7.8
DESTINATIONS = {
    'sol': ('sun', '太阳', '#ffbd53', '#fff1a8'),
    'terra': ('earth', '地球', '#59b9dd', '#83d2a0'),
    'luna': ('moon', '月球', '#c9c4e7', '#f6eaff'),
    'astra': ('stars', '星海', '#b59bff', '#e9caff'),
    'reserve': ('saturn', '环星', '#dfb993', '#ffe0af'),
    'deepseek': ('neptune', '海蓝星', '#64a9ec', '#a2eaff'),
    'claude': ('mars', '暖砂星', '#e3a18b', '#ffd5a6'),
    'gemini': ('twins', '双子星', '#a4b7ff', '#e4baff'),
    'qwen': ('jade', '青玉星', '#70d5bc', '#b7f2d3'),
}

def destination(model):
    tokens = re.findall(r'[a-z]+', str(model).lower())
    for token in tokens:
        if token in DESTINATIONS:
            kind, name, color, light = DESTINATIONS[token]
            return dict(kind=kind, name=name, color=color, light=light)
    # Unrecognized/custom model names still have a stable, distinct destination.
    hue = hashlib.sha256(str(model).encode()).digest()
    color = '#'+''.join(f'{100+n%125:02x}' for n in hue[:3])
    return dict(kind='planet', name='远航星', color=color, light='#e5dcff')

def snapshot(flight, now, reduced=False):
    if not flight:return None
    age = max(0, now-flight['start'])
    return dict(model=flight['model'], destination=dict(flight['destination']),
                age=age, duration=DURATION,
                phase='build' if age<1.6 else 'ignite' if age<2.2 else 'launch' if age<3.8 else 'orbit',
                reduced=reduced)

def ease(t):
    t=max(0,min(1,t));return t*t*(3-2*t)

def _rgb(hex_color):return tuple(bytes.fromhex(hex_color.lstrip('#')))

@lru_cache(maxsize=32)
def _exhaust_glow(side):
    im=Image.new('RGBA',(side,side));d=ImageDraw.Draw(im)
    d.ellipse((side*.28,side*.28,side*.72,side*.72),fill='#ffaf6070')
    return im.filter(ImageFilter.GaussianBlur(max(1,side*.12)))

@lru_cache(maxsize=96)
def _planet(kind, color, light, diameter):
    """Antialiased miniature, with cached local glow rather than full-frame blur."""
    official=celestial_icon(kind,diameter)
    if official is not None:return official
    size=diameter*4
    im=Image.new('RGBA',(size,size));d=ImageDraw.Draw(im)
    c=size/2;r=size*.25
    rgb=_rgb(color)
    glow=Image.new('RGBA',im.size);g=ImageDraw.Draw(glow)
    g.ellipse((c-r*1.3,c-r*1.3,c+r*1.3,c+r*1.3),fill=(*rgb,70))
    im=glow.filter(ImageFilter.GaussianBlur(size*.09));d=ImageDraw.Draw(im)
    if kind=='sun':
        for n in range(12):
            angle=n*math.tau/12
            d.line((c+math.cos(angle)*r*1.12,c+math.sin(angle)*r*1.12,
                    c+math.cos(angle)*r*1.39,c+math.sin(angle)*r*1.39),fill=(*rgb,150),width=2)
    d.ellipse((c-r,c-r,c+r,c+r),fill=color,outline=light,width=2)
    if kind=='earth':
        for points in (((-.6,-.5),(-.2,-.7),(.1,-.3),(-.1,.1),(-.45,.2)),
                       ((.3,-.05),(.7,.15),(.45,.65),(.15,.4))):
            d.polygon([(c+x*r,c+y*r) for x,y in points],fill=light)
    elif kind=='moon':
        for x,y,rad in ((-.4,-.3,.2),(.3,.2,.28),(-.2,.6,.14)):
            d.ellipse((c+(x-rad)*r,c+(y-rad)*r,c+(x+rad)*r,c+(y+rad)*r),fill='#aaa4c6',outline=light)
    elif kind=='saturn':
        d.ellipse((c-r*1.7,c-r*.38,c+r*1.7,c+r*.38),outline=light,width=4)
    else:
        for n in range(3):
            d.arc((c-r*.8,c-r*.7+n*r*.2,c+r*.8,c+r*.2+n*r*.2),10,155,fill=light,width=3)
        if kind in ('twins','stars'):
            d.ellipse((c+r*.7,c-r*1.1,c+r*1.4,c-r*.4),fill=light)
    # Shaded crescent keeps small bodies spherical.
    d.arc((c-r*.9,c-r*.9,c+r*.9,c+r*.9),-70,70,fill=(*rgb,100),width=max(2,int(r*.14)))
    return im.resize((diameter*2,diameter*2),Image.Resampling.LANCZOS)

def _rocket(height, color, assembly=1):
    """Separate hull, nose and fins slide into their real attachment points."""
    output=max(12,round(height));h=output*3;im=Image.new('RGBA',(h*2,h*2));d=ImageDraw.Draw(im)
    cx=h;top=h*.64;bottom=top+h*.66;w=h*.17
    gap=(1-ease(assembly))*h*.38
    d.rounded_rectangle(tuple(round(v) for v in (cx-w,top+h*.16,cx+w,bottom)),radius=max(1,round(h*.065)),fill='#e8eaf3',outline='#b9c2db',width=1)
    d.polygon(((cx-w,top+h*.18-gap),(cx,top-gap),(cx+w,top+h*.18-gap)),fill=color)
    for side in (-1,1):
        x=cx+side*(w+gap)
        d.polygon(((x,top+h*.42),(x+side*h*.17,bottom+h*.09),(x,bottom-h*.02)),fill=color)
    d.ellipse((cx-w*.55,top+h*.25,cx+w*.55,top+h*.25+w*1.1),fill='#5d83bd',outline='#fbf6ff',width=1)
    d.line((cx-w*.7,bottom-h*.03,cx+w*.7,bottom-h*.03),fill='#ffd28f',width=2)
    return im.resize((output*2,output*2),Image.Resampling.LANCZOS)

def _paste(canvas, im, x, y):
    x,y=round(x-im.width/2),round(y-im.height/2)
    left,top=max(0,x),max(0,y);right,bottom=min(canvas.width,x+im.width),min(canvas.height,y+im.height)
    if right>left and bottom>top:canvas.alpha_composite(im.crop((left-x,top-y,right-x,bottom-y)),(left,top))

def _ship(x,y,dx,dy,height,flame,assembly=1):
    # Pillow rotates counterclockwise; screen y increases downwards.
    angle=math.degrees(math.atan2(-dx,-dy))
    return dict(x=x,y=y,angle=angle,height=max(12,round(height)),flame=flame,assembly=assembly)

def _orbit_pose(age,cx,cy,rx,ry,height,rate=1.4,phase=0,ramp=False):
    elapsed=max(0,age)
    # Ease into orbital speed after the launch curve reaches its endpoint.
    theta=phase+rate*(elapsed-.18*(1-math.exp(-elapsed/.18)) if ramp else elapsed)
    return _ship(cx+math.cos(theta)*rx,cy+math.sin(theta)*ry,
                 -math.sin(theta)*rx,math.cos(theta)*ry,height,height*.58)

def _flight_pose(age,w,h,floor):
    cx,cy=w*.78,h*.40;rx=min(w*.13,h*.62);pad_x=w*.51
    if age<2.2:
        return _ship(pad_x,floor-h*.18,0,-1,h*.55,ease((age-1.6)/.6)*h*.17,ease(age/1.4))
    if age>=3.8:
        return _orbit_pose(age-3.8,cx,cy,rx,h*.25,h*.17,math.tau/1.9,math.pi,True)
    u=ease((age-2.2)/1.6);v=1-u
    # Both endpoints point upward. The endpoint and orbit share a tangent.
    points=((pad_x,floor-h*.18),(pad_x,floor-h*.58),(cx-rx,cy+h*.20),(cx-rx,cy))
    x,y=(v**3*points[0][axis]+3*v*v*u*points[1][axis]+3*v*u*u*points[2][axis]+u**3*points[3][axis] for axis in (0,1))
    dx,dy=(3*v*v*(points[1][axis]-points[0][axis])+6*v*u*(points[2][axis]-points[1][axis])+3*u*u*(points[3][axis]-points[2][axis]) for axis in (0,1))
    return _ship(x,y,dx,dy,h*(.55-.38*u),h*(.30-.20*u))

def _nozzle(pose):
    a=math.radians(pose['angle']);bx,by=math.sin(a),math.cos(a)
    return pose['x']+bx*pose['height']*.30,pose['y']+by*pose['height']*.30,bx,by

def _draw_exhaust(canvas,pose,age,path,color,strength=1):
    """Sample elapsed emission time, so the wake keeps the curve it flew through."""
    if pose['flame']<=0:return
    lifetime=.46;points=[];halfwidth=max(1.2,pose['height']*.13)
    for i in range(33):
        u=i/32;t=age-u*lifetime
        if t<0:break
        past=path(t)
        if past['flame']<=0:break
        x,y,bx,by=_nozzle(past)
        drift=past['flame']*.8*u
        points.append((x+bx*drift,y+by*drift,u))
    if len(points)<2:return
    scale=2;pad=halfwidth*3+5
    left=max(0,math.floor(min(x for x,y,u in points)-pad));top=max(0,math.floor(min(y for x,y,u in points)-pad))
    right=min(canvas.width,math.ceil(max(x for x,y,u in points)+pad));bottom=min(canvas.height,math.ceil(max(y for x,y,u in points)+pad))
    if right<=left or bottom<=top:return
    tile=Image.new('RGBA',((right-left)*scale,(bottom-top)*scale));d=ImageDraw.Draw(tile)
    # A broad faint halo, orange wake, gold flame, and a narrow white-hot core.
    rgb=_rgb(color)
    styles=((2.4,(*rgb,40)),(1.4,(255,130,83,150)),(.80,(255,208,112,225)),(.27,(255,247,219,245)))
    for spread,rgba in styles:
        for i in range(len(points)-2,-1,-1):
            a,b=points[i],points[i+1];dx,dy=b[0]-a[0],b[1]-a[1];length=math.hypot(dx,dy)
            if length<1e-5:continue
            nx,ny=-dy/length,dx/length
            def edges(p):
                x,y,u=p;width=halfwidth*spread*(1-u)**.65*(1+.5*u)
                return ((x+nx*width-left)*scale,(y+ny*width-top)*scale),((x-nx*width-left)*scale,(y-ny*width-top)*scale)
            ap,am=edges(a);bp,bm=edges(b)
            opacity=round(rgba[3]*(1-a[2])**1.5*strength)
            d.polygon((ap,bp,bm,am),fill=(*rgba[:3],opacity))
    halo=tile.filter(ImageFilter.GaussianBlur(2*scale))
    halo.alpha_composite(tile)
    canvas.alpha_composite(halo.resize((right-left,bottom-top),Image.Resampling.LANCZOS),(left,top))
    # Embers drift from earlier nozzle positions instead of rotating as one rod.
    d=ImageDraw.Draw(canvas)
    for n in range(12):
        u=(age*1.8+n*.083)%1;t=age-u*lifetime
        if t<0:continue
        past=path(t)
        if past['flame']<=0:continue
        x,y,bx,by=_nozzle(past);side=math.sin(n*2.4)*u*halfwidth*2.5
        x+=bx*past['flame']*u+by*side;y+=by*past['flame']*u-bx*side
        r=max(.35,(1-u)*1.2);alpha=round(175*min(1,u*8)*(1-u)*strength)
        d.ellipse((x-r,y-r,x+r,y+r),fill=(255,190+n%3*16,130,alpha))

def _draw_ship(canvas,pose,color):
    rocket=_rocket(pose['height'],color,pose['assembly']).rotate(pose['angle'],resample=Image.Resampling.BICUBIC,expand=True)
    _paste(canvas,rocket,pose['x'],pose['y'])

def draw_launch(canvas, state, floor, size, positions, font):
    flight=state.get('flight')
    if not flight:return
    age=flight['age'];w,h=canvas.size;target=flight['destination']
    color=target['color'];rgb=_rgb(color)
    d=ImageDraw.Draw(canvas)
    fade=min(1,age/.22,(DURATION-age)/.6)
    if fade<=0:return
    # Draw all ceremony graphics on one tile so both fade and clipping are exact.
    layer=Image.new('RGBA',canvas.size);d=ImageDraw.Draw(layer)
    cx,cy=w*.78,h*.40
    orbit_rx=min(w*.13,h*.62)
    diameter=max(12,round(h*.29))
    reveal=ease((age-2.8)/.75)
    if reveal>0 or flight['reduced']:
        planet=_planet(target['kind'],color,target['light'],diameter).copy()
        planet.putalpha(planet.getchannel('A').point(lambda a:round(a*(1 if flight['reduced'] else reveal))))
        _paste(layer,planet,cx,cy)
        label=target['name'];f=font(max(9,round(h*.066)))
        bb=d.textbbox((0,0),label,font=f)
        d.text((cx-(bb[2]-bb[0])/2,cy+diameter*.68),label,font=f,fill=target['light'])
    if flight['reduced']:
        _paste(layer,_rocket(h*.24,color),w*.56,h*.58)
    else:
        # Discreet stars appear around the destination, never in the transcript.
        for n in range(13):
            x=w*(.58+(n*37%35)/100);y=h*(.06+(n*19%57)/100)
            a=round(130*reveal*(.6+.4*math.sin(age*2+n)))
            d.ellipse((x,y,x+1,y+1),fill=(230,217,255,max(0,a)))
        pad_x=w*.51
        d.ellipse((pad_x-h*.19,floor-3,pad_x+h*.19,floor+1),fill='#acb4da77',outline='#cbd2f1aa')
        pose=_flight_pose(age,w,h,floor)
        if age<2.2:
            if age<1.6:
                for i,(ax,af,actor_size) in enumerate(positions):
                    hand=(ax,af-actor_size*.45)
                    progress=ease((age-i*.12)/.9)
                    px=hand[0]+(pad_x-hand[0])*progress
                    py=hand[1]+(floor-h*.34-hand[1])*progress-math.sin(progress*math.pi)*h*.12
                    if progress<1:
                        d.rounded_rectangle((px-4,py-3,px+4,py+3),radius=2,fill='#e4def6',outline=color)
                    # Little wrenches make the crew's assembly readable.
                    if i%2==0:d.line((hand[0]-4,hand[1]+4,hand[0]+3,hand[1]-4),fill='#d3d7ed',width=2)
        if age>=3.8:
            d.ellipse((cx-orbit_rx,cy-h*.25,cx+orbit_rx,cy+h*.25),outline=(*rgb,50),width=1)
        if pose['flame']>0:
            nozzle_x,nozzle_y,_,_=_nozzle(pose)
            _paste(layer,_exhaust_glow(max(12,round(h*.24))),nozzle_x,nozzle_y)
            if age<2.2:
                spread=ease((age-1.6)/.6)*h*.22
                d.ellipse((pad_x-spread,floor-5,pad_x+spread,floor),fill='#ffc87690')
            _draw_exhaust(layer,pose,age,lambda t:_flight_pose(t,w,h,floor),color)
        _draw_ship(layer,pose,color)
    layer.putalpha(layer.getchannel('A').point(lambda a:round(a*fade)))
    canvas.alpha_composite(layer)
