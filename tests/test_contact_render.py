"""Held objects follow pickup/return arcs and meet shared scene contact points."""
import unittest
from PIL import Image
from theater.hand_props import draw_held
from theater.props import prop_layout
from theater.world import World


class ContactRenderTests(unittest.TestCase):
    def state_actor(self, action, prop, progress=.5, environment='office'):
        state=World().snapshot();state['environment']=environment
        actor=dict(state['cast'][0], interaction={'action':action,'prop':prop,'active':True,'progress':progress})
        return state,actor

    def test_water_and_spoon_reach_the_prop_contact_anchor(self):
        for action,prop,env in [('water','plant','office'),('stir','hotpot','dinner')]:
            state,actor=self.state_actor(action,prop,environment=env)
            canvas=Image.new('RGBA',(960,180))
            draw_held(canvas,state,actor,340,178,120)
            anchor=prop_layout(env,960,178,120)[prop]
            x,y=round(anchor['x']),round(anchor['y'])
            self.assertIsNotNone(canvas.crop((x-8,y-8,x+8,y+8)).getbbox())
            self.assertIsNotNone(canvas.crop((330,110,380,155)).getbbox())

    def test_cup_picks_up_then_returns_to_the_table(self):
        locations=[]
        for progress in (0,.5,1):
            state,actor=self.state_actor('sip','teacup',progress,'home')
            canvas=Image.new('RGBA',(960,180))
            draw_held(canvas,state,actor,300,178,120)
            box=canvas.getbbox();locations.append((box[0]+box[2])/2)
        self.assertAlmostEqual(locations[0],locations[2],delta=2)
        self.assertGreater(locations[0]-locations[1],150)

    def test_input_and_gentle_modes_have_no_held_action_layer(self):
        for flag in ('quiet','reduced_motion'):
            state,actor=self.state_actor('water','plant');state[flag]=True
            canvas=Image.new('RGBA',(960,180))
            draw_held(canvas,state,actor,700,178,120)
            self.assertIsNone(canvas.getbbox())
