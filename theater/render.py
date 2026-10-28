"""Transparent composition; does not write terminal escape sequences."""
from pathlib import Path
import math
from PIL import Image, ImageDraw, ImageFont
from .world import NAMES

ROOT = Path(__file__).resolve().parents[1]
FONT_PATH = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
COLORS = {"gpt": "#c7b7ff", "deepseek": "#83b9f6", "claude": "#eac2a0",
          "gemini": "#bcb5fb", "seed": "#91dbda", "grok": "#dbb28d"}

class Renderer:
    def __init__(self, assets=None):
        self.assets = Path(assets or ROOT / "assets/cast")
        self.cache = {}
        self.fonts = {}

    def font(self, size):
        if size not in self.fonts:
            self.fonts[size] = ImageFont.truetype(FONT_PATH, size)
        return self.fonts[size]

    def sprite(self, actor, t, height):
        pose = actor["pose"]
        if pose.startswith("walk"):
            # Distance-based gait: no stationary running or abrupt restart every draw.
            index = (4 if pose == "walk_right" else 8) + int(actor["travel"] * 80) % 4
        elif pose == "idle":
            blink = t % 5.8
            index = 1 if 5.35 < blink < 5.46 else 2 if 5.46 <= blink < 5.60 else 3 if 5.60 <= blink < 5.7 else 0
        else:
            index = {"wave": 12, "talk": 13, "surprise": 14, "rest": 15}.get(pose, 0)
        key = (actor["id"], index, height)
        if key not in self.cache:
            path = self.assets / actor["id"] / "frames" / f"{index:02}.png"
            if not path.exists():
                raise FileNotFoundError(f"missing production sprite: {path}")
            im = Image.open(path).convert("RGBA")
            im.thumbnail((height * 2, height), Image.Resampling.LANCZOS)
            self.cache[key] = im
        return self.cache[key]

    def frame(self, state, width=960, height=180, labels=False):
        width, height = max(160, min(2560, int(width))), max(48, min(480, int(height)))
        canvas = Image.new("RGBA", (width, height))
        draw = ImageDraw.Draw(canvas)
        scale = min(1.5, height / 170)
        size = max(38, min(int(height * .72), int(width / (len(state["cast"])+1) * .85)))
        floor = height - (int(19 * scale) if labels else 2)
        t = state["time"]
        quiet = state["quiet"]
        for i, a in enumerate(state["cast"]):
            sprite = self.sprite(a, t, size)
            x = int(a["x"] * (width - size) + size / 2)
            bob = 0 if state["reduced_motion"] or quiet else (math.sin(t*2.4+i) * .8)
            if state["scene"] == "celebrate" and not quiet:
                bob -= max(0, math.sin(state["scene_age"] * 5 + i)) * 7 * scale
            y = floor - sprite.height + int(bob)
            canvas.alpha_composite(sprite, (x - sprite.width // 2, y))
            if labels:
                text = NAMES[a["id"]]
                f = self.font(max(10, int(11*scale)))
                box = draw.textbbox((0,0),text,font=f)
                draw.text((x-(box[2]-box[0])/2, floor+2), text, font=f, fill="#d7d2e8")
            if a["bubble_until"] > t and a["bubble"] and not quiet:
                # At most one live speaker; the other waits for its cue.
                f = self.font(max(11, int(13*scale)))
                text = a["bubble"]
                bb = draw.textbbox((0,0),text,font=f)
                bw, bh = bb[2]-bb[0]+18, max(21, bb[3]-bb[1]+13)
                bx = max(2, min(width-bw-2, x-bw//2))
                by = max(1, y-bh-6)
                draw.rounded_rectangle((bx,by,bx+bw,by+bh), radius=9, fill="#f8f3ffff", outline=COLORS.get(a["id"],"#c9bddc"), width=1)
                draw.polygon([(x-4,by+bh-1),(x+4,by+bh-1),(x,by+bh+5)],fill="#f8f3ff")
                draw.text((bx+9,by+4-bb[1]),text,font=f,fill="#463859")
        # Tiny scene props are code-native shapes; character artwork is generated art.
        age = state["scene_age"]
        if state["scene"] in ("cookie", "paperball") and not quiet:
            px = int(width * (.5 + .25*math.sin(age*.65)))
            py = floor - int(15*scale + abs(math.sin(age*2))*18*scale)
            r = max(3, int(6*scale))
            if state["scene"] == "cookie":
                draw.ellipse((px-r,py-r,px+r,py+r),fill="#e5b67e",outline="#8e5d42")
                for dx,dy in [(-2,-2),(2,0),(0,3)]:
                    draw.ellipse((px+dx-1,py+dy-1,px+dx+1,py+dy+1),fill="#71503e")
            else:
                draw.ellipse((px-r,py-r,px+r,py+r),fill="#f0edf9",outline="#a89bbb")
                draw.line((px-3,py,px+2,py-3,px+1,py+3),fill="#b5acc5")
        return canvas
