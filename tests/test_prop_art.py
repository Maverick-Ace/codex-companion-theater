"""Miniature set geometry and responses to actual prop contact."""
import unittest
from PIL import Image, ImageChops
from theater.props import prop_layout
from theater.stagecraft import environment, _set_art


def frame(name, prop=None, action=None, active=False, still=False):
    state={'cast':[] if prop is None else [{'interaction':{
        'prop':prop,'action':action,'active':active,'progress':.4}}]}
    image=Image.new('RGBA',(960,180))
    environment(image,name,178,120,2,still=still,state=state)
    return image


def changed(a,b):
    return ImageChops.difference(a.convert('RGB'),b.convert('RGB')).getbbox()


class PropArtTests(unittest.TestCase):
    def test_every_set_retains_full_stage_geometry_and_transparent_margin(self):
        for name in ('home','office','dinner','outing'):
            for width,height,size in ((160,48,38),(960,180,120),(1500,220,160),(2560,480,345)):
                with self.subTest(name=name,width=width,size=size):
                    art=_set_art(name,width,height,height-2,size,())
                    self.assertEqual(art.size,(width,height))
                    self.assertEqual(art.mode,'RGBA')
                    self.assertIsNotNone(art.getbbox())
                    self.assertEqual(art.getpixel((width-1,0))[3],0)
            # Plants/tea tables/trees on the right must not collapse into the left.
            self.assertIsNotNone(frame(name).crop((540,20,960,180)).getbbox())

    def test_book_and_cup_leave_their_supports_only_during_actual_contact(self):
        for prop,action in (('book','read'),('teacup','sip')):
            with self.subTest(prop=prop):
                baseline=frame('home')
                waiting=frame('home',prop,action,False)
                held=frame('home',prop,action,True)
                self.assertIsNone(changed(baseline,waiting))
                self.assertIsNotNone(changed(baseline,held))
                x=prop_layout('home',960,178,120)[prop]['x']
                delta=changed(baseline,held)
                self.assertLess(abs((delta[0]+delta[2])/2-x),28)

    def test_props_respond_after_contact_and_quiet_suppresses_responses(self):
        for name,prop,action in (('office','laptop','type'),('office','plant','water'),
                                 ('dinner','hotpot','stir'),('outing','basket','unpack'),
                                 ('outing','tent','inspect'),('home','sofa','sit')):
            with self.subTest(name=name,action=action):
                self.assertIsNone(changed(frame(name),frame(name,prop,action,False)))
                self.assertIsNotNone(changed(frame(name),frame(name,prop,action,True)))
                self.assertIsNone(changed(frame(name,still=True),frame(name,prop,action,True,still=True)))


if __name__=='__main__':unittest.main()
