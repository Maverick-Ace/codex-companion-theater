"""Accepted-submit deduplication, finite choreography and model destinations."""
import math
import json
import tempfile
import unittest
from PIL import ImageChops
from theater.world import World
from theater.render import Renderer
from theater.launch import destination, DURATION, _flight_pose, _orbit_pose, _nozzle, _draw_exhaust
from theater.service import Theater

def advance(world, seconds):
    for _ in range(round(seconds*60)):world.tick(1/60)

class LaunchTests(unittest.TestCase):
    def test_named_destinations_and_stable_custom_fallback(self):
        for model,kind in [('gpt-6.1-sol','sun'),('gpt-6.1-terra','earth'),('gpt-6-luna','moon'),('gpt-6-astra','stars')]:
            self.assertEqual(destination(model)['kind'],kind)
        self.assertEqual(destination('custom-x'),destination('custom-x'))
        self.assertNotEqual(destination('custom-x')['color'],destination('custom-y')['color'])

    def test_busy_events_and_typing_are_not_submissions(self):
        w=World();w.activity('working',model='gpt-6.1-sol');advance(w,.5)
        self.assertIsNone(w.flight)
        w.activity(typing=True);self.assertIsNone(w.flight)

    def test_launch_yields_prop_space_then_fades_work_set_back_in(self):
        w=World();w.activity('working');advance(w,1)
        w.submit('sol');advance(w,.3)
        layers=w.snapshot()['stage_transition']['layers']
        self.assertTrue(any(p['name']=='office' and 0<p['opacity']<1 for p in layers))
        advance(w,DURATION)
        self.assertIsNone(w.flight);self.assertEqual(w.environment,'office')
        w.submit('sol');w.activity(typing=True)
        self.assertIsNone(w.flight);self.assertEqual(w.environment,'office')

    def test_phases_finish_without_changing_cast_or_task_state(self):
        w=World();ids=[a.id for a in w.actors]
        w.activity('working');w.submit('gpt-6.1-sol')
        self.assertEqual(w.snapshot()['flight']['phase'],'build')
        advance(w,1.7);self.assertEqual(w.snapshot()['flight']['phase'],'ignite')
        advance(w,.6);self.assertEqual(w.snapshot()['flight']['phase'],'launch')
        advance(w,1.7);self.assertEqual(w.snapshot()['flight']['phase'],'orbit')
        w.activity('ready') # A fast answer must not truncate the launch ceremony.
        self.assertIsNotNone(w.flight)
        advance(w,4);self.assertIsNone(w.flight)
        self.assertEqual([a.id for a in w.actors],ids)
        self.assertEqual(w.phase,'ready');self.assertEqual(w.scene,'roam')

    def test_input_approval_cast_and_scene_cancel_and_pause_holds_time(self):
        for trigger in ('typing','waiting','cast','scene'):
            w=World();w.submit('sol')
            if trigger=='typing':w.activity(typing=True)
            elif trigger=='waiting':w.activity('waiting')
            elif trigger=='cast':w.set_cast(['claude'])
            else:w.start_scene('home')
            self.assertIsNone(w.flight,trigger)
        w=World();w.submit('terra');w.paused=True;s=w.snapshot();w.tick(.5)
        self.assertEqual(s,w.snapshot())

    def test_service_retries_do_not_replay_and_old_hidden_submits_expire(self):
        with tempfile.TemporaryDirectory() as temp:
            t=Theater(temp,7)
            msg=dict(op='layout',layout_key='test',width_px=640,height_px=160,model='sol',phase='working',
                     submission=dict(id=1,model='gpt-6.1-sol',age_ms=5))
            t.command(msg);start=t.world.flight['start']
            advance(t.world,1);t.command(msg)
            self.assertEqual(t.world.flight['start'],start)
            self.assertEqual(t.world.flight['destination']['kind'],'sun')
            t.command(dict(msg,submission=dict(id=2,model='terra',age_ms=0)))
            self.assertEqual(t.world.flight['destination']['kind'],'earth')
            t.world.flight=None
            t.command(dict(msg,submission=dict(id=3,model='luna',age_ms=4000)))
            self.assertIsNone(t.world.flight)

    def test_each_phase_renders_with_motion_and_reduced_mode_is_static(self):
        r=Renderer();w=World();w.submit('sol');images=[]
        for second in (.8,1.9,3,4.2,5.2):
            advance(w,second-w.t)
            images.append(r.frame(w.snapshot(),1040,156))
        self.assertTrue(all(ImageChops.difference(a,b).getbbox() for a,b in zip(images,images[1:])))
        w=World();w.reduced_motion=True;w.submit('sol');advance(w,5.2)
        a=r.frame(w.snapshot(),1040,156);advance(w,.5);b=r.frame(w.snapshot(),1040,156)
        self.assertIsNone(ImageChops.difference(a,b).getbbox())

    def test_nose_follows_actual_motion_through_takeoff_and_all_orbit_quadrants(self):
        w,h,floor=1040,180,176
        for t in (2.3,2.7,3.2,3.7,3.81,4.2,4.7,5.2,5.7,6.2,6.7,7.2):
            p=_flight_pose(t,w,h,floor);before=_flight_pose(t-.0001,w,h,floor);after=_flight_pose(t+.0001,w,h,floor)
            dx,dy=after['x']-before['x'],after['y']-before['y'];length=math.hypot(dx,dy)
            angle=math.radians(p['angle']);nose=(-math.sin(angle),-math.cos(angle))
            self.assertGreater((nose[0]*dx+nose[1]*dy)/length,.999,t)
            nx,ny,_,_=_nozzle(p)
            self.assertLess((nx-p['x'])*nose[0]+(ny-p['y'])*nose[1],0)
        left=_flight_pose(3.8-.0001,w,h,floor);right=_flight_pose(3.8+.0001,w,h,floor)
        self.assertLess(math.hypot(left['x']-right['x'],left['y']-right['y']),.001)
        self.assertLess(abs(left['angle']-right['angle']),.1)

    def test_curved_exhaust_follows_past_positions_and_clips_at_edges(self):
        from PIL import Image
        path=lambda t:_orbit_pose(t,90,70,50,30,24,rate=3)
        im=Image.new('RGBA',(180,140));_draw_exhaust(im,path(1.2),1.2,path,'#ffbd53')
        self.assertIsNotNone(im.getbbox())
        # Early emitted flame occupies the curved wake, away from the current axis.
        past=path(1.2-.22);x,y,bx,by=_nozzle(past);drift=past['flame']*.8*(.22/.46)
        x,y=round(x+bx*drift),round(y+by*drift)
        self.assertIsNotNone(im.crop((x-3,y-3,x+4,y+4)).getbbox())
        edge=lambda t:_orbit_pose(t,0,0,14,10,12,rate=3)
        small=Image.new('RGBA',(80,48));_draw_exhaust(small,edge(.4),.4,edge,'#ffbd53')
        self.assertIsNone(small.crop((60,0,80,48)).getbbox())

    def test_native_anchor_is_after_accept_and_contains_no_prompt(self):
        import importlib.util
        from pathlib import Path
        spec=importlib.util.spec_from_file_location('launch_migrate',Path(__file__).resolve().parents[1]/'scripts/migrate.py')
        migrate=importlib.util.module_from_spec(spec);spec.loader.exec_module(migrate)
        from test_effort_adapter import EffortAdapterTests
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);tui=EffortAdapterTests().source(root)
            output=migrate.prepare(root)
            source=output[tui/'chatwidget/input_submission.rs']
            self.assertLess(source.index('return (false, None)'),source.index('note_submission'))
            self.assertIn('note_submission(effective_mode.model())',source)
            self.assertNotIn('submitted_message.text',source)
            file=tui/'chatwidget/input_submission.rs';file.write_text('upstream changed')
            before={p:p.read_text() for p in tui.rglob('*.rs')}
            with self.assertRaises(ValueError):migrate.prepare(root)
            self.assertEqual(before,{p:p.read_text() for p in tui.rglob('*.rs')})
