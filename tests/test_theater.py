import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from PIL import Image
from theater.world import World, CAST, SCENES
from theater.service import Theater, UnixServer, request
from theater.render import Renderer, ROOT

class BehaviorTests(unittest.TestCase):
    def test_elapsed_time_not_frame_count(self):
        a,b=World(77),World(77)
        for _ in range(100):a.tick(.04)
        for _ in range(200):b.tick(.02)
        for aa,bb in zip(a.actors,b.actors):self.assertAlmostEqual(aa.x,bb.x,delta=.003)

    def test_typing_slows_then_resumes(self):
        w=World();w.next_scene=100;w.actors[0].target=.08
        for _ in range(20):w.tick(.05)
        self.assertGreater(abs(w.actors[0].v),.01)
        for _ in range(30):w.activity(typing=True);w.tick(.05)
        self.assertTrue(w.snapshot()['quiet']);self.assertLess(abs(w.actors[0].v),.0001)
        for _ in range(35):w.tick(.05)
        self.assertFalse(w.snapshot()['quiet'])

    def test_movement_stays_within_stage(self):
        w=World(9)
        for _ in range(3600):
            w.tick(1/30)
            self.assertTrue(all(.069<=a.x<=.931 for a in w.actors))
            # Rotation is intentionally disabled for this movement-only interval.
            w.next_visit=w.t+100

    def test_all_seventeen_can_take_the_stage(self):
        w=World()
        for name in CAST:
            w.set_cast([name]);w.tick(.2)
            self.assertEqual(w.actors[0].id,name)
        with self.assertRaises(ValueError):w.set_cast(['gpt','gpt'])

    def test_work_to_done_celebrates(self):
        w=World();w.activity('working');w.tick(.1)
        self.assertEqual(w.scene,'work')
        w.activity('ready');self.assertEqual(w.scene,'celebrate')

    def test_pause_and_reduced_motion(self):
        w=World();w.paused=True;before=w.snapshot();w.tick(.5)
        self.assertEqual(before,w.snapshot())
        w.paused=False;w.reduced_motion=True
        for _ in range(100):w.tick(.05)
        self.assertTrue(all(a.pose=='idle' for a in w.actors))

class RenderAndProtocolTests(unittest.TestCase):
    def test_every_sprite_and_scene_renders(self):
        r=Renderer();w=World()
        for name in CAST:
            for index in range(16):
                p=ROOT/'assets/cast'/name/'frames'/f'{index:02}.png'
                with Image.open(p) as image:
                    self.assertEqual(image.mode,'RGBA');self.assertIsNotNone(image.getchannel('A').getbbox())
                    self.assertEqual(image.getchannel('A').getextrema()[0],0)
            w.set_cast([name]);w.tick(.1)
            self.assertIsNotNone(r.frame(w.snapshot(),640,160).getbbox())
        for scene in SCENES:
            w.start_scene(scene)
            self.assertEqual(r.frame(w.snapshot()).size,(960,180))

    def test_socket_frame_and_version_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            theater=Theater(temp);sock=Path(temp)/'control.sock'
            server=UnixServer(sock,theater)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                reply=request(sock,{'v':1,'op':'layout','layout_key':'abc','width_px':800,'height_px':154,'phase':'idle'})
                self.assertEqual(reply['layout_key'],'abc')
                self.assertTrue(Path(reply['frame']).is_file())
                bad=request(sock,{'v':99,'op':'status'})
                self.assertFalse(bad['ok'])
                self.assertEqual(sock.stat().st_mode&0o777,0o600)
            finally:server.shutdown();server.server_close();thread.join()

    def test_ring_is_bounded(self):
        with tempfile.TemporaryDirectory() as temp:
            t=Theater(temp)
            for _ in range(70):t.command({'op':'layout','layout_key':'same','width_px':400,'height_px':80})
            self.assertEqual(len(list(Path(temp).glob('frame-*.png'))),64)

    def test_mcp_initialization_and_catalog(self):
        messages=[{'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2024-11-05'}},
                  {'jsonrpc':'2.0','method':'notifications/initialized'},
                  {'jsonrpc':'2.0','id':2,'method':'tools/list'}]
        result=subprocess.run([sys.executable,str(ROOT/'plugin/scripts/mcp_server.py')],
            input=''.join(json.dumps(m)+'\n' for m in messages),text=True,capture_output=True,check=True)
        replies=[json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual(len(replies),2);self.assertEqual(len(replies[1]['result']['tools']),5)

    def test_mcp_can_change_real_local_scene(self):
        with tempfile.TemporaryDirectory() as temp:
            theater=Theater(temp);sock=Path(temp)/'control.sock'
            server=UnixServer(sock,theater)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                message={'jsonrpc':'2.0','id':5,'method':'tools/call','params':{'name':'theater_scene','arguments':{'name':'paperball'}}}
                result=subprocess.run([sys.executable,str(ROOT/'plugin/scripts/mcp_server.py')],input=json.dumps(message)+'\n',text=True,capture_output=True,check=True,env=dict(os.environ,HOME=temp,CODEX_THEATER_SOCKET=str(sock)))
                reply=json.loads(result.stdout)['result']
                self.assertFalse(reply['isError'])
                self.assertEqual(theater.world.scene,'paperball')
            finally:server.shutdown();server.server_close();thread.join()

    def test_unknown_source_does_not_write(self):
        spec=importlib.util.spec_from_file_location('migrate',ROOT/'scripts/migrate.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'codex-rs/tui/src';p.mkdir(parents=True)
            (p/'lib.rs').write_text('unknown upstream')
            with self.assertRaises(ValueError):module.prepare(Path(temp))
            self.assertEqual((p/'lib.rs').read_text(),'unknown upstream')
            self.assertEqual(len(list(p.iterdir())),1)

if __name__=='__main__':unittest.main()
