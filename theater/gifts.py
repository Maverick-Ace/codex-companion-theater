"""Cached, antialiased miniature parcels and collectible stage props."""
from functools import lru_cache
import math
from PIL import Image,ImageDraw,ImageFilter

def _star(x,y,r):
    return [(x+math.cos(i*math.pi/5-math.pi/2)*r*(1 if i%2==0 else .43),
             y+math.sin(i*math.pi/5-math.pi/2)*r*(1 if i%2==0 else .43)) for i in range(10)]

def _canvas(side):
    # All outlines and small seams share the same four-times supersampling.
    return Image.new('RGBA',(side*4,side*4))

def _shadow(im):
    s=im.width/64;shadow=Image.new('RGBA',im.size)
    ImageDraw.Draw(shadow).ellipse((12*s,53*s,55*s,61*s),fill=(29,23,43,65))
    im.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(2*s)))

def parcel(side,opened=0):
    return _parcel(int(side),max(0,min(16,round(opened*16))))

@lru_cache(maxsize=96)
def _parcel(side,step):
    im=_canvas(side);_shadow(im);s=im.width/64
    d=ImageDraw.Draw(im)
    def poly(points,fill,outline=None):
        d.polygon([(x*s,y*s) for x,y in points],fill=fill,outline=outline,width=max(1,round(s*.5)))
    # Recessed interior and two shaded faces keep the box readable at 28px.
    poly(((9,23),(32,12),(56,23),(34,35)),'#805c8b','#edcfdf')
    poly(((9,23),(34,35),(34,58),(9,47)),'#c99dbe','#e6c5d9')
    poly(((34,35),(56,23),(56,46),(34,58)),'#a37da5','#d4b2ce')
    poly(((19,28),(25,31),(25,54),(19,51)),'#f0d6aa')
    poly(((42,31),(47,28),(47,51),(42,54)),'#dac395')
    d.line((10*s,45*s,33*s,56*s),fill='#b384a5',width=max(1,round(s*.7)))
    d.ellipse((27*s,37*s,32*s,42*s),fill='#e7c78c',outline='#f9e4bd',width=max(1,round(s*.5)))
    # A separate lid rises when the courier's gift opens.
    extra=14 if step else 0
    lid=Image.new('RGBA',(im.width,im.height+round(extra*s)));g=ImageDraw.Draw(lid);lift=step/16*13
    base=Image.new('RGBA',lid.size);base.alpha_composite(im,(0,round(extra*s)));im=base
    def top(points,fill,outline=None):
        g.polygon([(x*s,(y-lift+extra)*s) for x,y in points],fill=fill,outline=outline,width=max(1,round(s*.5)))
    top(((7,20),(32,8),(58,20),(34,32)),'#e6c3db','#f6dfea')
    top(((7,20),(34,32),(34,37),(7,25)),'#d0a6c9','#e9c9df')
    top(((34,32),(58,20),(58,25),(34,37)),'#b68caf','#d6b1ce')
    top(((16,16),(22,13),(48,25),(42,28)),'#f4ddba')
    top(((42,13),(48,16),(23,28),(17,25)),'#e8c99e')
    # Folded ribbon loops, lighter inner seams, and tapered tails.
    top(((32,14),(20,10),(18,5),(23,2),(30,6),(34,13)),'#edd0a9','#fff0cf')
    top(((34,13),(39,5),(46,3),(49,7),(45,12),(35,16)),'#e0b98e','#fce5bd')
    top(((31,15),(25,20),(24,27),(29,24),(31,25),(35,16)),'#f1d4ab')
    top(((35,15),(39,19),(46,20),(42,23),(44,25),(36,20)),'#dbb28c')
    top(((30,12),(36,11),(39,15),(34,18),(30,16)),'#f9e0b5','#e3bd95')
    im.alpha_composite(lid)
    return im.resize((side,round(side*(1+extra/64))),Image.Resampling.LANCZOS)

