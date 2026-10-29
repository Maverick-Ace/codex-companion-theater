"""Arrival speakers and contacts with real scene objects, rather than global poses."""
import unittest
from theater.world import World, PERSONALITIES
from theater.props import interaction_slots


def advance(world, seconds):
    for _ in range(round(seconds*60)):
        world.tick(1/60)


class EntranceTests(unittest.TestCase):
    def test_only_newly_visible_actor_greets_after_portal_materializes(self):
        w=World(cast=['gpt','claude'],density=2)
        w.set_cast(['gpt','deepseek'])
        advance(w,.65)
        self.assertTrue(all(not a.bubble for a in w.actors))
        advance(w,.2)
        speakers=[a.id for a in w.actors if a.bubble]
        self.assertEqual(speakers,['deepseek'])
        self.assertIn(w.actors[1].bubble,PERSONALITIES['deepseek']['lines']['entrance'])

    def test_all_personalities_have_varied_non_repeating_entrances(self):
        for identifier,p in PERSONALITIES.items():
            self.assertGreaterEqual(len(set(p['lines']['entrance'])),4)
            w=World(cast=[identifier])
            lines=[w._line(identifier,'entrance') for _ in range(20)]
            self.assertTrue(all(a!=b for a,b in zip(lines,lines[1:])))

    def test_initial_same_cast_and_ultra_do_not_queue_entrance_spam(self):
        w=World();self.assertFalse(w.entrances)
        w.set_cast([a.id for a in w.actors]);self.assertFalse(w.entrances)
        w.set_effort('ultra');self.assertFalse(w.entrances)
        advance(w,10.1);self.assertFalse(w.entrances)

    def test_typing_scene_change_and_departure_cancel_old_arrivals(self):
        for trigger in ('typing','scene','departure'):
            w=World(cast=['gpt'],density=1);w.set_cast(['claude'])
            if trigger=='typing':w.activity(typing=True)
            elif trigger=='scene':w.start_scene('dinner')
            else:w.set_cast(['deepseek'])
            advance(w,1)
            self.assertTrue(all(not a.bubble or a.bubble not in PERSONALITIES['claude']['lines']['entrance'] for a in w.actors))

    def test_auto_rotation_greets_incoming_actor_not_retained_leader(self):
        w=World();w.next_visit=.1;w.next_scene=100
        advance(w,1)
        speakers=[a.id for a in w.actors if a.bubble]
        self.assertEqual(speakers,['minimax'])
        self.assertEqual(w.actors[0].id,'deepseek')

    def test_density_increase_and_multiple_arrivals_have_sequential_speakers(self):
        w=World(cast=['gpt','deepseek','claude'],density=1)
        w.set_density(3)
        advance(w,1)
        self.assertEqual([a.id for a in w.actors if a.bubble],['deepseek'])
        advance(w,3)
        self.assertEqual([a.id for a in w.actors if a.bubble],['claude'])


class PropContactTests(unittest.TestCase):
    def test_each_set_reaches_real_anchor_before_acting(self):
        for scene in ('home','office','dinner','outing'):
            w=World(seed=4);w.start_scene(scene)
            for a in w.actors:a.x=.93
            advance(w,.35)
            self.assertTrue(any(a.interaction for a in w.actors))
            self.assertFalse(any(a.interaction and a.interaction['active'] for a in w.actors))
            active_props=set()
            anchors={s['prop']:s for s in interaction_slots(scene,3)}
            for _ in range(600):
                w.tick(1/60)
                for a in w.actors:
                    if a.interaction and a.interaction['active']:
                        contact=a.interaction
                        self.assertAlmostEqual(a.x,anchors[contact['prop']]['x'],delta=.025)
                        self.assertGreaterEqual(contact['progress'],0)
                        self.assertLess(contact['progress'],1)
                        active_props.add(contact['prop'])
            self.assertEqual(active_props,set(anchors))

    def test_work_phase_also_uses_desk_props(self):
        w=World();w.activity('working')
        active=set()
        for _ in range(600):
            w.tick(1/60)
            active.update(a.interaction['prop'] for a in w.actors if a.interaction and a.interaction['active'])
        self.assertTrue({'laptop','plant','notebook'}.issubset(active))

    def test_contact_faces_the_object_not_the_actor_standing_slot(self):
        w=World(cast=['gpt'],density=1);w.start_scene('dinner')
        w.actors[0].x=.85
        for _ in range(700):
            w.tick(1/60)
            a=w.actors[0]
            if a.interaction and a.interaction['active'] and a.interaction['prop']=='hotpot':
                self.assertEqual(a.facing,1)
                break
        else:self.fail('the actor never reached the pot')

    def test_wheelchair_uses_reading_or_tea_instead_of_climbing_sofa(self):
        w=World(cast=['wenxin'],density=1);w.start_scene('home')
        advance(w,3)
        self.assertIsNotNone(w.actors[0].interaction)
        self.assertNotEqual(w.actors[0].interaction['action'],'sit')

    def test_contact_releases_and_quiet_reduced_or_spectacle_clears_it(self):
        for mode in ('quiet','reduced','ultra','scene'):
            w=World();w.start_scene('office');advance(w,3)
            self.assertTrue(any(a.interaction and a.interaction['active'] for a in w.actors))
            if mode=='quiet':w.activity(typing=True)
            elif mode=='reduced':w.reduced_motion=True
            elif mode=='ultra':w.set_effort('ultra')
            else:w.start_scene('home')
            w.tick(1/60)
            self.assertFalse(any(a.interaction and a.interaction['active'] for a in w.actors))

    def test_prop_is_reserved_for_only_one_actor(self):
        w=World(density=5);w.start_scene('office')
        for _ in range(650):
            w.tick(1/60)
            contacts=[a.interaction['prop'] for a in w.actors if a.interaction]
            self.assertEqual(len(contacts),len(set(contacts)))

    def test_ultra_restore_does_not_reuse_stale_contact(self):
        w=World();w.start_scene('dinner');advance(w,3)
        w.set_effort('ultra');advance(w,10.02)
        self.assertEqual(w.environment,'dinner')
        self.assertFalse(any(a.interaction and a.interaction['active'] for a in w.actors))
        advance(w,2)
        self.assertTrue(any(a.interaction and a.interaction['active'] for a in w.actors))
