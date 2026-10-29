"""Real contact, evasion, shake release, and caret-bound choreography."""
import math
import unittest
from PIL import ImageChops
from theater.geometry import stage_metrics, stage_position
from theater.render import Renderer
from theater.world import World


def advance(world, seconds):
    for _ in range(round(seconds * 60)):
        world.tick(1 / 60)


def single(seed=3, actor='gpt'):
    world = World(seed=seed, cast=[actor], density=1)
    world.set_geometry(960, 180)
    world.next_scene = world.next_roam = 100
    return world


def overhead(world):
    size, floor = stage_metrics(len(world.actors), 960, 180)
    return .5, (floor - size * 1.05) / 180


class PointerContactTests(unittest.TestCase):
    def catch(self, world):
        x, y = overhead(world)
        world.pointer('move', x, y)
        advance(world, .25)
        self.assertEqual(world.snapshot()['pointer']['caught'], world.actors[0].id)
        return x, y

    def test_body_hover_and_personal_click_have_distinct_visible_states(self):
        world = single()
        world.pointer('move', .5, .6)
        advance(world, .05)
        self.assertEqual(world.actors[0].reaction['kind'], 'hover')
        self.assertEqual(world.snapshot()['pointer']['hover'], 'gpt')
        world.pointer('down', .5, .6)
        advance(world, .05)
        self.assertEqual(world.actors[0].reaction['kind'], 'click')
        self.assertEqual(world.actors[0].reaction['style'], 'wave')
        other = single(actor='claude')
        other.pointer('down', .5, .6)
        advance(other, .05)
        self.assertEqual(other.actors[0].reaction['style'], 'shy')

    def test_jump_requires_overhead_proximity_and_can_be_evaded(self):
        world = single()
        x, y = overhead(world)
        world.pointer('move', x, y)
        self.assertEqual(world.attention.reactions['gpt']['kind'], 'jump')
        world.pointer('move', .9, y)
        advance(world, .7)
        self.assertIsNone(world.snapshot()['pointer']['caught'])
        self.assertIsNone(world.actors[0].reaction)

    def test_real_catch_follows_then_shake_lands_without_wrapping(self):
        world = single()
        _, y = self.catch(world)
        before = world.actors[0].x
        world.pointer('move', .58, y)
        advance(world, .08)
        self.assertGreater(world.actors[0].x, before)
        for x in (.46, .57, .45, .58):
            world.pointer('move', x, y)
            advance(world, .05)
        self.assertIsNone(world.snapshot()['pointer']['caught'])
        self.assertEqual(world.actors[0].reaction['kind'], 'land')
        advance(world, .6)
        self.assertIsNone(world.actors[0].reaction)
        self.assertTrue(.07 <= world.actors[0].x <= .93)

    def test_small_pointer_jitter_does_not_release_a_catch(self):
        world = single()
        _, y = self.catch(world)
        for x in (.501, .499, .502, .498, .501):
            world.pointer('move', x, y)
            advance(world, .04)
        self.assertEqual(world.snapshot()['pointer']['caught'], 'gpt')

    def test_maximum_hold_timeout_lands_even_with_stationary_pointer_reports(self):
        world = single()
        x, y = self.catch(world)
        for _ in range(16):
            world.pointer('move', x, y)
            advance(world, .5)
        self.assertIsNone(world.snapshot()['pointer']['caught'])
        self.assertEqual(world.actors[0].reaction['kind'], 'land')
        self.assertGreater(world.actors[0].reaction['lift'], 0)

    def test_paused_modal_leave_releases_attachment_before_resume(self):
        world = single()
        self.catch(world)
        world.paused = True
        world.pointer('leave')
        self.assertIsNone(world.snapshot()['pointer']['caught'])
        self.assertIsNone(world.snapshot()['pointer']['position'])
        self.assertIsNone(world.actors[0].reaction)
        world.paused = False
        advance(world, .1)
        self.assertNotEqual((world.actors[0].reaction or {}).get('kind'), 'caught')

    def test_leave_stale_timeout_typing_and_cast_release(self):
        for trigger in ('leave', 'stale', 'typing', 'cast'):
            world = single()
            self.catch(world)
            if trigger == 'leave': world.pointer('leave')
            elif trigger == 'stale': advance(world, 4.2)
            elif trigger == 'typing': world.activity(typing=True, cursor={'x': .2, 'y': 1.1})
            else: world.set_cast(['claude'])
            advance(world, .05)
            self.assertIsNone(world.snapshot()['pointer']['caught'], trigger)

    def test_paused_and_reduced_motion_do_not_jump_or_capture(self):
        world = single()
        world.paused = True
        before = world.snapshot()
        world.pointer('move', *overhead(world))
        advance(world, .3)
        self.assertEqual(before, world.snapshot())
        world.paused = False
        world.reduced_motion = True
        world.pointer('move', *overhead(world))
        advance(world, .4)
        self.assertFalse(any(r['kind'] in ('jump', 'caught') for r in world.attention.reactions.values()))

    def test_bad_pointer_numbers_and_events_are_rejected(self):
        world = single()
        for kind, x, y in (('move', math.nan, .5), ('move', .5, math.inf), ('teleport', .5, .5), ('move', 4, .5)):
            with self.assertRaises(ValueError): world.pointer(kind, x, y)

    def test_seated_character_reaches_without_lifting_wheelchair(self):
        world = single(actor='wenxin')
        world.pointer('move', *overhead(world))
        advance(world, .2)
        self.assertEqual(world.actors[0].reaction['style'], 'reach')
        self.assertEqual(world.actors[0].reaction['lift'], 0)
        self.assertIsNone(world.snapshot()['pointer']['caught'])


