"""Elapsed-time stage choreography, local dialogue and model-inspired personalities.

Only display metadata enters this module. Personality is fiction, not a model
capability claim, and all dialogue is authored locally rather than sent to an API.
"""
from dataclasses import dataclass, asdict
import math
import random
import json
from pathlib import Path
from .props import interaction_slots, POSITIONS
from .scenery import SetTransition
from .attention import Attention
from .workshop import Workshop
from .launch import destination, snapshot as flight_snapshot, DURATION as FLIGHT_DURATION

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
    interaction: dict | None = None
    reaction: dict | None = None
    attention: dict | None = None
    job: dict | None = None

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
        self.flight = None
        self._saved_stage = None
        self.typing_until = 0.0
        self.paused = False
        self.reduced_motion = False
        self.scene = "roam"
        self.environment = "none"
        self.set_transition = SetTransition()
        self.scene_start = 0.0
        self.scene_end = 0.0
        self.next_scene = 5.0
        self.next_roam = 1.0
        self.next_visit = 55.0
        self.generation = 0
        self.dialogue = []
        self.entrances = []
        self.entrance_speaker = None
        self._line_last = {}
        self._interaction_plans = {}
        self._interaction_round = 0
        self._next_interaction = 0.0
        self.workshop = Workshop()
        self.attention = Attention()
        self._populate(self.pool[:self.density])

    def set_geometry(self, width, height, labels=False):
        if not (80 <= int(width) <= 2560 and 48 <= int(height) <= 480):
            raise ValueError('invalid stage geometry')
        self.attention.geometry(width, height, labels)

    def pointer(self, kind, x=0.0, y=0.0, button=0):
        if kind not in ('move', 'down', 'up', 'leave'):
            raise ValueError('unknown pointer event')
        x, y = float(x), float(y)
        if not math.isfinite(x) or not math.isfinite(y) or not (-2 <= x <= 3 and -2 <= y <= 3):
            raise ValueError('invalid pointer coordinates')
        self.attention.pointer(self, kind, x, y, button)
        return self.snapshot()

    def _set_environment(self, name):
        if name != self.environment:
            self._clear_interactions()
        self.set_transition.change(name, self.t)
        self.environment = name

    def _clear_entrances(self):
        self.entrances = []
        if self.entrance_speaker:
            identifier, text = self.entrance_speaker
            for a in self.actors:
                if a.id == identifier and a.bubble == text:
                    a.bubble = ""
        self.entrance_speaker = None

    def _clear_interactions(self):
        self._interaction_plans = {}
        self._next_interaction = self.t+.25
        for a in self.actors:
            a.interaction = None

    def _arrange_interactions(self):
        # A single actor can eventually try all three props; each prop has one user.
        slots = interaction_slots(self.environment, 3)
        if not slots or not self.actors:
            return
        offset = self._interaction_round % len(slots)
        slots = slots[offset:]+slots[:offset]
        offset = self._interaction_round % len(self.actors)
        actors = self.actors[offset:]+self.actors[:offset]
        self._interaction_round += 1
        for i,a in enumerate(actors[:len(slots)]):
            if a.id == 'wenxin' and slots[i]['action'] == 'sit':
                # Keep the wheelchair on the ground; let her read or sip instead.
                j = next(j for j,slot in enumerate(slots) if slot['action'] != 'sit')
                slots[i],slots[j] = slots[j],slots[i]
        for a, slot in zip(actors, slots):
            self._interaction_plans[a.id] = dict(slot, started=None, duration=self.rng.uniform(3.0, 4.3))
            a.target = slot['x']
            a.interaction = {"prop":slot['prop'], "action":slot['action'],
                             "active":False, "progress":0.0}

    def _step_interactions(self):
        if (self.t < self.typing_until or self.reduced_motion or self.spectacle or self.flight
                or any(a.reaction or a.attention for a in self.actors)
                or self.phase in ('waiting','blocked')):
            self._clear_interactions()
            return
        if not self._interaction_plans and self.t >= self._next_interaction:
            self._arrange_interactions()
        for a in self.actors:
            plan = self._interaction_plans.get(a.id)
            if plan is None:
                continue
            arrived = abs(a.x-plan['x']) < .025 and abs(a.v) < .006 and self.t-a.arrival >= 1.2
            if not arrived:
                a.interaction = {"prop":plan['prop'], "action":plan['action'],
                                 "active":False, "progress":0.0}
                continue
            if plan['started'] is None:
                plan['started'] = self.t
            progress = (self.t-plan['started'])/plan['duration']
            if progress >= 1:
                a.interaction = None
                del self._interaction_plans[a.id]
                self._next_interaction = self.t+1.0
            else:
                a.interaction = {"prop":plan['prop'], "action":plan['action'],
                                 "active":True, "progress":progress}

    def _speak_entrances(self):
        while self.entrances and self.entrances[0][0] <= self.t:
            due, identifier, text = self.entrances.pop(0)
            if self.t-due > 4:
                continue
            for i,a in enumerate(self.actors):
                if a.id == identifier:
                    self.say(i,text,2.8)
                    self.entrance_speaker = (identifier,text)
                    return

    def _new_actor(self, identifier, x, arrival):
        p = PERSONALITIES[identifier]
        return Actor(identifier, x, x, arrival=arrival, gesture=p["gesture"],
                     temperament=p["temperament"], tempo=p["tempo"], accent=p["accent"])

    def _populate(self, ids):
        self.cancel_flight()
        self.attention.reset(self)
        old = {a.id: a for a in self.actors}
        self._clear_entrances()
        self._clear_interactions()
        self.departing = [d for d in self.departing if d["id"] not in ids]
        self.departing.extend(dict(asdict(a), departure=self.t) for a in self.actors if a.id not in ids)
        n = len(ids)
        self.actors = [old[k] if k in old else self._new_actor(k, (i+1)/(n+1), self.t if old else -10.0)
                       for i, k in enumerate(ids)]
        self.pair = []
        self.dialogue = []
        self.generation += 1
        if old and not self.spectacle:
            new_ids = [k for k in ids if k not in old]
            for i, identifier in enumerate(new_ids):
                self.entrances.append((self.t+.75+i*3.1, identifier, self._line(identifier,'entrance')))
            if new_ids:
                self.next_scene = max(self.next_scene,self.t+.75+len(new_ids)*3.1)

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
        if previous != effort:self.cancel_flight()
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
        self._set_environment("none")
        self._clear_entrances()
        self._clear_interactions()
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
            self._set_environment(saved["environment"])
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
                a.interaction = None
            self._clear_interactions()
            # Task status can change during a celebration; resume the current task.
            if self.phase != saved["phase"]:
                if self.phase == "working":
                    self.scene = "work"
                    self._set_environment("office")
                elif self.phase in ("waiting", "blocked"):
                    self.scene = "waiting"
                    self._set_environment("none")
                else:
                    self.scene = "roam"
                    self._set_environment("none")
                self.scene_start = self.t
            self.generation += 1

    def cancel_flight(self):
        if self.flight is None:return
        self.flight = None
        self.scene, self.scene_start = ('work' if self.phase=='working' else 'roam'), self.t
        self._set_environment('office' if self.phase=='working' else 'none')
        self.next_scene = max(self.next_scene,self.t+3)

    def submit(self, model=None):
        """Accepted user message metadata only, independent of redraw/work events."""
        self.cancel_spectacle()
        if model is not None:self.model = str(model)[:160]
        self.attention.reset(self)
        self._clear_interactions()
        self._clear_entrances()
        self.dialogue = []
        self.typing_until = self.t
        for a in self.actors:a.bubble = ''
        self.scene, self.scene_start = 'work', self.t
        self._set_environment('none')
        self.flight = {'start':self.t, 'model':self.model, 'destination':destination(self.model)}
        self.workshop.submit(self)
        return self.snapshot()

    def activity(self, phase=None, model=None, typing=False, effort=None, cursor=None):
        if phase and phase not in ("idle", "working", "waiting", "ready", "blocked"):
            raise ValueError("unknown phase")
        if model is not None:
            self.model = model
        if typing:
            self.cancel_flight()
            if cursor is not None:
                if not isinstance(cursor, dict) or set(cursor) != {'x', 'y'}:
                    raise ValueError('cursor must contain x and y only')
                cursor = {k:float(cursor[k]) for k in ('x', 'y')}
                if any(not math.isfinite(value) or not -32 <= value <= 32 for value in cursor.values()):
                    raise ValueError('invalid cursor coordinates')
            self.typing_until = self.t+1.3
            self._clear_entrances()
            self._clear_interactions()
            self.attention.typing(self, cursor)
        if effort is not None:
            self.set_effort(effort, baseline=not self._effort_seen)
        if phase and phase != self.phase:
            previous = self.phase
            self.phase = phase
            if previous=='working' and phase in ('idle','ready'):self.workshop.event(self,'complete')
            if self.spectacle:
                return
            if self.flight:
                if phase not in ('waiting','blocked'):return
                self.cancel_flight()
            self.dialogue = []
            self._clear_entrances()
            self._clear_interactions()
            if phase == "working":
                self.scene, self.scene_start = "work", self.t
                self._set_environment("office")
                self.pair = []
                for i, a in enumerate(self.actors):
                    a.target = .14+i*.20
                    a.bubble = ""
                self.say(0, self._line(self.actors[0].id, "work"), 3.2)
            elif phase in ("waiting", "blocked"):
                self.scene = "waiting"
                self._set_environment("none")
                self.pair = []
                for a in self.actors:
                    a.target = a.x
                self.say(0, self._line(self.actors[0].id, "waiting"), 4)
            elif previous == "working" and phase in ("idle", "ready"):
                self.start_scene("celebrate")

    def work_event(self, kind):
        self.workshop.event(self,kind)
        return self.snapshot()

    def _line(self, identifier, context):
        lines = PERSONALITIES[identifier]["lines"]
        choices = lines.get(context, lines["chat"])
        previous = self._line_last.get((identifier,context))
        available = [line for line in choices if line != previous] or choices
        line = self.rng.choice(available)
        self._line_last[identifier,context] = line
        return line

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
        self.cancel_flight()
        self.scene, self.scene_start = name, self.t
        self._set_environment(ENVIRONMENTS.get(name, "none"))
        self._clear_entrances()
        self._clear_interactions()
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
        if self.flight and self.t-self.flight['start'] >= FLIGHT_DURATION:
            self.cancel_flight()
        self.departing = [a for a in self.departing if self.t-a["departure"] < 1.2]
        if self.spectacle and self.t-self.spectacle["start"] >= self.spectacle["duration"]:
            self.cancel_spectacle()
        quiet = self.t < self.typing_until
        social = self.phase in ("idle", "ready") and not quiet and self.spectacle is None and self.flight is None
        age = self.t-self.scene_start
        if social and self.scene != "roam" and self.t >= self.scene_end:
            self.scene, self.pair = "roam", []
            self._set_environment("none")
            self.dialogue = []
        if social and self.t >= self.next_scene:
            self.start_scene(self.rng.choice(SOCIAL_SCENES))
            age = 0
        if not quiet and not self.spectacle and not self.flight:
            self._speak_entrances()
        if social and not self.reduced_motion and not self.entrances:
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
        if social and self.scene in ("cookie", "paperball", "parade") and age > 4:
            for i, a in enumerate(self.actors[:2]):
                a.target = .5+.29*math.sin(age*.65+i*1.5)
        self.attention.step(self, dt)
        self.workshop.step(self)
        self._step_interactions()
        for i, a in enumerate(self.actors):
            launching = self.flight is not None
            if launching:
                a.target = .23 + i*.095 if i<3 else .72+(i-3)*.12
            observing = a.attention is not None
            reacting = a.reaction is not None
            airborne = reacting and a.reaction['kind'] in ('jump', 'caught', 'land')
            ramp = 1.0
            if observing:
                ramp = max(0, min(1, (a.attention['age']-a.attention['delay'])/.5))
                ramp = ramp*ramp*(3-2*ramp)
            speed = (.43*a.attention['pace']*ramp if observing else .3 if launching else .14)*a.tempo
            desired = max(-speed, min(speed, (a.target-a.x)*(4 if observing else 1.8)))
            if (quiet and not observing) or self.reduced_motion or airborne or 0 <= self.t-a.arrival < 1.2:
                desired = 0
            a.v += (desired-a.v)*(1-math.exp(-dt*(7 if observing else 9)))
            a.x = max(.07, min(.93, a.x+a.v*dt))
            a.travel += abs(a.v)*dt
            if self.reduced_motion:
                a.pose, a.gesture = "idle", "rest"
            elif airborne:
                a.pose, a.gesture = 'wave', 'hang' if a.reaction['kind'] == 'caught' else 'catch'
            elif abs(a.v) > .008:
                a.facing = 1 if a.v > 0 else -1
                a.pose = "walk_right" if a.facing == 1 else "walk_left"
                a.gesture = "run" if observing else "walk"
            elif observing:
                a.facing = self.attention.gaze_direction(self, a)
                a.pose = 'rest' if a.attention['style'] == 'crouch' else 'idle'
                a.gesture = 'look_up' if a.attention['look_up'] else 'observe_' + a.attention['style']
            elif a.job:
                a.pose='rest' if a.job['kind']=='read' else 'idle'
                a.gesture={'read':'read','search':'peek','command':'type','edit':'write','tool':'type'}.get(a.job['kind'],'think')
            elif launching:
                age = self.t-self.flight['start']
                a.pose = 'idle' if age<1.6 else 'wave'
                a.gesture = ('type' if i%2 else 'write') if age<1.6 else 'reach' if age<3.8 else 'clap'
                a.facing = 1 if a.x<.51 else -1
            elif quiet:
                a.pose, a.gesture = 'idle', 'rest'
            elif reacting:
                a.pose = 'wave' if a.reaction['kind'] == 'click' else 'idle'
                a.gesture = a.reaction['style']
            elif a.interaction and a.interaction['active']:
                action = a.interaction['action']
                a.pose = 'rest' if action in ('sit','read') else 'talk'
                a.gesture = {'sit':'rest','inspect':'peek'}.get(action,action)
                plan = self._interaction_plans.get(a.id)
                if plan:
                    object_x = POSITIONS[self.environment][plan['prop']]
                    if abs(object_x-a.x) > .005:
                        a.facing = 1 if object_x > a.x else -1
            elif self.spectacle:
                a.pose = "wave"
                a.gesture = "clap" if self.spectacle["kind"] == "ultra" else "reach"
            elif self.scene in ("tea", "home", "stargaze"):
                a.pose = "rest"
                a.gesture = "rest" if self.scene == "home" else "sway"
            elif self.scene in ("office", "work"):
                a.pose, a.gesture = "idle", "think"
            elif self.scene in ("celebrate", "highfive"):
                a.pose, a.gesture = "wave", "clap"
            elif self.scene == "dinner":
                a.pose, a.gesture = "idle", "sway"
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
            if social and self.scene == "whisper" and a.id in self.pair and abs(a.x-a.target) < .025 and not self.reduced_motion and not reacting and not observing:
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
                "stage_transition": self.set_transition.snapshot(self.t, self.reduced_motion or self.t < self.typing_until),
                "quiet": self.t < self.typing_until, "paused": self.paused,
                "reduced_motion": self.reduced_motion, "cast": [asdict(a) for a in self.actors],
                "pool": self.pool[:], "density": self.density, "generation": self.generation,
                "departing": [dict(a) for a in self.departing], "pair": self.pair[:],
                "pointer": self.attention.snapshot(),
                "flight": flight_snapshot(self.flight,self.t,self.reduced_motion),
                "station": self.workshop.snapshot(self), "work_kind":self.workshop.kind}
