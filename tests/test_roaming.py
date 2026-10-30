import unittest
from theater.world import World
from theater.geometry import stage_metrics,stage_position

class RoamingTests(unittest.TestCase):
    def test_seeded_spawns_are_spread_and_roles_have_no_home_slots(self):
        starts=[]
        for seed in range(12):
            a,b=World(seed),World(seed)
            self.assertEqual([(p.x,p.depth) for p in a.actors],[(p.x,p.depth) for p in b.actors])
            self.assertTrue(all(.07<=p.x<=.93 and 0<=p.depth<=1 for p in a.actors))
            starts.append(a.actors[0].x)
        self.assertGreater(max(starts)-min(starts),.5)
        self.assertGreater(len({round(x,2) for x in starts}),8)

    def test_all_characters_choose_new_horizontal_and_depth_destinations(self):
        w=World(seed=23);w.next_scene=w.next_visit=w.play.next_social=1000
        positions={a.id:set() for a in w.actors};depths={a.id:set() for a in w.actors}
        for _ in range(1800):
            w.life.touch(w);w.tick(1/30)
            for a in w.actors:
                positions[a.id].add(round(a.target,2));depths[a.id].add(round(a.depth_target,2))
                self.assertTrue(.07<=a.x<=.93 and 0<=a.depth<=1)
        self.assertTrue(all(len(s)>6 for s in positions.values()))
        self.assertTrue(all(len(s)>5 for s in depths.values()))
        self.assertGreater(len({round(p['next'],1) for p in w.roaming.plans.values()}),2)

    def test_property_contacts_and_typing_interrupt_depth_walks(self):
        w=World(seed=23);w.activity(typing=True,cursor={'x':.7,'y':1.1});w.tick(.1)
        self.assertTrue(all(a.depth_target==0 for a in w.actors))
        w.activity('working');w.tick(.5)
        self.assertTrue(all(a.depth_target==0 for a in w.actors if a.interaction))

    def test_pointer_and_drawing_share_actual_depth_coordinates(self):
        w=World(seed=9,cast=['gpt'],density=1);w.set_geometry(640,160)
        size,floor=stage_metrics(1,640,160)
        a=w.actors[0];a.depth=a.depth_target=1
        x,y,_=stage_position(w.snapshot()['cast'][0],0,1,640,size,floor)
        w.pointer('down',x/640,(y-size*.4)/160);w.tick(.05)
        self.assertEqual(w.actors[0].reaction['kind'],'click')

    def test_repeating_a_social_scene_does_not_reuse_the_same_formation(self):
        w=World(seed=12);formations=set()
        for _ in range(6):
            w.start_scene('photo');formations.add(tuple(round(a.target,3) for a in w.actors))
        self.assertEqual(len(formations),6)
