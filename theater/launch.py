"""A local, finite launch ceremony. Destinations are playful model-name motifs."""
from functools import lru_cache
import hashlib
import math
import re
from PIL import Image, ImageDraw, ImageFilter

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
        if age<2.2:
            x,y=pad_x,floor-h*.18
            rocket_h=h*.55;angle=0
            assembly=ease(age/1.4)
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
            flame=ease((age-1.6)/.6)*h*.17
        elif age<3.8:
            u=ease((age-2.2)/1.6)
            x=pad_x+(cx-orbit_rx-pad_x)*u
            y=(floor-h*.18)*(1-u)+cy*u-math.sin(u*math.pi)*h*.20
            rocket_h=h*(.55-.38*u);angle=-math.sin(u*math.pi)*55;assembly=1
            flame=h*(.30-.20*u)
        else:
            theta=(age-3.8)*math.tau/1.9+math.pi
            rx=orbit_rx;ry=h*.25
            x=cx+math.cos(theta)*rx;y=cy+math.sin(theta)*ry
            dx=-math.sin(theta)*rx;dy=math.cos(theta)*ry
            angle=-math.degrees(math.atan2(dx,-dy))
            rocket_h=h*.17;assembly=1;flame=h*.10
            # A gently luminous orbit with a short, fading trail.
            d.ellipse((cx-rx,cy-ry,cx+rx,cy+ry),outline=(*rgb,65),width=1)
            for n in range(1,17):
                a=theta-n*.045;px=cx+math.cos(a)*rx;py=cy+math.sin(a)*ry
                r=max(.6,2.5-n*.12)
                d.ellipse((px-r,py-r,px+r,py+r),fill=(*rgb,round(180*(1-n/18))))
        if flame>0:
            # Multi-layer hot core and turbulent particles follow the ship's axis.
            radians=math.radians(-angle);back_x=-math.sin(radians);back_y=math.cos(radians)
            nozzle_x=x+back_x*rocket_h*.25;nozzle_y=y+back_y*rocket_h*.25
            _paste(layer,_exhaust_glow(max(12,round(h*.24))),nozzle_x,nozzle_y)
            if age<2.2:
                spread=ease((age-1.6)/.6)*h*.22
                d.ellipse((pad_x-spread,floor-5,pad_x+spread,floor),fill='#ffc87690')
            side_x,side_y=back_y,-back_x
            flicker=1+.13*math.sin(age*43)+.07*math.sin(age*71)
            for length,spread,fill in ((1,.13,'#c695ff90'),(.85,.10,'#ff8756dd'),(.62,.065,'#ffd778ff'),(.35,.035,'#fff9dcff')):
                tip_x=nozzle_x+back_x*flame*length*flicker;tip_y=nozzle_y+back_y*flame*length*flicker
                sw=h*spread*.35
                d.polygon(((nozzle_x+side_x*sw,nozzle_y+side_y*sw),(tip_x,tip_y),
                           (nozzle_x-side_x*sw,nozzle_y-side_y*sw)),fill=fill)
            for n in range(18):
                u=(age*1.9+n*.071)%1;spread=math.sin(n*2.4+age*6)*u*h*.06
                px=nozzle_x+back_x*flame*u*1.6+side_x*spread
                py=nozzle_y+back_y*flame*u*1.6+side_y*spread
                r=(1-u)*1.7
                d.ellipse((px-r,py-r,px+r,py+r),fill=(255,180+n%3*25,124,round(200*(1-u))))
        rocket=_rocket(rocket_h,color,assembly).rotate(angle,resample=Image.Resampling.BICUBIC,expand=True)
        _paste(layer,rocket,x,y)
    layer.putalpha(layer.getchannel('A').point(lambda a:round(a*fade)))
    canvas.alpha_composite(layer)
