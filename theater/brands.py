"""Locally bundled source-attributed marks, displayed inside teleport medallions.

The mark itself keeps its source colors and proportions. Only the surrounding
rings, particles and light are theater artwork. Nothing is downloaded at runtime.
"""
from functools import lru_cache
import json
import math
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter

ASSETS = Path(__file__).resolve().parents[1] / 'assets/brands'
BRANDS = json.loads((ASSETS / 'sources.json').read_text())['characters']


def _composite(canvas, image, x, y):
    x, y = round(x), round(y)
    left, top = max(0, x), max(0, y)
    right, bottom = min(canvas.width, x+image.width), min(canvas.height, y+image.height)
    if right > left and bottom > top:
        canvas.alpha_composite(image.crop((left-x, top-y, right-x, bottom-y)), (left, top))


@lru_cache(maxsize=192)
def brand_badge(actor_id, diameter):
    """Fit a complete, unmodified mark with neutral clear space, at 2x sampling."""
    diameter = max(12, min(160, int(diameter)))
    side = diameter * 2
    badge = Image.new('RGBA', (side, side))
    draw = ImageDraw.Draw(badge)
    draw.ellipse((1, 1, side-2, side-2), fill='#faf9f5', outline='#dedbd5', width=2)
    with Image.open(ASSETS / BRANDS[actor_id]['file']) as source:
        mark = source.convert('RGBA')
    mark.thumbnail((round(side*.68), round(side*.68)), Image.Resampling.LANCZOS)
    badge.alpha_composite(mark, ((side-mark.width)//2, (side-mark.height)//2))
    return badge.resize((diameter, diameter), Image.Resampling.LANCZOS)


@lru_cache(maxsize=96)
def _halo(side, color):
    layer = Image.new('RGBA', (side, side))
    d = ImageDraw.Draw(layer)
    d.ellipse((side*.16, side*.16, side*.84, side*.84), fill=(*color, 48))
    return layer.filter(ImageFilter.GaussianBlur(max(1, side*.11)))


def draw_brand_portal(canvas, actor_id, x, floor, size, progress, seed=0):
    """Draw a bounded 1.2s sigil, without distorting/rotating the official mark.

    ``progress`` is normalized [0,1]; both endpoints leave the canvas untouched.
    The renderer owns actor opacity and supplies arrival or departure progress.
    """
    if actor_id not in BRANDS or not 0 < progress < 1:
        return
    info = BRANDS[actor_id]
    color = tuple(bytes.fromhex(info['accent'].lstrip('#')))
    size = max(18, min(360, int(size)))
    strength = math.sin(math.pi*progress) ** .7
    # Draw only into a small local tile, not the whole terminal frame.
    tile_w, tile_h = round(size*1.6)+8, round(size*1.35)+10
    tile = Image.new('RGBA', (tile_w*2, tile_h*2))
    d = ImageDraw.Draw(tile)
    cx, base = tile_w, (tile_h-5)*2
    s = size*2
    alpha = round(210*strength)
    r = s*(.24+.16*strength)
    d.ellipse((cx-r,base-s*.055,cx+r,base+s*.018), outline=(*color,alpha), width=3)
    d.ellipse((cx-r*.73,base-s*.032,cx+r*.73,base+s*.01), outline=(*color,alpha//2), width=2)
    # Sparse orbital traces preserve contrast for the recognizable central mark.
    cy = base-s*.57
    radius = s*(.39+.04*math.sin(progress*math.pi))
    pattern = info['effect']
    for n in range(3):
        angle = progress*110+n*120+seed*13
        bounds = (cx-radius,cy-radius*1.06,cx+radius,cy+radius*1.06)
        d.arc(bounds,angle,angle+53,fill=(*color,round(alpha*.55)),width=2)
    for n in range(12):
        turn = n*2.39996+seed
        distance = s*(.18+(n%4)*.06)*strength
        px = cx+math.cos(turn+progress*1.3)*distance
        py = base-s*(progress*.85+(n%5)*.055)
        radius_px = 1.4+(n%3==0)*1.1
        if pattern == 'pixels':
            d.rectangle((px-radius_px,py-radius_px,px+radius_px,py+radius_px),fill=(*color,alpha))
        elif pattern == 'rays' and n%2==0:
            d.line((px-radius_px*2,py,px+radius_px*2,py),fill=(*color,alpha),width=2)
            d.line((px,py-radius_px*2,px,py+radius_px*2),fill=(*color,alpha),width=2)
        else:
            d.ellipse((px-radius_px,py-radius_px,px+radius_px,py+radius_px),fill=(*color,alpha))
    tile = tile.resize((tile_w,tile_h), Image.Resampling.LANCZOS)
    # The logo medallion is strongest before the sprite finishes materializing.
    badge_strength = min(1,progress/.18)*min(1,(1-progress)/.30)
    diameter = max(16,round(size*.43))
    badge = brand_badge(actor_id,diameter).copy()
    badge.putalpha(badge.getchannel('A').point(lambda p:round(p*badge_strength)))
    center_y = tile_h-5-size*.71-math.sin(progress*math.pi)*size*.045
    halo_side = round(diameter*1.7)
    halo = _halo(halo_side,color).copy()
    halo.putalpha(halo.getchannel('A').point(lambda p:round(p*badge_strength)))
    _composite(tile,halo,tile_w/2-halo_side/2,center_y-halo_side/2)
    _composite(tile,badge,tile_w/2-diameter/2,center_y-diameter/2)
    _composite(canvas,tile,x-tile_w/2,floor-(tile_h-5))
