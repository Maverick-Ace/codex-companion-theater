"""Continuous rig, stage layers and dense ensemble visibility regressions."""
import unittest
from PIL import Image, ImageChops
from theater.motion import PuppetRig, joint_motion, PROFILES
from theater.world import World, CAST
from theater.render import Renderer
from theater.stagecraft import environment


class ContinuousMotionTests(unittest.TestCase):
    def test_virtual_joints_deform_without_detached_crop_edges(self):
        renderer=Renderer()
        actor=World().snapshot()['cast'][0]
        a=renderer.sprite(actor,.3,128)
        b=renderer.sprite(actor,.6,128)
        self.assertIsNotNone(ImageChops.difference(a,b).getbbox())
        # Padding keeps the puppet mesh away from the image edges.
        self.assertIsNone(a.crop((0,0,a.width,3)).getbbox())
        self.assertIsNone(a.crop((0,0,3,a.height)).getbbox())
        self.assertEqual(len(joint_motion(actor,.3)),8)
        self.assertEqual(set(PROFILES),set(CAST))

    def test_quiet_rig_has_no_breathing_or_joint_motion(self):
        renderer=Renderer()
        actor=World().snapshot()['cast'][0]
        a=renderer.sprite(actor,.3,128,still=True)
        b=renderer.sprite(actor,.6,128,still=True)
        self.assertIsNone(ImageChops.difference(a,b).getbbox())
        wheelchair=dict(actor,id='wenxin')
        self.assertEqual(len(joint_motion(wheelchair,.3)),5)

    def test_scenery_is_transparent_and_each_set_is_distinct(self):
        hashes=[]
        for name in ('home','office','dinner','outing'):
            for size in (38,77,120,140,170,230,345):
                # Thin laptop/desk pieces must survive rounded pixel geometry.
                environment(Image.new('RGBA',(960,180)),name,178,size,2)
            im=Image.new('RGBA',(960,180))
            environment(im,name,178,120,2)
            self.assertIsNotNone(im.getbbox())
            self.assertEqual(im.getpixel((0,0))[3],0)
            hashes.append(hash(im.tobytes()))
        self.assertEqual(len(set(hashes)),4)

    def test_all_seventeen_render_in_two_rows(self):
        world=World();world.set_effort('ultra')
        for _ in range(45):world.tick(1/30)
        state=world.snapshot()
        self.assertEqual(len(state['cast']),17)
        renderer=Renderer()
        self.assertEqual(renderer.frame(state,960,180).size,(960,180))
        quiet=dict(state,quiet=True)
        # Suppressing fireworks still leaves every character in the ensemble.
        im=renderer.frame(quiet,960,180)
        self.assertIsNotNone(im.crop((0,30,480,100)).getbbox())
        self.assertIsNotNone(im.crop((480,80,960,180)).getbbox())