class CaretWatchingTests(unittest.TestCase):
    def test_typing_runs_to_real_caret_and_uses_different_observing_poses(self):
        world = World(seed=6)
        world.set_geometry(960, 180)
        for actor in world.actors: actor.x = actor.target = .1
        world.activity(typing=True, cursor={'x': .75, 'y': 1.1})
        advance(world, .5)
        self.assertTrue(all(a.x > .3 for a in world.actors))
        self.assertTrue(all(a.gesture == 'run' for a in world.actors))
        glancers = set()
        for _ in range(24):
            world.activity(typing=True, cursor={'x': .75, 'y': 1.1})
            advance(world, .1)
            glancers.update(a.id for a in world.actors if a.attention and a.attention['look_up'])
        self.assertTrue(all(a.attention for a in world.actors))
        self.assertGreaterEqual(len({a.attention['style'] for a in world.actors}), 3)
        self.assertTrue(glancers)
        self.assertLess(len(glancers), len(world.actors))
        self.assertTrue(all(not a.bubble and a.interaction is None for a in world.actors))
        self.assertGreaterEqual(len({round(a.target, 3) for a in world.actors}), 4)
        advance(world, 2.2)
        self.assertTrue(all(a.attention is None for a in world.actors))

    def test_edge_caret_gathers_without_stacking_or_leaving_stage(self):
        for x in (-.5, 1.5):
            world = World()
            world.activity(typing=True, cursor={'x': x, 'y': 1.1})
            advance(world, .05)
            self.assertTrue(all(.07 <= a.target <= .93 for a in world.actors))
            self.assertEqual(len({round(a.target, 3) for a in world.actors}), len(world.actors))

    def test_multiline_caret_below_stage_still_gathers_at_its_column(self):
        world = World()
        world.activity(typing=True, cursor={'x': .6, 'y': 8})
        advance(world, .05)
        self.assertTrue(all(a.attention and a.attention['y'] == 8 for a in world.actors))

    def test_wide_terminal_caret_left_of_stage_is_preserved_but_actors_stay_inside(self):
        world = World()
        world.activity(typing=True, cursor={'x': -8, 'y': 1.1})
        advance(world, .05)
        self.assertTrue(all(a.attention and a.attention['x'] == -8 for a in world.actors))
        self.assertTrue(all(.07 <= a.target <= .93 for a in world.actors))

    def test_observing_faces_actual_scaled_center_on_a_small_stage(self):
        world = single()
        world.set_geometry(400, 80)
        size, floor = stage_metrics(1, 400, 80)
        world.actors[0].x = .15
        center, _, _ = stage_position({'x': .15}, 0, 1, 400, size, floor)
        world.activity(typing=True, cursor={'x': (center + 2) / 400, 'y': 1.1})
        advance(world, .01)
        self.assertEqual(world.attention.gaze_direction(world, world.actors[0]), 1)

    def test_watching_state_and_reaction_render_differ_from_static_idle(self):
        renderer = Renderer()
        world = single()
        world.activity(typing=True, cursor={'x': .5, 'y': 1.1})
        advance(world, .3)
        watching = renderer.frame(world.snapshot(), 960, 180)
        state = world.snapshot()
        for a in state['cast']:
            a['attention'] = None
        idle = renderer.frame(state, 960, 180)
        self.assertIsNotNone(ImageChops.difference(watching, idle).getbbox())
        caught = single()
        caught.pointer('move', *overhead(caught))
        advance(caught, .25)
        im = renderer.frame(caught.snapshot(), 960, 180)
        self.assertEqual(im.size, (960, 180))
        self.assertIsNone(im.crop((0, 0, 150, 180)).getbbox())

    def test_caught_whisper_partner_keeps_hanging_gesture_and_render_lift(self):
        world = World(seed=3, cast=['gpt', 'claude'], density=2)
        world.set_geometry(960, 180)
        world.start_scene('whisper')
        world.next_scene = 100
        for a in world.actors:
            a.x = a.target = .5
        actor = world.actors[0]
        world.attention.point = {'x': .5, 'y': .2}
        world.attention.last_move = world.t
        world.attention.reactions[actor.id] = {'kind': 'caught', 'start': world.t, 'style': 'catch'}
        advance(world, .05)
        self.assertEqual(actor.gesture, 'hang')
        renderer = Renderer()
        state = world.snapshot()
        # Hold the partner's drawing steady so only the caught origin is tested.
        for item in state['cast']:
            item['bubble'] = ''
            if item['id'] != actor.id:
                item['reaction'] = {'kind': 'hover', 'style': 'curious', 'progress': 0, 'lift': 0, 'tilt': 0}
        lifted = renderer.frame(state, 960, 180)
        grounded_state = dict(state, scene='roam')
        grounded_state['cast'] = [dict(a, reaction=None, pose='idle') if a['id'] == actor.id else a for a in state['cast']]
        grounded = renderer.frame(grounded_state, 960, 180)
        self.assertIsNotNone(ImageChops.difference(lifted, grounded).getbbox())
        # Whisper choreography must not reset the grabbed actor's drawing origin.
        no_whisper = renderer.frame(dict(state, scene='roam'), 960, 180)
        center = int(actor.x * (960 - 129) + 129 / 2)
        self.assertIsNone(ImageChops.difference(lifted, no_whisper).crop((center - 70, 60, center + 70, 150)).getbbox())

    def test_geometry_matches_rendered_center_and_labeled_floor(self):
        world = single()
        world.set_geometry(960, 180, labels=True)
        a, x, floor, size = world.attention._layout(world)[0]
        expected_size, expected_floor = stage_metrics(1, 960, 180, True)
        self.assertEqual((size, floor), (expected_size, expected_floor))
        self.assertEqual((x, floor, size), stage_position({'x': a.x}, 0, 1, 960, size, floor))


if __name__ == '__main__': unittest.main()
