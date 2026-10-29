"""Small reaction accents; the real cursor and input remain entirely native."""
import math
from PIL import ImageDraw


def accents(canvas, state, actor, x, floor, size, still=False):
    draw = ImageDraw.Draw(canvas)
    reaction, attention = actor.get('reaction'), actor.get('attention')
    if reaction and not still:
        progress = reaction['progress']
        strength = math.sin(math.pi * progress) if reaction['kind'] != 'caught' else .8
        color = (222, 196, 255, round(220 * max(0, strength)))
        y = floor - size * (.84 + reaction.get('lift', 0))
        if reaction['kind'] == 'caught':
            pointer = state.get('pointer', {}).get('position')
            if pointer:
                px, py = pointer['x'] * canvas.width, pointer['y'] * canvas.height
                # A tiny luminous thread makes the hand contact readable.
                draw.line((x + actor.get('facing', 1) * size * .10, y + size * .06, px, py), fill=color, width=2)
                for i in range(4):
                    angle = state['time'] * 2 + i * math.pi / 2
                    dx, dy = math.cos(angle) * 5, math.sin(angle) * 5
                    draw.ellipse((px + dx - 1, py + dy - 1, px + dx + 1, py + dy + 1), fill=color)
        elif reaction['kind'] in ('hover', 'click'):
            count = 3 if reaction['kind'] == 'click' else 1
            for i in range(count):
                px = x + (i - (count - 1) / 2) * size * .17
                py = y - size * (.04 + progress * .14) + math.sin(i + progress * 6) * 2
                r = max(1, size * .022 * strength)
                if reaction.get('style') in ('shy', 'wink', 'wave'):
                    draw.polygon([(px, py + r * 2), (px - r * 2, py), (px - r, py - r), (px, py), (px + r, py - r), (px + r * 2, py)], fill=color)
                else:
                    draw.line((px - r * 2, py, px + r * 2, py), fill=color, width=1)
                    draw.line((px, py - r * 2, px, py + r * 2), fill=color, width=1)
    if attention and not still and abs(actor.get('v', 0)) < .015:
        # Thought dots are beside the head, below the transcript and above input.
        direction = -1 if attention.get('look_up') else actor.get('facing', 1)
        px, py = x + direction * size * .25, floor - size * .77
        for i in range(3):
            alpha = int(80 + 100 * (.5 + .5 * math.sin(state['time'] * 2.5 - i)))
            cx, cy = px + direction * i * 4, py - i * 2
            draw.ellipse((cx - 1, cy - 1, cx + 1, cy + 1), fill=(215, 205, 239, alpha))
