import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from PIL import Image
from theater.world import World
from theater.service import Theater
from theater.celestial import icon,ROOT

def advance(w,s):
    for _ in range(round(s*60)):w.tick(1/60)

class WorkshopTests(unittest.TestCase):
    def test_sources_are_official_and_bundled(self):
        for name,data in json.loads((ROOT/'sources.json').read_text())['images'].items():
            self.assertEqual(hashlib.sha256((ROOT/data['file']).read_bytes()).hexdigest(),data['sha256'])
            self.assertTrue(data['source'].startswith('https://learn.chatgpt.com/'))
            image=icon(name,40);self.assertEqual(image.size,(80,80));self.assertEqual(image.getpixel((0,0))[3],0)

    def test_return_waits_for_launch_then_delivers_once(self):
        w=World();w.activity('working');w.submit('sol');w.work_event('complete')
        self.assertFalse(w.snapshot()['station']['returning'])
        advance(w,8);self.assertTrue(w.snapshot()['station']['returning'])
        advance(w,6.2);self.assertIsNone(w.snapshot()['station'])
        w.activity('idle');advance(w,1);self.assertIsNone(w.snapshot()['station'])

    def test_roles_follow_real_kind_and_yield_to_typing(self):
        w=World();w.activity('working');w.work_event('read');advance(w,.2)
        self.assertTrue(all(a.job and a.job['kind']=='read' for a in w.actors))
        self.assertEqual(len({a.job['role'] for a in w.actors}),3)
        w.activity(typing=True,cursor={'x':.5,'y':1.1});advance(w,.1)
        self.assertTrue(all(a.job is None for a in w.actors))

    def test_failed_or_interrupted_turn_has_no_success_delivery(self):
        for kind in ('failed','interrupted'):
            w=World();w.submit('sol');w.work_event(kind);advance(w,9)
            self.assertIsNone(w.snapshot()['station'])

    def test_activity_retry_is_deduplicated_without_command_content(self):
        with tempfile.TemporaryDirectory() as temp:
            t=Theater(temp)
            msg=dict(op='layout',layout_key='a',width_px=400,height_px=80,phase='working',
                     activity={'id':1,'kind':'read'})
            t.command(msg);started=t.world.workshop.changed
            advance(t.world,.3);t.command(msg)
            self.assertEqual(started,t.world.workshop.changed)
            self.assertNotIn('command',json.dumps(t.world.snapshot()))
