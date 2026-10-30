"""Official model-page materials framed as small, transparent celestial icons."""
from functools import lru_cache
from pathlib import Path
import math
from PIL import Image, ImageChops, ImageDraw, ImageFilter

ROOT=Path(__file__).resolve().parents[1]/'assets/celestial'
CROPS={'sun':(358,92,534,268),'earth':(336,0,696,360),
       'moon':(0,0,178,240),'stars':(160,0,520,360)}

@lru_cache(maxsize=48)
def icon(kind, diameter):
    if kind not in CROPS:return None
    # Render large enough for soft atmospheric edges, then downsample once.
    size=max(48,int(diameter)*3);pad=size//3;side=size+pad*2
    with Image.open(ROOT/(kind+'.webp')) as source:
        photo=source.convert('RGB').crop(CROPS[kind]).resize((size,size),Image.Resampling.LANCZOS)
    alpha=Image.new('L',(size,size));shade=Image.new('RGB',(size,size))
    ap=alpha.load();sp=shade.load()
    for y in range(size):
        ny=(y+.5-size/2)/(size/2)
        for x in range(size):
            nx=(x+.5-size/2)/(size/2);r2=nx*nx+ny*ny
            if r2>=1:continue
            z=math.sqrt(1-r2)
            ap[x,y]=round(255*min(1,(1-r2)*45))
            base=.55 if kind=='moon' else .32
            light=1 if kind in ('sun','stars') else base+(1-base)*max(0,-.35*nx-.2*ny+.88*z)
            sp[x,y]=(round(255*light),)*3
    photo=ImageChops.multiply(photo,shade).convert('RGBA');photo.putalpha(alpha)
    tile=Image.new('RGBA',(side,side));glow=Image.new('RGBA',tile.size)
    color={'sun':(255,187,78),'earth':(109,194,255),'moon':(204,211,237),'stars':(179,165,255)}[kind]
    ImageDraw.Draw(glow).ellipse((pad-3,pad-3,pad+size+3,pad+size+3),fill=(*color,90))
    tile.alpha_composite(glow.filter(ImageFilter.GaussianBlur(size*.09)))
    tile.alpha_composite(photo,(pad,pad))
    return tile.resize((diameter*2,diameter*2),Image.Resampling.LANCZOS)

@lru_cache(maxsize=36)
def ambience(period, side):
    """Readable corner silhouettes with official texture inside, drawn at 4x.

    The tiny stage marker needs rays or a crescent to read at terminal scale;
    the photographic spheres above remain the destinations for rocket flights.
    """
    scale=4;n=side*scale;c=n/2;r=n*.18
    night=period=='night';dusk=period=='dusk'
    kind='moon' if night else 'sun'
    tile=Image.new('RGBA',(n,n));glow=Image.new('RGBA',tile.size)
    g=ImageDraw.Draw(glow)
    color=(166,187,230) if night else (232,164,104) if dusk else (236,191,103)
    g.ellipse((c-r*1.7,c-r*1.7,c+r*1.7,c+r*1.7),fill=(*color,25))
    tile.alpha_composite(glow.filter(ImageFilter.GaussianBlur(n*.09)))
    d=ImageDraw.Draw(tile)
    if not night:
        for i in range(8):
            a=math.tau*i/8
            if dusk and math.sin(a)>.1:continue
            inner,outer=n*.28,n*(.37 if i%2 else .40)
            points=(c+math.cos(a)*inner,c+math.sin(a)*inner,c+math.cos(a)*outer,c+math.sin(a)*outer)
            d.line(points,fill=(*color,210),width=scale)
            for x,y in (points[:2],points[2:]):
                d.ellipse((x-scale/2,y-scale/2,x+scale/2,y+scale/2),fill=(*color,210))
    # Tone-map the official highlights so the center stays amber, not white.
    with Image.open(ROOT/(kind+'.webp')) as source:
        texture=source.convert('L').crop(CROPS[kind]).resize((n,n),Image.Resampling.LANCZOS)
    low=(155,178,211) if night else (190,119,72) if dusk else (207,151,66)
    high=(224,228,230) if night else (235,180,126) if dusk else (243,210,140)
    surface=Image.new('RGBA',(n,n));pixels=surface.load();values=texture.load()
    for y in range(n):
        for x in range(n):
            light=values[x,y]/255
            pixels[x,y]=tuple(round(a+(b-a)*light) for a,b in zip(low,high))+(245,)
    mask=Image.new('L',(n,n));m=ImageDraw.Draw(mask)
    if night:
        r=n*.27
        m.ellipse((c-r,c-r,c+r,c+r),fill=255)
        cut=Image.new('L',(n,n));ImageDraw.Draw(cut).ellipse((c-r+n*.15,c-r-n*.09,c+r+n*.15,c+r-n*.09),fill=255)
        mask=ImageChops.subtract(mask,cut)
        for x,y,s in ((n*.76,n*.22,n*.045),(n*.78,n*.68,n*.027)):
            d.line((x-s,y,x+s,y),fill=(190,201,230,180),width=scale//2)
            d.line((x,y-s,x,y+s),fill=(190,201,230,180),width=scale//2)
    else:
        m.ellipse((c-r,c-r,c+r,c+r),fill=255)
        if dusk:
            # A quiet horizon gives dusk a different silhouette from daytime.
            m.rectangle((0,c+r*.45,n,n),fill=0)
            d.line((c-r*1.5,c+r*.65,c+r*1.5,c+r*.65),fill=(*color,180),width=scale//2)
    surface.putalpha(mask.point(lambda a:round(a*.95)))
    tile.alpha_composite(surface)
    return tile.resize((side,side),Image.Resampling.LANCZOS)
