"""Official model-page materials framed as small, transparent celestial icons."""
from functools import lru_cache
from pathlib import Path
import math
from PIL import Image, ImageChops, ImageDraw, ImageFilter

ROOT=Path(__file__).resolve().parents[1]/'assets/celestial'
CROPS={'sun':(358,92,534,268),'earth':(336,0,696,360),
       'moon':(0,85,140,275),'stars':(160,0,520,360)}

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
            light=1 if kind in ('sun','stars') else .32+.68*max(0,-.35*nx-.2*ny+.88*z)
            sp[x,y]=(round(255*light),)*3
    photo=ImageChops.multiply(photo,shade).convert('RGBA');photo.putalpha(alpha)
    tile=Image.new('RGBA',(side,side));glow=Image.new('RGBA',tile.size)
    color={'sun':(255,187,78),'earth':(109,194,255),'moon':(204,211,237),'stars':(179,165,255)}[kind]
    ImageDraw.Draw(glow).ellipse((pad-3,pad-3,pad+size+3,pad+size+3),fill=(*color,90))
    tile.alpha_composite(glow.filter(ImageFilter.GaussianBlur(size*.09)))
    tile.alpha_composite(photo,(pad,pad))
    return tile.resize((diameter*2,diameter*2),Image.Resampling.LANCZOS)