@lru_cache(maxsize=64)
def decoration(key,side):
    im=_canvas(side);_shadow(im);s=im.width/64;d=ImageDraw.Draw(im)
    def box(coords,fill,outline=None,r=0):
        q=tuple(round(v*s) for v in coords)
        if r:d.rounded_rectangle(q,radius=round(r*s),fill=fill,outline=outline,width=max(1,round(s*.6)))
        else:d.rectangle(q,fill=fill,outline=outline,width=max(1,round(s*.6)))
    def ellipse(coords,fill,outline=None):d.ellipse(tuple(v*s for v in coords),fill=fill,outline=outline,width=max(1,round(s*.7)))
    def line(points,fill,width=1):d.line(tuple(v*s for v in points),fill=fill,width=max(1,round(width*s)))
    def poly(points,fill,outline=None):d.polygon([(x*s,y*s) for x,y in points],fill=fill,outline=outline,width=max(1,round(s*.5)))
    if key=='plant':
        line((32,42,31,15),'#739780',1.8)
        for leaf,vein in ((((31,23),(19,23),(14,16),(21,12),(29,16),(32,23)),(20,16,30,23)),
                          (((31,30),(35,18),(45,14),(51,19),(43,28),(31,31)),(33,29,46,19)),
                          (((31,18),(26,9),(30,3),(37,8),(36,14),(31,20)),(31,17,32,7))):
            poly(leaf,'#98bca0','#bfd6ac');line(vein,'#6f9b82',.6)
        poly(((19,38),(46,38),(42,56),(24,56)),'#b98f94','#ebc8b8')
        ellipse((18,34,47,43),'#d8b3ac','#f0d1bd');ellipse((22,36,43,40),'#6c5c60')
        line((26,44,27,52),'#dfbbb0',1.6);ellipse((21,54,45,59),'#a8838c','#d0a59f')
    elif key=='paper_plane':
        box((22,53,45,57),'#aa9bbd','#d8c8e4',r=2);line((34,53,35,29),'#c3b1c8',.7)
        poly(((8,20),(56,8),(37,36),(29,26)),'#d6d8ee','#f0e9f9')
        poly(((8,20),(29,26),(45,15)),'#b2c1e3')
        poly(((29,26),(37,36),(36,21),(56,8)),'#9caed5','#e3d9ee')
        line((29,26,56,8),'#f4e7f5',.7);poly(((36,21),(37,36),(41,29)),'#7789b7')
        line((18,33,12,36,16,39),'#c8b6d5',.6)
    elif key=='moon_cushion':
        mask=Image.new('L',im.size);m=ImageDraw.Draw(mask);m.ellipse((12*s,7*s,53*s,55*s),fill=255)
        m.ellipse((29*s,1*s,64*s,43*s),fill=0)
        cloth=Image.new('RGBA',im.size,'#baa9d3');cloth.putalpha(mask);im.alpha_composite(cloth)
        d=ImageDraw.Draw(im)
        d.arc((13*s,8*s,52*s,54*s),78,278,fill='#e2d0ec',width=max(1,round(s*1.2)))
        for i in range(9):
            a=math.radians(100+i*19);x=32+17*math.cos(a);y=31+21*math.sin(a)
            line((x,y,x+.6,y+1),'#8f80ad',.5)
        poly(_star(23,30,4.1),'#edcf91','#fff0c8')
        ellipse((20,36,22,37),'#d4b7d7')
    elif key=='star_map':
        poly(((10,12),(50,7),(53,50),(13,55)),'#a78a9d','#e2c2ad')
        poly(((14,15),(46,11),(49,46),(17,51)),'#424761','#d2b58f')
        line((20,40,25,25,33,32,41,19,44,39),'#aebcd7',.7)
        for x,y in ((20,40),(25,25),(33,32),(41,19),(44,39)):ellipse((x-1,y-1,x+1,y+1),'#f1d7a3')
        poly(_star(25,25,2.5),'#f6dfb8');line((19,55,16,59),'#a58b9c',1.4);line((48,51,52,56),'#a58b9c',1.4)
    elif key=='star_lamp':
        glow=Image.new('RGBA',im.size);ImageDraw.Draw(glow).ellipse((11*s,1*s,54*s,42*s),fill=(234,206,152,37))
        im.alpha_composite(glow.filter(ImageFilter.GaussianBlur(s*3)));d=ImageDraw.Draw(im)
        box((29,34,35,54),'#b79a88','#dec5a7',r=2)
        ellipse((20,52,45,59),'#9e8c9e','#dcc1bc');ellipse((23,51,42,55),'#cdb6ad')
        ellipse((15,5,49,39),'#d7c8af','#f4dfb6')
        d.arc((17*s,7*s,47*s,37*s),-80,95,fill='#b7a7af',width=max(1,round(s*.8)))
        ellipse((20,9,25,19),'#f6e5c7');poly(_star(34,23,5),'#ae91ae','#ead8d6')
        ellipse((27,31,30,33),'#f2ddb8')
    else:raise ValueError('unknown decoration')
    return im.resize((side,side),Image.Resampling.LANCZOS)

@lru_cache(maxsize=32)
def floating(kind,side):
    if kind=='box':return parcel(side)
    if kind=='plane':return decoration('paper_plane',side).crop((0,0,side,round(side*.65)))
    im=_canvas(side);s=im.width/64;d=ImageDraw.Draw(im)
    d.polygon([(x*s,y*s) for x,y in _star(32,31,20)],fill='#ebcc93',outline='#ffe5b0',width=max(1,round(s)))
    d.polygon([(32*s,11*s),(32*s,31*s),(13*s,25*s)],fill='#f9e2ad')
    d.polygon([(32*s,31*s),(44*s,48*s),(32*s,41*s),(20*s,48*s)],fill='#c9a578')
    return im.resize((side,side),Image.Resampling.LANCZOS)

def place(canvas,tile,x,y):
    left,top=round(x-tile.width/2),round(y-tile.height/2)
    l,t=max(0,left),max(0,top);r,b=min(canvas.width,left+tile.width),min(canvas.height,top+tile.height)
    if r>l and b>t:canvas.alpha_composite(tile.crop((l-left,t-top,r-left,b-top)),(l,t))
