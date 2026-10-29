"""Local pointer play and caret watching, without reading a draft or moving a mouse.

All timers use world time. Catching needs a real hand/pointer overlap during the
jump; moving away can evade it. A caught actor follows until a directional shake,
pointer leave, typing, an interruption, or the bounded safety timeout releases it.
"""
from collections import deque
import math
from .geometry import stage_metrics, stage_position, stage_x


CLICK_STYLES = {
    'gpt': 'wave', 'claude': 'shy', 'deepseek': 'nod', 'gemini': 'sparkle',
    'grok': 'wink', 'kimi': 'peek', 'qwen': 'wave', 'llama': 'bounce',
    'minimax': 'sparkle', 'rwkv': 'nod', 'seed': 'bounce', 'perplexity': 'peek',
    'mistral': 'wink', 'glm': 'nod', 'wenxin': 'wave', 'jev': 'shy', 'hunyuan': 'sparkle',
}
FOCUS_STYLES = ('chin', 'lean', 'crouch', 'peek')


class Attention:
    def __init__(self):
        self.width, self.height = 960, 180
        self.labels = False
        self.point = None
        self.last_move = -100.0
        self.hover = None
        self.reactions = {}
        self.cooldowns = {}
        self.samples = deque(maxlen=24)
        self.cursor = None
        self.focus_start = None
        self.focus_until = -100.0
        self.look_schedules = {}
        self.approaches = {}
        self.focus_x = None

    def geometry(self, width, height, labels=False):
        self.width, self.height = int(width), int(height)
        self.labels = bool(labels)

    def _layout(self, world):
        ensemble = bool(world.spectacle and world.spectacle['kind'] == 'ultra')
        size, floor = stage_metrics(len(world.actors), self.width, self.height, self.labels, ensemble)
        return [(a, *stage_position({'x': a.x}, i, len(world.actors), self.width, size, floor, ensemble))
                for i, a in enumerate(world.actors)]

    def reset(self, world):
        self.point = None
        self.hover = None
        self.samples.clear()
        self.reactions.clear()
        self.focus_start = None
        self.focus_until = -100.0
        self.look_schedules.clear()
        self.approaches.clear()
        self.focus_x = None
        for a in world.actors:
            a.reaction = None
            a.attention = None

    def release(self, world):
        for a in world.actors:
            reaction = self.reactions.get(a.id)
            if reaction and reaction['kind'] in ('caught', 'jump'):
                lift = (a.reaction or {}).get('lift', reaction.get('lift', 0))
                self.reactions[a.id] = {'kind': 'land', 'start': world.t, 'lift': lift}
                self.cooldowns[a.id] = world.t + 3
                a.target = a.x
        self.samples.clear()

    def typing(self, world, cursor):
        if cursor is not None:
            self.cursor = dict(cursor)
        if self.cursor is None:
            return
        if self.focus_start is None or world.t > self.focus_until:
            self.focus_start = world.t
            self.focus_x = self.cursor['x']
            # Keep left/right order, but vary spacing, reaction delay and pace.
            actors = sorted(world.actors, key=lambda actor: actor.x)
            weights = [world.rng.uniform(.94, 1.16) for _ in actors]
            offsets = [0.0]
            for weight in weights[1:]:offsets.append(offsets[-1] + weight)
            midpoint = (offsets[0] + offsets[-1]) / 2
            self.approaches = {a.id: {'offset': offset-midpoint,
                'delay': world.rng.uniform(.06, .42), 'pace': world.rng.uniform(.82, 1.12)}
                for a, offset in zip(actors, offsets)}
            # A sampled subset occasionally checks the output, while the others
            # keep watching the input. Steady layout frames do not restart it.
            count = max(1, len(world.actors) // 2)
            selected = world.rng.sample(world.actors, min(count, len(world.actors)))
            self.look_schedules = {a.id: {'next': world.t + world.rng.uniform(.65, 1.9), 'until': -1}
                                   for a in selected}
        self.focus_until = world.t + 2.1
        self.release(world)
        self.reactions = {k: v for k, v in self.reactions.items() if v['kind'] == 'land'}

    def pointer(self, world, kind, x, y, button=0):
        if kind == 'leave':
            self.point = None
            self.hover = None
            self.release(world)
            if world.paused:
                self.reactions.clear()
                for actor in world.actors:
                    actor.reaction = None
            return
        if world.paused:
            return
        if world.phase in ('waiting', 'blocked') or world.spectacle or world.flight or world.t < world.typing_until:
            return
        px, py = x * self.width, y * self.height
        previous = self.point
        self.point = {'x': x, 'y': y}
        self.last_move = world.t
        self.samples.append((world.t, px, py))
        caught = next((k for k, r in self.reactions.items() if r['kind'] == 'caught'), None)
        if caught:
            if self._shaken(world.t):
                self.release(world)
            return
        hits = []
        overhead = []
        for a, cx, floor, size in self._layout(world):
            # The conservative body box sits inside the transparent sprite cell.
            if abs(px - cx) < size * .35 and floor - size * .94 <= py <= floor - size * .05:
                hits.append(a)
            if abs(px - cx) < size * .42 and floor - size * 1.25 <= py < floor - size * .70:
                overhead.append(a)
        hit = hits[-1] if hits else None
        active_hit = hit and self.reactions.get(hit.id, {}).get('kind') in ('jump', 'caught', 'land')
        if hit and not active_hit:
            hit.facing = 1 if px >= next(cx for a, cx, _, _ in self._layout(world) if a.id == hit.id) else -1
        if hit and hit.id != self.hover and not active_hit:
            self.reactions[hit.id] = {'kind': 'hover', 'start': world.t, 'style': 'curious'}
        self.hover = hit.id if hit else None
        if kind == 'down' and button == 0 and hit and not active_hit:
            self.reactions[hit.id] = {'kind': 'click', 'start': world.t, 'style': CLICK_STYLES.get(hit.id, 'wave')}
            hit.target, hit.v = hit.x, 0.0
            world._clear_interactions()
            world._clear_entrances()
            self.cooldowns[hit.id] = world.t + 1.2
        if world.reduced_motion or kind != 'move' or not overhead:
            return
        if any(r['kind'] in ('jump', 'caught', 'land') for r in self.reactions.values()):
            return
        candidate = min(overhead, key=lambda a: abs(a.x - x))
        moved = previous is None or math.hypot(x - previous['x'], y - previous['y']) > .002
        if moved and world.t >= self.cooldowns.get(candidate.id, -1):
            self.cooldowns[candidate.id] = world.t + 2.4
            if world.rng.random() < .38:
                if candidate.id == 'wenxin':
                    # The seated character reaches up while her chair stays put.
                    self.reactions[candidate.id] = {'kind': 'click', 'start': world.t, 'style': 'reach'}
                    candidate.target, candidate.v = candidate.x, 0.0
                    world._clear_interactions()
                    return
                self.reactions[candidate.id] = {'kind': 'jump', 'start': world.t, 'style': 'catch'}
                candidate.target = candidate.x
                candidate.v = 0
                world._clear_interactions()
                world._clear_entrances()

    def _shaken(self, now):
        points = [p for p in self.samples if now - p[0] <= .7]
        if len(points) < 5:
            return False
        # Require intentional travel in both directions, not device jitter.
        for axis, threshold in ((1, max(16, self.width * .018)), (2, max(12, self.height * .07))):
            direction, travel, reversals = 0, 0.0, 0
            anchor = points[0][axis]
            for sample in points[1:]:
                delta = sample[axis] - anchor
                if abs(delta) < threshold:
                    continue
                current = 1 if delta > 0 else -1
                travel += abs(delta)
                if direction and current != direction:
                    reversals += 1
                direction, anchor = current, sample[axis]
            if reversals >= 2 and travel >= threshold * 4:
                return True
        return False

    def step(self, world, dt):
        if world.reduced_motion or world.spectacle or world.phase in ('waiting', 'blocked'):
            self.release(world)
        if self.point and world.t - self.last_move > 4:
            self.point = None
            self.hover = None
            self.release(world)
        active_ids = {a.id for a in world.actors}
        self.reactions = {k: v for k, v in self.reactions.items() if k in active_ids}
        following = (self.cursor is not None and world.t < self.focus_until and not world.spectacle
                     and world.phase not in ('waiting', 'blocked'))
        if following:
            self.focus_x += (self.cursor['x']-self.focus_x)*(1-math.exp(-dt*4.5))
        for index, (a, cx, floor, size) in enumerate(self._layout(world)):
            a.attention = None
            a.reaction = None
            if following:
                plan = self.approaches[a.id]
                extent = max((abs(p['offset']) for p in self.approaches.values()), default=0)
                spacing = min(size, .84*(self.width-size)/max(1, extent*2))
                half_span = extent*spacing
                left = size/2 + .07*(self.width-size) + half_span
                right = size/2 + .93*(self.width-size) - half_span
                center = max(left, min(right, self.focus_x*self.width))
                a.target = stage_x(center + plan['offset']*spacing, self.width, size)
                style = FOCUS_STYLES[sum(map(ord, a.id)) % len(FOCUS_STYLES)]
                look = self.look_schedules.get(a.id)
                if look and world.t >= look['next']:
                    look['until'] = world.t + world.rng.uniform(.55, 1.05)
                    look['next'] = look['until'] + world.rng.uniform(1.8, 3.4)
                look_up = bool(look and world.t < look['until'])
                a.attention = {'kind': 'input', 'style': style, 'look_up': look_up,
                               'x': self.cursor['x'], 'y': self.cursor['y'],
                               'age': world.t - self.focus_start,
                               'delay': plan['delay'], 'pace': plan['pace']}
            reaction = self.reactions.get(a.id)
            if not reaction:
                continue
            kind = reaction['kind']
            age = world.t - reaction['start']
            duration = {'jump': .64, 'land': .45, 'click': 1.4, 'hover': 1.1, 'caught': 8.0}[kind]
            if age > duration or (kind == 'caught' and self.point is None):
                if kind == 'caught':
                    self.release(world)
                else:
                    self.reactions.pop(a.id, None)
                continue
            progress = min(1, max(0, age / duration))
            lift = 0.0
            if kind == 'jump':
                lift = .43 * math.sin(math.pi * progress)
                if self.point and .22 < progress < .76:
                    px, py = self.point['x'] * self.width, self.point['y'] * self.height
                    hand_x, hand_y = cx + a.facing * size * .10, floor - size * (.78 + lift)
                    if math.hypot(px - hand_x, py - hand_y) < size * .21:
                        reaction = self.reactions[a.id] = {'kind': 'caught', 'start': world.t, 'style': 'catch'}
                        self.samples.clear()
                        kind, progress = 'caught', 0.0
            if kind == 'caught':
                if self.point:
                    target_x = stage_x(self.point['x'] * self.width - a.facing * size * .10, self.width, size)
                    a.x += (target_x - a.x) * (1 - math.exp(-dt * 28))
                    lift = max(-.04, min(max(0, floor/size-1.18), (floor - self.point['y'] * self.height) / size - .78))
                a.target, a.v = a.x, 0.0
                reaction['lift'] = lift
            elif kind == 'land':
                lift = reaction['lift'] * (1 - progress) ** 2
                if progress > .65:
                    lift -= math.sin((progress - .65) / .35 * math.pi) * .035
            a.reaction = {'kind': kind, 'style': reaction.get('style', 'catch'),
                          'progress': progress, 'lift': lift,
                          'tilt': math.sin(age * 8) * 8 if kind == 'caught' else 0}

    def snapshot(self):
        caught = next((key for key, r in self.reactions.items() if r['kind'] == 'caught'), None)
        return {'position': dict(self.point) if self.point else None, 'hover': self.hover,
                'caught': caught, 'cursor': dict(self.cursor) if self.cursor else None}

    def gaze_direction(self, world, actor):
        size, floor = stage_metrics(len(world.actors), self.width, self.height, self.labels)
        center, _, _ = stage_position({'x': actor.x}, 0, len(world.actors), self.width, size, floor)
        return 1 if actor.attention['x'] * self.width >= center else -1
