import unittest
from theater.world import World
from theater.render import Renderer

def advance(w,s):
    for _ in range(round(s*60)):w.tick(1/60)

class PlayTests(unittest.TestCase):
    def test_personality_duo_is_finite_and_uses_real_cast(self):
        w=World();self.assertTrue(w.play.start(w,'duo'));advance(w,1)
        event=w.snapshot()['play'];self.assertEqual(set(event['actors']),{'gpt','deepseek'})
        self.assertTrue(any(a.bubble for a in w.actors))
        advance(w,6);self.assertIsNone(w.play.active)

    def test_every_finish_variant_renders(self):
        r=Renderer();w=World()
        for theme in ('stamp','photo','confetti','highfive'):
            w.play.start(w,'finish');w.play.active['theme']=theme;advance(w,.5)
            self.assertIsNotNone(r.frame(w.snapshot(),640,160).getbbox())

    def test_input_approval_and_cast_interrupt_play(self):
        for kind in ('typing','waiting','cast'):
            w=World();w.play.start(w,'duo')
            if kind=='typing':w.activity(typing=True)
            elif kind=='waiting':w.activity('waiting')
            else:w.set_cast(['gpt'])
            advance(w,.05);self.assertIsNone(w.play.active,kind)

    def test_mouse_game_yields_to_a_real_catch_and_leave(self):
        w=World();w.attention.point={'x':.7,'y':.2};w.attention.last_move=w.t
        self.assertTrue(w.play.start(w,'tease'));advance(w,.5)
        self.assertTrue(any(a.play for a in w.actors))
        w.pointer('leave');advance(w,.1);self.assertIsNone(w.play.active)

    def test_all_pranks_render_and_wheelchair_keeps_ground(self):
        w=World(cast=['wenxin','gpt']);r=Renderer()
        for theme in ('book','paperball','chair'):
            w.play.start(w,'prank')
            self.assertNotEqual(w.play.active['theme'],'chair')
            w.play.active['theme']=theme;advance(w,1)
            r.frame(w.snapshot(),640,160)
            self.assertEqual(w.actors[0].play['bob'],0)

    def test_failed_activity_does_not_queue_success_party(self):
        w=World();w.work_event('complete');w.work_event('failed')
        advance(w,.1);self.assertFalse(w.play.finish_pending);self.assertIsNone(w.play.active)
