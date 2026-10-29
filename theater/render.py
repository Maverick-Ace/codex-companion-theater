"""Transparent composition; does not write terminal escape sequences."""
from pathlib import Path
import math
from PIL import Image, ImageDraw, ImageFont
from .world import NAMES
from .motion import PuppetRig
from .stagecraft import power_backdrop, power_foreground, scene_details
from .scenery import draw_set
from .hand_props import draw_held, engagement
from .props import position

ROOT = Path(__file__).resolve().parents[1]
FONT_PATH = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
COLORS = {"gpt": "#c7b7ff", "deepseek": "#83b9f6", "claude": "#eac2a0",
          "gemini": "#bcb5fb", "seed": "#91dbda", "grok": "#dbb28d"}

def composite_clipped(canvas, sprite, x, y):
    """Clip source pixels explicitly; neither source nor destination may wrap."""
    left,top=max(0,x),max(0,y)
    right,bottom=min(canvas.width,x+sprite.width),min(canvas.height,y+sprite.height)
    if right>left and bottom>top:
        canvas.alpha_composite(sprite.crop((left-x,top-y,right-x,bottom-y)),(left,top))

def portal(draw,x,floor,size,progress,seed):
    strength=math.sin(math.pi*max(0,min(1,progress)))
    radius=max(2,int(size*.42*strength))
    color=(195,159,255,int(230*strength))
    draw.ellipse((x-radius,floor-7,x+radius,floor+1),outline=color,width=2)
    for n in range(18):
        angle=n*2.399+seed
        spread=(.12+((n*17)%19)/28)*size*strength
        px=x+math.cos(angle+progress*2)*spread*.65
        py=floor-size*(progress*.8+(n%5)*.035)
        r=1+(n%3==0)
        draw.ellipse((px-r,py-r,px+r,py+r),fill=(218,198,255,int(220*strength)))

