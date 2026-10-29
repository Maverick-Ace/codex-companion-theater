"""Closure signals, staggered pursuit and complete airborne sprite bounds."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from theater.world import World
from theater.render import Renderer, composite_clipped

ROOT=Path(__file__).resolve().parents[1]

class CloseTests(unittest.TestCase):
    def test_engine_exits_if_owner_disappears(self):
        with tempfile.TemporaryDirectory() as temp:
            # A deliberately absent parent models uncatchable launcher death.
            proc=subprocess.Popen([sys.executable,'-m','theater.cli','serve','--runtime',temp],
                cwd=ROOT,env=dict(os.environ,CODEX_THEATER_OWNER_PID='2147483647'),
                stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
            try:
                _,error=proc.communicate(timeout=5)
                self.assertEqual(proc.returncode,0,error.decode())
                self.assertFalse((Path(temp)/'control.sock').exists())
            finally:
                if proc.poll() is None:proc.kill();proc.wait()

    def test_close_signals_remove_engine_and_registry(self):
        for sig in (signal.SIGHUP,signal.SIGTERM):
            with self.subTest(signal=sig), tempfile.TemporaryDirectory() as temp:
                folder=Path(temp); binary=folder/'fake-cli'
                binary.write_text('#!'+sys.executable+'\nimport time\ntime.sleep(60)\n');binary.chmod(0o755)
                manifest=folder/'manifest.json';manifest.write_text(json.dumps({'binary':str(binary)}))
                env=dict(os.environ,HOME=temp,XDG_RUNTIME_DIR=temp,CODEX_THEATER_MANIFEST=str(manifest))
                proc=subprocess.Popen([sys.executable,str(ROOT/'scripts/codex-theater')],env=env,start_new_session=True)
                engine_pid=None
                try:
                    deadline=time.monotonic()+5
                    records=[]
                    while time.monotonic()<deadline:
                        records=list((folder/'.cache/codex-companion-theater/instances').glob('*.json'))
                        if records:break
                        time.sleep(.03)
                    self.assertTrue(records)
                    children=Path(f'/proc/{proc.pid}/task/{proc.pid}/children').read_text().split()
                    for child in children:
                        if b'theater.cli' in Path(f'/proc/{child}/cmdline').read_bytes():engine_pid=int(child)
                    self.assertIsNotNone(engine_pid)
                    self.assertEqual(os.readlink(f'/proc/{engine_pid}/fd/0'),'/dev/null')
                    proc.send_signal(sig)
                    self.assertEqual(proc.wait(timeout=6),128+sig)
                    self.assertFalse(Path(f'/proc/{engine_pid}').exists())
                    self.assertFalse(records[0].exists())
                    self.assertFalse(list(folder.glob('codex-theater-*')))
                finally:
                    if proc.poll() is None:os.killpg(proc.pid,signal.SIGKILL);proc.wait()
                    if engine_pid and Path(f'/proc/{engine_pid}').exists():os.kill(engine_pid,signal.SIGKILL)

class MotionTests(unittest.TestCase):
    def test_plans_persist_and_cursor_jump_is_eased(self):
        world=World(seed=31);world.next_scene=100
        world.activity(typing=True,cursor={'x':.2,'y':1.1})
        for _ in range(90):world.activity(typing=True,cursor={'x':.2,'y':1.1});world.tick(1/60)
        plans={k:dict(v) for k,v in world.attention.approaches.items()}
        before=[a.x for a in world.actors]
        world.activity(typing=True,cursor={'x':.9,'y':1.1});world.tick(1/30)
        self.assertEqual(plans,world.attention.approaches)
        self.assertTrue(all(abs(a.x-x)<.02 for a,x in zip(world.actors,before)))
        self.assertGreater(len({p['delay'] for p in plans.values()}),1)
        self.assertGreater(len({p['pace'] for p in plans.values()}),1)
        self.assertGreater(min(abs(a.target-b.target) for i,a in enumerate(world.actors) for b in world.actors[i+1:]),.08)

    def test_drag_above_stage_preserves_rotated_head_and_feet(self):
        renderer=Renderer();world=World(seed=3,cast=['gpt'],density=1)
        world.set_geometry(960,180);world.next_scene=world.next_roam=100
        world.pointer('move',.5,(178-129*1.05)/180)
        for _ in range(15):world.tick(1/60)
        self.assertEqual(world.snapshot()['pointer']['caught'],'gpt')
        world.pointer('move',.5,-.9)
        for _ in range(6):world.tick(1/60)
        for width,height in ((960,180),(480,80),(1040,156)):
            calls=[]
            def record(canvas,sprite,x,y):
                bounds=sprite.getbbox()
                if bounds:calls.append((x+bounds[0],y+bounds[1],x+bounds[2],y+bounds[3]))
                composite_clipped(canvas,sprite,x,y)
            with patch('theater.render.composite_clipped',side_effect=record):
                renderer.frame(world.snapshot(),width,height)
            self.assertTrue(calls)
            for left,top,right,bottom in calls:
                self.assertGreaterEqual(top,2);self.assertGreaterEqual(left,2)
                self.assertLessEqual(bottom,height-2);self.assertLessEqual(right,width-2)
