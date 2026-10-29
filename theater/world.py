"""Elapsed-time stage choreography, local dialogue and model-inspired personalities.

Only display metadata enters this module. Personality is fiction, not a model
capability claim, and all dialogue is authored locally rather than sent to an API.
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
PERSONALITIES = json.loads((ROOT / "config/personalities.json").read_text())
ENVIRONMENTS = {"home": "home", "office": "office", "work": "office",
                "dinner": "dinner", "outing": "outing", "stargaze": "outing",
                "tea": "home"}
SOCIAL_SCENES = ["chat", "cookie", "paperball", "tea", "parade", "whisper",
                 "home", "office", "dinner", "outing", "highfive", "photo", "stargaze"]

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
    arrival: float = -10.0
    gesture: str = "sway"
    temperament: str = ""
    tempo: float = 1.0
    accent: str = "#c7b7ff"

class World:
    def __init__(self, seed=7, cast=None, density=4):
        self.rng = random.Random(seed)
        self.pool = list(cast or CAST)
        self.density = max(1, min(5, density))
        self.actors = []
        self.departing = []
        self.pair = []
        self.t = 0.0
        self.phase = "idle"
        self.model = ""
        self.effort = "medium"
        self._effort_seen = False
        self.spectacle = None
        self._saved_stage = None
        self.typing_until = 0.0
        self.paused = False
        self.reduced_motion = False
        self.scene = "roam"
        self.environment = "none"
        self.scene_start = 0.0
        self.scene_end = 0.0
        self.next_scene = 5.0
        self.next_roam = 1.0
        self.next_visit = 55.0
        self.generation = 0
        self.dialogue = []
        self._populate(self.pool[:self.density])

    def _new_actor(self, identifier, x, arrival):
        p = PERSONALITIES[identifier]
        return Actor(identifier, x, x, arrival=arrival, gesture=p["gesture"],
                     temperament=p["temperament"], tempo=p["tempo"], accent=p["accent"])

    def _populate(self, ids):
        old = {a.id: a for a in self.actors}
        self.departing = [d for d in self.departing if d["id"] not in ids]
        self.departing.extend(dict(asdict(a), departure=self.t) for a in self.actors if a.id not in ids)
        n = len(ids)
        self.actors = [old[k] if k in old else self._new_actor(k, (i+1)/(n+1), self.t if old else -10.0)
                       for i, k in enumerate(ids)]
        self.pair = []
        self.dialogue = []
        self.generation += 1

    def set_cast(self, ids):
        if not ids or any(k not in CAST for k in ids) or len(ids) != len(set(ids)):
            raise ValueError("cast must contain distinct known character IDs")
        self.cancel_spectacle()
        self.pool = list(ids)
        self._populate(ids[:self.density])
        return self.snapshot()

    def set_density(self, value):
        density = max(1, min(5, int(value)))
        self.cancel_spectacle()
        self.density = density
        self._populate(self.pool[:density])
        return self.snapshot()

    def set_effort(self, effort, baseline=False):
        if not isinstance(effort, str) or not effort.strip() or len(effort) > 40:
            raise ValueError("effort must be a nonempty short string")
        effort = effort.strip().lower()
        previous = self.effort
        self.effort = effort
        self._effort_seen = True
        if previous == effort:
            return self.snapshot()
        if baseline:
            self.cancel_spectacle()
            return self.snapshot()
        self.typing_until = self.t
        self.cancel_spectacle()
        if effort not in ("max", "ultra"):
            return self.snapshot()
        self._saved_stage = {
            "actors": [Actor(**asdict(a)) for a in self.actors],
            "scene": self.scene, "environment": self.environment,
            "scene_age": self.t-self.scene_start,
            "scene_left": max(0, self.scene_end-self.t),
            "next_scene": max(0, self.next_scene-self.t),
            "next_visit": max(0, self.next_visit-self.t),
            "next_roam": max(0, self.next_roam-self.t),
            "pair": self.pair[:], "phase": self.phase,
        }
        self.spectacle = {"kind": effort, "start": self.t, "duration": 8.0 if effort == "max" else 10.0}
        self.scene = "power_"+effort
        self.environment = "none"
        self.scene_start = self.t
        self.scene_end = self.t+self.spectacle["duration"]
        self.dialogue = []
        self.pair = []
        if effort == "ultra":
            self._populate(CAST)
            for i, a in enumerate(self.actors):
                a.x = a.target = .07 + .86*i/(len(self.actors)-1)
                a.v = 0
        else:
            for i, a in enumerate(self.actors):
                a.target = .18 + .64*i/max(1, len(self.actors)-1)
        for a in self.actors:
            a.bubble = ""
            a.gesture = "clap" if effort == "ultra" else "reach"
        self.say(0, "思考引擎，全力点亮！" if effort == "max" else "全员到齐，为灵感喝彩！", 2.8)
        return self.snapshot()

    def cancel_spectacle(self):
        if self.spectacle is None:
            return
        saved = self._saved_stage
        self.spectacle = None
        self._saved_stage = None
        if saved:
            ids = [a.id for a in saved["actors"]]
            self.departing = [dict(asdict(a), departure=self.t) for a in self.actors if a.id not in ids]
            self.actors = saved["actors"]
            self.scene = saved["scene"]
            self.environment = saved["environment"]
            self.scene_start = self.t-saved["scene_age"]
            self.scene_end = self.t+saved["scene_left"]
            self.next_scene = self.t+max(2, saved["next_scene"])
            self.next_visit = self.t+max(2, saved["next_visit"])
            self.next_roam = self.t+max(.5, saved["next_roam"])
            self.pair = saved["pair"]
            self.dialogue = []
            for a in self.actors:
                a.bubble = ""
                a.gesture = PERSONALITIES[a.id]["gesture"]
            # Task status can change during a celebration; resume the current task.
            if self.phase != saved["phase"]:
                if self.phase == "working":
                    self.scene, self.environment = "work", "office"
                elif self.phase in ("waiting", "blocked"):
                    self.scene, self.environment = "waiting", "none"
                else:
                    self.scene, self.environment = "roam", "none"
                self.scene_start = self.t
            self.generation += 1

    def activity(self, phase=None, model=None, typing=False, effort=None):
        if phase and phase not in ("idle", "working", "waiting", "ready", "blocked"):
            raise ValueError("unknown phase")
        if model is not None:
            self.model = model
        if typing:
            self.typing_until = self.t+1.3
        if effort is not None:
            self.set_effort(effort, baseline=not self._effort_seen)
        if phase and phase != self.phase:
            previous = self.phase
            self.phase = phase
            if self.spectacle:
                return
            self.dialogue = []
            if phase == "working":
                self.scene, self.environment, self.scene_start = "work", "office", self.t
                self.pair = []
                for i, a in enumerate(self.actors):
                    a.target = .14+i*.20
                    a.bubble = ""
                self.say(0, self._line(self.actors[0].id, "work"), 3.2)
            elif phase in ("waiting", "blocked"):
                self.scene, self.environment = "waiting", "none"
                self.pair = []
                for a in self.actors:
                    a.target = a.x
                self.say(0, self._line(self.actors[0].id, "waiting"), 4)
            elif previous == "working" and phase in ("idle", "ready"):
                self.start_scene("celebrate")

    def _line(self, identifier, context):
        lines = PERSONALITIES[identifier]["lines"]
        return self.rng.choice(lines.get(context, lines["chat"]))

    def say(self, index, text, duration=3.0):
        if 0 <= index < len(self.actors):
            # One speaker at a time keeps small terminal stages readable.
            for a in self.actors:
                a.bubble = ""
            a = self.actors[index]
            a.bubble, a.bubble_until = text, self.t+duration

    def start_scene(self, name):
        if name not in SCENES and name != "roam":
            raise ValueError("unknown scene")
        self.cancel_spectacle()
        self.scene, self.scene_start = name, self.t
        self.environment = ENVIRONMENTS.get(name, "none")
        self.pair = []
        self.dialogue = []
        duration = 14 if name in ("home", "office", "dinner", "outing", "stargaze") else 12 if name in ("cookie", "paperball", "parade", "whisper") else 9
        self.scene_end = self.t+duration
        self.next_scene = self.scene_end+self.rng.uniform(4, 8)
        for i, a in enumerate(self.actors):
            a.bubble = ""
            a.gesture = PERSONALITIES[a.id]["gesture"]
            if name in ("chat", "tea", "celebrate", "highfive"):
                a.target = .36+i*.16 if i < 2 else (.12 if i == 2 else .88)
            elif name in ("cookie", "paperball"):
                a.target = .30+i*.19
            elif name == "parade":
                a.target = .14+i*.17
            elif name in ("home", "dinner", "office"):
                a.target = .22+.56*i/max(1, len(self.actors)-1)
            elif name in ("outing", "stargaze", "photo"):
                a.target = .24+.52*i/max(1, len(self.actors)-1)
        partners = self.actors[:2]
        if name == "whisper" and len(self.actors) > 1:
            partners = sorted(self.rng.sample(self.actors, 2), key=lambda a: a.x)
            self.pair = [a.id for a in partners]
            center = max(.2, min(.8, sum(a.x for a in partners)/2))
            for i, a in enumerate(partners):
                a.target = center+(i-.5)*.075
        if name in SCENES and partners:
            delay = 2.8 if name == "whisper" else 0
            for i, a in enumerate(partners):
                self.dialogue.append((self.t+delay+i*3.6, a.id, self._line(a.id, name)))
            if name in ("home", "office", "dinner", "outing", "stargaze") and len(self.actors) > 2:
                a = self.rng.choice(self.actors[2:])
                self.dialogue.append((self.t+8.0, a.id, self._line(a.id, name)))
            if delay == 0:
                self._speak_due()
        return self.snapshot()

    def _speak_due(self):
        while self.dialogue and self.dialogue[0][0] <= self.t:
            _, identifier, text = self.dialogue.pop(0)
            for i, a in enumerate(self.actors):
                if a.id == identifier:
                    self.say(i, text, 3.2)
                    break

    def tick(self, dt):
        if self.paused:
            return
        remaining = max(0, min(float(dt), .5))
        while remaining > 1e-8:
            step = min(remaining, 1/60)
            self._step(step)
            remaining -= step

    def _step(self, dt):
        self.t += dt
        self.departing = [a for a in self.departing if self.t-a["departure"] < 1.2]
        if self.spectacle and self.t-self.spectacle["start"] >= self.spectacle["duration"]:
            self.cancel_spectacle()
        quiet = self.t < self.typing_until
        social = self.phase in ("idle", "ready") and not quiet and self.spectacle is None
        age = self.t-self.scene_start
        if social and self.scene != "roam" and self.t >= self.scene_end:
            self.scene, self.environment, self.pair = "roam", "none", []
            self.dialogue = []
        if social and self.t >= self.next_scene:
            self.start_scene(self.rng.choice(SOCIAL_SCENES))
            age = 0
        if social and not self.reduced_motion:
            self._speak_due()
        if social and self.scene == "roam" and self.t >= self.next_roam:
            self.next_roam = self.t+self.rng.uniform(3, 6)
            a = self.rng.choice(self.actors)
            a.target = self.rng.uniform(.09, .91)
        if social and self.t >= self.next_visit and len(self.pool) > len(self.actors):
            self.next_visit = self.t+55
            incoming = self.pool.pop(0)
            self.pool.append(incoming)
            self._populate(self.pool[:self.density])
            self.say(0, self._line(self.actors[0].id, "entrance"))
        if social and self.scene in ("cookie", "paperball", "parade") and age > 4:
            for i, a in enumerate(self.actors[:2]):
                a.target = .5+.29*math.sin(age*.65+i*1.5)
        for i, a in enumerate(self.actors):
            speed = .14*a.tempo
            desired = max(-speed, min(speed, (a.target-a.x)*1.8))
            if quiet or self.reduced_motion or 0 <= self.t-a.arrival < 1.2:
                desired = 0
            a.v += (desired-a.v)*(1-math.exp(-dt*9))
            a.x = max(.07, min(.93, a.x+a.v*dt))
            a.travel += abs(a.v)*dt
            if quiet or self.reduced_motion:
                a.pose, a.gesture = "idle", "rest"
            elif abs(a.v) > .008:
                a.facing = 1 if a.v > 0 else -1
                a.pose = "walk_right" if a.facing == 1 else "walk_left"
                a.gesture = "walk"
            elif self.spectacle:
                a.pose = "wave"
                a.gesture = "clap" if self.spectacle["kind"] == "ultra" else "reach"
            elif self.scene in ("tea", "home", "stargaze"):
                a.pose = "rest"
                a.gesture = "rest" if self.scene == "home" else "sway"
            elif self.scene in ("office", "work"):
                a.pose, a.gesture = "talk", "type"
            elif self.scene in ("celebrate", "highfive"):
                a.pose, a.gesture = "wave", "clap"
            elif self.scene == "dinner":
                a.pose, a.gesture = "talk", "reach"
            elif self.scene == "outing":
                a.pose, a.gesture = "wave", "bounce"
            elif self.scene == "photo":
                a.pose, a.gesture = "wave", "peek"
            elif self.scene == "paperball" and age % 4 < .6:
                a.pose, a.gesture = "surprise", "bounce"
            elif a.bubble and a.bubble_until > self.t:
                a.pose, a.gesture = "talk", PERSONALITIES[a.id]["gesture"]
            else:
                a.pose, a.gesture = "idle", PERSONALITIES[a.id]["gesture"]
            if social and self.scene == "whisper" and a.id in self.pair and abs(a.x-a.target) < .025 and not self.reduced_motion:
                a.pose = "talk" if int(age*1.4) % 2 == self.pair.index(a.id) else "idle"
                a.gesture = "nod" if a.pose == "talk" else "think"
                a.facing = 1 if a.id == self.pair[0] else -1

    def snapshot(self):
        spectacle = None
        if self.spectacle:
            spectacle = {"kind": self.spectacle["kind"], "age": self.t-self.spectacle["start"],
                         "duration": self.spectacle["duration"]}
        return {"time": round(self.t, 3), "scene": self.scene, "scene_age": self.t-self.scene_start,
                "phase": self.phase, "model": self.model, "effort": self.effort,
                "spectacle": spectacle, "environment": self.environment,
                "quiet": self.t < self.typing_until, "paused": self.paused,
                "reduced_motion": self.reduced_motion, "cast": [asdict(a) for a in self.actors],
                "pool": self.pool[:], "density": self.density, "generation": self.generation,
                "departing": [dict(a) for a in self.departing], "pair": self.pair[:]}
