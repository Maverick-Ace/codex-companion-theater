"""Interrupted scene fades preserve visible weights and respect quiet playback."""
import unittest
from theater.world import World
from theater.render import Renderer
from PIL import ImageChops


def advance(world, seconds):
    remaining = seconds
    while remaining > 1e-8:
        dt = min(1 / 60, remaining)
        world.tick(dt)
        remaining -= dt


def weights(world):
    return {item['name']: item['opacity']
            for item in world.snapshot()['stage_transition']['layers']}


class StageTransitionTests(unittest.TestCase):
    def test_entering_and_leaving_props_fade_without_an_opaque_backdrop(self):
        world = World()
        world.start_scene('home')
        initial = weights(world)
        self.assertLess(initial.get('home', 0), .01)
        advance(world, .3)
        self.assertGreater(weights(world)['home'], .1)
        self.assertLess(weights(world)['home'], .9)
        advance(world, .35)
        self.assertAlmostEqual(weights(world)['home'], 1)
        world.start_scene('roam')
        self.assertAlmostEqual(weights(world)['home'], 1)
        advance(world, .3)
        self.assertGreater(weights(world)['home'], 0)
        self.assertLess(weights(world)['home'], 1)
        advance(world, .35)
        self.assertEqual(weights(world), {})

    def test_same_environment_does_not_restart_a_partial_fade(self):
        world = World()
        world.start_scene('office')
        advance(world, .24)
        before = world.snapshot()['stage_transition']
        world.activity('working')
        after = world.snapshot()['stage_transition']
        self.assertEqual(world.environment, 'office')
        self.assertEqual(before['layers'], after['layers'])
        self.assertAlmostEqual(before['age'], after['age'])

    def test_fast_scene_change_starts_from_the_current_visible_mix(self):
        world = World()
        world.start_scene('home')
        advance(world, .65)
        world.start_scene('office')
        advance(world, .2)
        before = weights(world)
        self.assertGreater(before['home'], 0)
        self.assertGreater(before['office'], 0)
        world.start_scene('dinner')
        after = weights(world)
        for name, opacity in before.items():
            self.assertAlmostEqual(after.get(name, 0), opacity)
        self.assertLess(after.get('dinner', 0), .001)
        advance(world, .65)
        self.assertEqual(weights(world), {'dinner': 1.0})

    def test_repeated_interruption_never_accumulates_extra_opacity(self):
        world = World()
        for name in ['home', 'office', 'dinner', 'outing'] * 4:
            world.start_scene(name)
            advance(world, .075)
            current = weights(world)
            self.assertLessEqual(sum(current.values()), 1.000001)
            self.assertTrue(all(0 <= value <= 1 for value in current.values()))
            self.assertTrue(set(current).issubset({'home', 'office', 'dinner', 'outing'}))

    def test_typing_uses_static_target_and_does_not_restart_the_fade(self):
        world = World()
        world.start_scene('home')
        advance(world, .2)
        world.activity(typing=True)
        self.assertEqual(weights(world), {'home': 1.0})
        advance(world, .7)
        self.assertTrue(world.snapshot()['quiet'])
        advance(world, .7)
        self.assertFalse(world.snapshot()['quiet'])
        self.assertEqual(weights(world), {'home': 1.0})
        world.activity(typing=True)
        world.start_scene('roam')
        self.assertEqual(weights(world), {})

    def test_reduced_motion_and_pause_keep_transition_behavior_predictable(self):
        world = World()
        world.reduced_motion = True
        world.start_scene('outing')
        self.assertEqual(weights(world), {'outing': 1.0})
        world.reduced_motion = False
        advance(world, .2)
        world.paused = True
        before = world.snapshot()['stage_transition']
        world.tick(.5)
        self.assertEqual(world.snapshot()['stage_transition'], before)
        world.paused = False
        advance(world, .5)
        self.assertEqual(weights(world), {'outing': 1.0})

    def test_ultra_clears_then_restores_the_prior_scenery_with_a_new_fade(self):
        world = World()
        world.start_scene('home')
        advance(world, .7)
        world.set_effort('ultra')
        advance(world, .65)
        self.assertEqual(world.environment, 'none')
        self.assertEqual(weights(world), {})
        advance(world, 9.4)
        self.assertIsNone(world.snapshot()['spectacle'])
        self.assertEqual(world.environment, 'home')
        self.assertGreater(weights(world).get('home', 0), 0)
        self.assertLess(weights(world)['home'], 1)
        advance(world, .65)
        self.assertEqual(weights(world), {'home': 1.0})

    def test_renderer_keeps_the_same_visible_props_at_an_interruption(self):
        world = World()
        world.start_scene('home')
        advance(world, .65)
        renderer = Renderer()
        def scenery_frame():
            state = world.snapshot()
            state['cast'] = []
            state['departing'] = []
            return renderer.frame(state, 960, 180)
        before = scenery_frame()
        world.start_scene('office')
        immediate = scenery_frame()
        self.assertIsNone(ImageChops.difference(before, immediate).getbbox())
        advance(world, .3)
        middle = scenery_frame()
        self.assertIsNotNone(ImageChops.difference(before, middle).getbbox())
        advance(world, .35)
        complete = scenery_frame()
        self.assertIsNotNone(ImageChops.difference(middle, complete).getbbox())

    def test_scene_timeout_fades_props_away(self):
        world = World()
        world.start_scene('dinner')
        advance(world, 14.05)
        self.assertEqual(world.environment, 'none')
        self.assertEqual(world.scene, 'roam')
        self.assertGreater(weights(world).get('dinner', 0), .8)
        advance(world, .65)
        self.assertEqual(weights(world), {})


if __name__ == '__main__':
    unittest.main()