class Renderer:
    def __init__(self, assets=None):
        self.assets = Path(assets or ROOT / "assets/cast")
        self.cache = {}
        self.fonts = {}
        self.rig = PuppetRig()

    def font(self, size):
        if size not in self.fonts:
            self.fonts[size] = ImageFont.truetype(FONT_PATH, size)
        return self.fonts[size]

    def _source(self, actor_id, index, height):
        key = (actor_id, index, height)
        if key not in self.cache:
            path = self.assets / actor_id / "frames" / f"{index:02}.png"
            if not path.exists():
                raise FileNotFoundError(f"missing production sprite: {path}")
            with Image.open(path) as source:
                im = source.convert("RGBA")
            im.thumbnail((height * 2, height), Image.Resampling.LANCZOS)
            self.cache[key] = im
        return self.cache[key]

    def sprite(self, actor, t, height, still=False):
        pose = actor["pose"]
        contact = actor.get('interaction')
        if contact and contact['active'] and contact['action'] in ('type','write','water','stir','serve','unpack','inspect'):
            pose = 'idle'
        next_index = None
        mix = 0
        if pose.startswith("walk"):
            gait = actor["travel"] * 80
            first = 4 if pose == "walk_right" else 8
            index = first + int(gait) % 4
            next_index = first + (int(gait) + 1) % 4
            # Ease between drawings, with continuous joint motion in between.
            mix = (gait % 1) ** 2 * (3 - 2 * (gait % 1))
        elif pose == "idle":
            blink = t % 5.8
            index = 1 if 5.35 < blink < 5.46 else 2 if 5.46 <= blink < 5.60 else 3 if 5.60 <= blink < 5.7 else 0
        else:
            index = {"wave": 12, "talk": 13, "surprise": 14, "rest": 15}.get(pose, 0)
        im = self._source(actor["id"], index, height)
        if next_index is not None and mix > .01 and not still:
            other = self._source(actor["id"], next_index, height)
            im = Image.blend(im, other, mix)
        return self.rig.animate(im, actor, t, still=still)

    def frame(self, state, width=960, height=180, labels=False):
        width, height = max(160, min(2560, int(width))), max(48, min(480, int(height)))
        canvas = Image.new("RGBA", (width, height))
        draw = ImageDraw.Draw(canvas)
        scale = min(1.5, height / 170)
        size = max(38, min(int(height * .72), int(width / (len(state["cast"])+1) * .85)))
        floor = height - (int(19 * scale) if labels else 2)
        t = state["time"]
        quiet = state["quiet"]
        still = state["reduced_motion"] or quiet
        effect = state.get('spectacle')
        ensemble = bool(effect and effect['kind'] == 'ultra')
        if ensemble:
            size = max(18, min(int(height*.43), int(width/9*.88)))
        draw_set(canvas,state,floor,size)
        def placement(a, index):
            if ensemble and 'departure' not in a:
                row, column = (0,index) if index<8 else (1,index-8)
                count=8 if row==0 else 9
                return int((column+1)*width/(count+1)), floor-int(size*.58) if row==0 else floor, int(size*.9) if row==0 else size
            return position(a['x'],width,size),floor,size
        positions=[placement(a,i) for i,a in enumerate(state['cast'])]
        power_backdrop(canvas,state,floor,size,positions)
        actors=([] if ensemble else state.get('departing',[]))+state['cast']
        for i, a in enumerate(actors):
            index=next((j for j,item in enumerate(state['cast']) if item['id']==a['id']),0)
            x, actor_floor, actor_size = placement(a,index)
            contact=a.get('interaction')
            if contact and contact['active'] and contact['action']=='sit' and a['id']!='wenxin' and not still:
                actor_floor-=round(20*max(.65,min(1.8,actor_size/110))*engagement(contact['progress']))
            sprite = self.sprite(a, t, actor_size, still=still)
            bob = 0 if state["reduced_motion"] or quiet else (math.sin(t*2.4+i) * .8)
            if a.get('gesture') == 'bounce' and not still:
                bob -= max(0, math.sin(t*3.8*a.get('tempo',1)+i))*4*scale
            if state["scene"] in ("celebrate","power_max","power_ultra") and not still:
                bob -= max(0, math.sin(state["scene_age"] * 5 + i)) * 7 * scale
            # Mesh padding is transparent and must not lift the character off the floor.
            pad = max(3,round(actor_size*.055)) if not still else 0
            y = actor_floor - sprite.height + pad + int(bob)
            active_portal=False
            if not state['reduced_motion'] and not quiet:
                if 'departure' in a:
                    progress=(t-a['departure'])/1.2
                    opacity=max(0,1-progress*2)
                    active_portal=0<=progress<1
                else:
                    progress=(t-a.get('arrival',-10))/1.2
                    opacity=max(0,min(1,(progress-.45)/.55)) if 0<=progress<1 else 1
                    active_portal=0<=progress<1
                if active_portal:
                    sprite=sprite.copy()
                    sprite.putalpha(sprite.getchannel('A').point(lambda p:int(p*opacity)))
                    portal(draw,x,actor_floor,actor_size,progress,i*.7)
            elif 'departure' in a:
                continue
            partners=[p for p in state['cast'] if p['id'] in state.get('pair',[])]
            if state['scene']=='whisper' and a['id'] in state.get('pair',[]) and len(partners)==2 and abs(partners[0]['x']-partners[1]['x'])<.14 and not quiet and not state['reduced_motion']:
                partner=state['pair'].index(a['id'])
                angle=(7 if partner==0 else -7)*(.65+.35*math.sin(t*3))
                sprite=sprite.rotate(-angle,resample=Image.Resampling.BICUBIC,expand=True)
                y=actor_floor-sprite.height+pad
            composite_clipped(canvas,sprite,x-sprite.width//2,y)
            if 'departure' in a:continue
            if not active_portal:
                draw_held(canvas,state,a,x,actor_floor,actor_size)
            if labels:
                text = NAMES[a["id"]]
                f = self.font(max(10, int(11*scale)))
                box = draw.textbbox((0,0),text,font=f)
                draw.text((x-(box[2]-box[0])/2, actor_floor+2), text, font=f, fill="#d7d2e8")
            if a["bubble_until"] > t and a["bubble"] and not quiet:
                # At most one live speaker; the other waits for its cue.
                f = self.font(max(11, int(13*scale)))
                text = a["bubble"]
                bb = draw.textbbox((0,0),text,font=f)
                bw, bh = bb[2]-bb[0]+18, max(21, bb[3]-bb[1]+13)
                bx = max(2, min(width-bw-2, x-bw//2))
                by = max(1, y-bh-6)
                draw.rounded_rectangle((bx,by,bx+bw,by+bh), radius=9, fill="#f8f3ffff", outline=a.get('accent',COLORS.get(a["id"],"#c9bddc")), width=1)
                draw.polygon([(x-4,by+bh-1),(x+4,by+bh-1),(x,by+bh+5)],fill="#f8f3ff")
                draw.text((bx+9,by+4-bb[1]),text,font=f,fill="#463859")
        # Tiny scene props are code-native shapes; character artwork is generated art.
        age = state["scene_age"]
        if state['scene']=='whisper' and len(state.get('pair',[]))==2 and not still:
            pair=[a for a in state['cast'] if a['id'] in state['pair']]
            if len(pair)==2 and abs(pair[0]['x']-pair[1]['x'])<.1:
                px=int(sum(a['x'] for a in pair)/2*(width-size)+size/2)
                py=max(6,floor-size-9)
                draw.rounded_rectangle((px-22,py-7,px+22,py+8),radius=7,fill='#f8f3ffec')
                for j in range(3):
                    dy=math.sin(t*4+j)*2
                    draw.ellipse((px-11+j*10,py+dy-1,px-8+j*10,py+dy+2),fill='#8061a7')
        if state["scene"] in ("cookie", "paperball") and not quiet:
            prop_age = 0 if still else age
            px = int(width * (.5 + .25*math.sin(prop_age*.65)))
            py = floor - int(15*scale + abs(math.sin(prop_age*2))*18*scale)
            r = max(3, int(6*scale))
            if state["scene"] == "cookie":
                draw.ellipse((px-r,py-r,px+r,py+r),fill="#e5b67e",outline="#8e5d42")
                for dx,dy in [(-2,-2),(2,0),(0,3)]:
                    draw.ellipse((px+dx-1,py+dy-1,px+dx+1,py+dy+1),fill="#71503e")
            else:
                draw.ellipse((px-r,py-r,px+r,py+r),fill="#f0edf9",outline="#a89bbb")
                draw.line((px-3,py,px+2,py-3,px+1,py+3),fill="#b5acc5")
        scene_details(canvas,state,floor,size)
        power_foreground(canvas,state)
        return canvas
