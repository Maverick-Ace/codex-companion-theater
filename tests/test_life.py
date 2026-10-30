import json
from pathlib import Path
import tempfile
import unittest
from theater.life import Life, CollectionStore, DECORATIONS
from theater.world import World
from theater.render import Renderer
from theater.service import Theater


def advance(w,s):
    for _ in range(round(s*60)):w.tick(1/60)


class LifeTests(unittest.TestCase):
    def test_store_merges_windows_and_ignores_invalid_entries(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'collection.json';one=CollectionStore(path);two=CollectionStore(path)
            self.assertEqual(one.load(),([],None))
            one.save(['star_lamp'],'star_lamp');two.save(['plant'],'plant')
            self.assertEqual(one.load(),(['plant','star_lamp'],'plant'))
            path.write_text(json.dumps({'owned':['plant','unknown'],'selected':'unknown'}))
            self.assertEqual(two.load(),(['plant'],'plant'))
            path.write_text('{bad');self.assertEqual(one.load(),([],None))

    def test_click_collects_once_hover_does_not_and_collection_is_bounded(self):
        w=World();w.set_geometry(640,160)
        for _ in range(8):
            w.life.spawn(w);x,y=w.life.point(w)
            w.pointer('move',x,y);self.assertIsNotNone(w.life.treasure)
            w.pointer('down',x,y);self.assertIsNone(w.life.treasure)
        self.assertEqual(set(w.life.owned),set(DECORATIONS))
        self.assertEqual(len(w.life.owned),5)
        self.assertFalse(any(r['kind']=='click' for r in w.attention.reactions.values()))

    def test_input_approval_reduced_motion_and_pause_win(self):
        for mode in ('typing','waiting','reduced','paused'):
            w=World();w.life.spawn(w);x,y=w.life.point(w)
            if mode=='typing':w.activity(typing=True)
            elif mode=='waiting':w.activity('waiting')
            elif mode=='reduced':w.reduced_motion=True
            else:w.paused=True
            w.pointer('down',x,y);self.assertFalse(w.life.owned,mode)
            self.assertFalse(w.life.sleeping)

    def test_idle_sleeps_and_pointer_or_typing_wakes(self):
        w=World();w.next_scene=w.next_visit=1000;w.play.next_social=1000
        advance(w,61);self.assertTrue(w.life.sleeping)
        self.assertTrue(all(a.pose=='rest' for a in w.actors))
        self.assertIsNone(w.play.active)
        w.pointer('move',.9,.5);self.assertFalse(w.life.sleeping)
        w.life.last_touch=w.t-61;advance(w,.1);self.assertTrue(w.life.sleeping)
        w.activity(typing=True);self.assertFalse(w.life.sleeping)

    def test_automatic_duets_do_not_prevent_sleep_and_work_keeps_cast_awake(self):
        w=World();w.next_scene=w.next_visit=1000
        advance(w,61);self.assertTrue(w.life.sleeping)
        w.activity('working');advance(w,61)
        self.assertFalse(w.life.sleeping)
        w.activity('ready');w.work_event('complete');advance(w,.1)
        self.assertFalse(w.life.sleeping)
        self.assertEqual(w.play.active['kind'],'finish')

    def test_day_night_and_each_decoration_render_at_small_geometry(self):
        w=World();r=Renderer()
        for hour in (10,19,23):
            w.life.clock(hour)
            self.assertEqual(w.snapshot()['life']['period'],{10:'day',19:'dusk',23:'night'}[hour])
            for key in DECORATIONS:
                w.life.owned=list(DECORATIONS);w.life.select(key)
                self.assertIsNotNone(r.frame(w.snapshot(),400,80).getbbox())
        for value in (-1,24,True,'night'):
            with self.assertRaises(ValueError):w.life.clock(value)

    def test_collection_survives_service_restart(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'data/collection.json';t=Theater(Path(root)/'one',seed=8,collection_path=path)
            t.command({'op':'treasure'});p=t.world.life.point(t.world)
            reply=t.command({'op':'pointer','kind':'down','x':p[0],'y':p[1]})
            self.assertEqual(len(reply['state']['life']['owned']),1)
            self.assertEqual(CollectionStore(path).load()[0],reply['state']['life']['owned'])
            restored=Theater(Path(root)/'two',collection_path=path)
            self.assertEqual(restored.world.life.owned,t.world.life.owned)
            restored.command({'op':'clock','hour':23})
            self.assertEqual(restored.world.life.hour,23)
