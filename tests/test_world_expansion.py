import unittest
from theater.world import World, CAST, PERSONALITIES


def advance(world, seconds):
    for _ in range(round(seconds*60)):
        world.tick(1/60)


class WorldExpansionTests(unittest.TestCase):
    def test_initial_layout_effort_is_baseline_and_identical_frames_do_not_retrigger(self):
        w = World()
        w.activity(effort='max')
        self.assertIsNone(w.snapshot()['spectacle'])
        w.activity(effort='high')
        w.activity(effort='max')
        advance(w, 1)
        age = w.snapshot()['spectacle']['age']
        w.activity(effort='max')
        self.assertAlmostEqual(w.snapshot()['spectacle']['age'], age)

    def test_max_preserves_selected_four_and_ultra_restores_stage(self):
        w = World(cast=['qwen', 'grok', 'kimi', 'seed'])
        w.start_scene('dinner')
        originals = [(a.id, a.x, a.target) for a in w.actors]
        pool = w.pool[:]
        w.set_effort('max')
        self.assertEqual([a.id for a in w.actors], pool)
        w.set_effort('ultra')
        self.assertEqual({a.id for a in w.actors}, set(CAST))
        self.assertEqual(w.pool, pool)
        self.assertEqual(w.density, 4)
        advance(w, 10.02)
        self.assertIsNone(w.snapshot()['spectacle'])
        self.assertEqual([a.id for a in w.actors], pool)
        self.assertEqual(w.scene, 'dinner')
        self.assertEqual(w.environment, 'dinner')
        for a, (_, x, target) in zip(w.actors, originals):
            self.assertAlmostEqual(a.x, x, delta=.01)
            self.assertEqual(a.target, target)

    def test_user_controls_cancel_spectacle_and_keep_latest_choices(self):
        for command in ('cast', 'density', 'scene'):
            w = World()
            w.set_effort('ultra')
            if command == 'cast':
                w.set_cast(['grok', 'kimi'])
                self.assertEqual([a.id for a in w.actors], ['grok', 'kimi'])
            elif command == 'density':
                w.set_density(2)
                self.assertEqual(len(w.actors), 2)
            else:
                w.start_scene('home')
                self.assertEqual(w.scene, 'home')
            self.assertIsNone(w.snapshot()['spectacle'])
            self.assertLessEqual(len(w.actors), 4)

    def test_baseline_different_session_cancels_old_show_without_starting_one(self):
        w = World()
        w.set_effort('ultra')
        w.set_effort('high', baseline=True)
        self.assertIsNone(w.snapshot()['spectacle'])
        self.assertEqual(len(w.actors), 4)
        self.assertEqual(w.effort, 'high')

    def test_repeated_baseline_same_value_does_not_cancel_show(self):
        w = World()
        w.set_effort('ultra')
        advance(w, 1)
        w.set_effort('ultra', baseline=True)
        self.assertIsNotNone(w.snapshot()['spectacle'])
        self.assertGreater(w.snapshot()['spectacle']['age'], .9)

    def test_spectacle_clears_shortcut_quiet_then_respects_new_typing(self):
        w = World()
        w.activity(typing=True)
        self.assertTrue(w.snapshot()['quiet'])
        w.set_effort('max')
        self.assertFalse(w.snapshot()['quiet'])
        w.activity(typing=True)
        advance(w, .5)
        self.assertTrue(all(a.pose == 'idle' and a.gesture == 'rest' for a in w.actors))
        advance(w, 8)
        self.assertIsNone(w.snapshot()['spectacle'])

    def test_task_status_during_spectacle_is_preserved_on_restore(self):
        w = World()
        w.set_effort('ultra')
        w.activity('working')
        advance(w, 10.02)
        self.assertEqual(w.phase, 'working')
        self.assertEqual(w.scene, 'work')
        self.assertEqual(w.environment, 'office')
        self.assertEqual(len(w.actors), 4)

    def test_all_characters_have_unique_authored_personality_lines(self):
        self.assertEqual(set(PERSONALITIES), set(CAST))
        for context in ('chat', 'work', 'whisper', 'home', 'office', 'dinner', 'outing', 'stargaze'):
            lines = [PERSONALITIES[k]['lines'][context][0] for k in CAST]
            self.assertEqual(len(set(lines)), 17, context)
            self.assertTrue(all(len(line) <= 20 for line in lines), context)
        self.assertIsNone(PERSONALITIES['jev']['source'])
        self.assertTrue(all('temperament' in a and 'tempo' in a for a in World().snapshot()['cast']))

    def test_whisper_actual_speakers_are_the_selected_pair(self):
        w = World(seed=14)
        w.start_scene('whisper')
        spoken = set()
        for _ in range(700):
            w.tick(1/60)
            spoken.update(a.id for a in w.actors if a.bubble and a.bubble_until > w.t)
        self.assertEqual(spoken, set(w.pair))

    def test_ultra_delays_cast_rotation_until_after_restoring_regular_cast(self):
        w = World()
        ids = [a.id for a in w.actors]
        w.next_visit = w.t+.1
        w.set_effort('ultra')
        advance(w, 10.1)
        self.assertEqual([a.id for a in w.actors], ids)
        self.assertGreater(w.next_visit, w.t)


if __name__ == '__main__':
    unittest.main()
