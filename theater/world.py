"""Deterministic, elapsed-time animation and social scene scheduling.

Coordinates are normalized to the usable stage. Rendering never advances time.
Only metadata enters this module: no prompt, transcript, or tool payloads.
"""
from dataclasses import dataclass, asdict
import math
import random
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_catalog = json.loads((ROOT / "assets/cast/catalog.json").read_text())["characters"]
NAMES = {c["id"]: c["name"] for c in _catalog}
_preferred = ["gpt", "deepseek", "claude", "gemini"]
CAST = [k for k in _preferred if k in NAMES] + [k for k in NAMES if k not in _preferred]
SCENES = json.loads((ROOT / "config/scenes.json").read_text())

@dataclass
class Actor:
    id: str
    x: float
    target: float
    v: float = 0.0
    facing: int = 1
    pose: str = "idle"
    bubble: str = ""
    bubble_until: float = 0.0
    travel: float = 0.0

class World:
    def __init__(self, seed=7, cast=None, density=4):
        self.rng = random.Random(seed)
        self.pool = list(cast or CAST)
        self.density = max(1, min(5, density))
        self.actors = []
        self.t = 0.0
        self.phase = "idle"
        self.model = ""
        self.typing_until = 0.0
        self.paused = False
        self.reduced_motion = False
        self.scene = "roam"
        self.scene_start = 0.0
        self.scene_end = 0.0
        self.next_scene = 5.0
        self.next_roam = 1.0
        self.next_visit = 55.0
        self.generation = 0
        self._populate(self.pool[:self.density])

    def _populate(self, ids):
        old = {a.id: a for a in self.actors}
        n = len(ids)
        self.actors = [old.get(k, Actor(k, (i + 1) / (n + 1), (i + 1) / (n + 1)))
                       for i, k in enumerate(ids)]
        self.generation += 1

    def set_cast(self, ids):
        if not ids or any(k not in CAST for k in ids) or len(ids) != len(set(ids)):
            raise ValueError("cast must contain distinct known character IDs")
        self.pool = list(ids)
        self._populate(ids[:self.density])
        return self.snapshot()

    def activity(self, phase=None, model=None, typing=False):
        if model is not None:
            self.model = model
        if typing:
            self.typing_until = self.t + 1.3
        if phase and phase != self.phase:
            if phase not in ("idle", "working", "waiting", "ready", "blocked"):
                raise ValueError("unknown phase")
            previous = self.phase
            self.phase = phase
            if phase == "working":
                self.scene = "work"
                for i, a in enumerate(self.actors):
                    a.target = .13 + i * .19
                    a.bubble = "开工，我来帮忙。" if i == 0 else ""
                    a.bubble_until = self.t + 2.5
            elif phase in ("waiting", "blocked"):
                self.scene = "waiting"
                for a in self.actors:
                    a.target = a.x
                self.say(0, "等你点头再出发。", 4)
            elif previous == "working" and phase in ("idle", "ready"):
                self.start_scene("celebrate")

    def say(self, index, text, duration=3.0):
        if index < len(self.actors):
            a = self.actors[index]
            a.bubble, a.bubble_until = text, self.t + duration

    def start_scene(self, name):
        if name not in SCENES and name != "roam":
            raise ValueError("unknown scene")
        self.scene, self.scene_start = name, self.t
        self.scene_end = self.t + (12 if name in ("cookie", "paperball", "parade") else 9)
        self.next_scene = self.scene_end + self.rng.uniform(4, 8)
        for i, a in enumerate(self.actors):
            a.bubble = ""
            if name in ("chat", "tea", "celebrate"):
                a.target = .36 + i * .16 if i < 2 else (.12 if i == 2 else .88)
            elif name in ("cookie", "paperball"):
                a.target = .30 + i * .19
            elif name == "parade":
                a.target = .14 + i * .17
        if name in SCENES:
            lines = self.rng.choice(SCENES[name])
            self.say(0, lines[0], 4)
            # Reply starts later, rather than two simultaneous speech balloons.
            self.reply = lines[1]
        return self.snapshot()

    def tick(self, dt):
        if self.paused:
            return
        # Substeps preserve collision behavior after delayed frames, bounded to avoid catch-up storms.
        remaining = max(0, min(float(dt), .5))
        while remaining > 1e-8:
            step = min(remaining, 1 / 60)
            self._step(step)
            remaining -= step

    def _step(self, dt):
        self.t += dt
        quiet = self.t < self.typing_until
        social = self.phase in ("idle", "ready") and not quiet
        age = self.t - self.scene_start
        if social and self.scene != "roam" and self.t >= self.scene_end:
            self.scene = "roam"
        if social and self.t >= self.next_scene:
            self.start_scene(self.rng.choice(["chat", "cookie", "paperball", "tea", "parade"]))
        if social and 4.1 < age < 4.2 and self.scene in SCENES:
            self.say(1, getattr(self, "reply", "好呀。"), 3.5)
        if social and self.scene == "roam" and self.t >= self.next_roam:
            self.next_roam = self.t + self.rng.uniform(3, 6)
            a = self.rng.choice(self.actors)
            a.target = self.rng.uniform(.09, .91)
        if social and self.t >= self.next_visit and len(self.pool) > len(self.actors):
            self.next_visit = self.t + 55
            incoming = self.pool.pop(0)
            self.pool.append(incoming)
            ids = self.pool[:self.density]
            self._populate(ids)
            self.say(0, "换我来值班啦。")
        if social and self.scene in ("cookie", "paperball", "parade") and age > 4:
            for i, a in enumerate(self.actors[:2]):
                a.target = .5 + .29 * math.sin(age * .65 + i * 1.5)
        ordered = sorted(self.actors, key=lambda a: a.x)
        for i, a in enumerate(ordered):
            desired = max(-.14, min(.14, (a.target - a.x) * 1.8))
            if quiet or self.reduced_motion:
                desired = 0.0
            # Yield to an actor in front, preventing bodies from passing through each other.
            if desired > 0 and i + 1 < len(ordered) and ordered[i+1].x - a.x < .12:
                desired = min(desired, max(0, (ordered[i+1].x - a.x - .10) * 1.8))
            if desired < 0 and i > 0 and a.x - ordered[i-1].x < .12:
                desired = max(desired, min(0, (a.x - ordered[i-1].x - .10) * -1.8))
            a.v += (desired - a.v) * (1 - math.exp(-dt * 9))
            a.x = max(.07, min(.93, a.x + a.v * dt))
            a.travel += abs(a.v) * dt
            if abs(a.v) > .008:
                a.facing = 1 if a.v > 0 else -1
                a.pose = "walk_right" if a.facing == 1 else "walk_left"
            elif quiet or self.reduced_motion:
                a.pose = "idle"
            elif self.scene == "tea":
                a.pose = "rest"
            elif self.scene == "celebrate":
                a.pose = "wave"
            elif self.scene == "paperball" and age % 4 < .6:
                a.pose = "surprise"
            elif a.bubble and a.bubble_until > self.t:
                a.pose = "talk"
            else:
                a.pose = "idle"

    def snapshot(self):
        return {"time": round(self.t, 3), "scene": self.scene, "scene_age": self.t-self.scene_start,
                "phase": self.phase, "model": self.model, "quiet": self.t < self.typing_until,
                "paused": self.paused, "reduced_motion": self.reduced_motion,
                "cast": [asdict(a) for a in self.actors], "pool": self.pool,
                "generation": self.generation}
