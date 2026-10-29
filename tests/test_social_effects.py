import unittest
from theater.world import World
from theater.render import Renderer

class SocialEffectsTests(unittest.TestCase):
 def test_switch_preserves_departing_actor_for_portal(self):
  w=World(cast=['gpt'],density=1);w.set_cast(['claude'])
  s=w.snapshot();self.assertEqual(s['departing'][0]['id'],'gpt')
  self.assertEqual(s['cast'][0]['arrival'],w.t)
  for _ in range(40):w.tick(.05)
  self.assertFalse(w.snapshot()['departing'])
 def test_two_characters_can_cross(self):
  w=World(cast=['gpt','claude'],density=2);w.next_scene=w.next_roam=100
  w.actors[0].target=.85;w.actors[1].target=.15
  for _ in range(140):w.tick(.05)
  self.assertGreater(w.actors[0].x,w.actors[1].x)
 def test_whisper_chooses_two_and_brings_them_together(self):
  w=World(seed=14);w.start_scene('whisper')
  self.assertEqual(len(w.snapshot()['pair']),2)
  for _ in range(130):w.tick(.05)
  pair=[a for a in w.actors if a.id in w.snapshot()['pair']]
  self.assertLess(abs(pair[0].x-pair[1].x),.10)
  self.assertTrue(any(a.pose=='talk' for a in pair))
 def test_quiet_stops_whisper(self):
  w=World();w.start_scene('whisper');w.activity(typing=True);w.tick(.1)
  self.assertTrue(w.snapshot()['quiet'])
  self.assertTrue(all(a.pose=='idle' for a in w.actors))

class CropTests(unittest.TestCase):
 def test_cell_edge_fragment_is_removed_without_wrapping(self):
  import importlib.util,tempfile
  from pathlib import Path
  from PIL import Image,ImageDraw
  from theater.render import ROOT
  spec=importlib.util.spec_from_file_location('sprites',ROOT/'scripts/prepare_sprites.py')
  module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
  with tempfile.TemporaryDirectory() as temp:
   source=Path(temp)/'cell.png';out=Path(temp)/'clean.png'
   im=Image.new('RGBA',(100,100));d=ImageDraw.Draw(im)
   d.rectangle((30,20,70,90),fill='white');d.rectangle((80,0,90,5),fill='red');im.save(source)
   module.clean_cell(source,(0,0,100,100),out)
   clean=Image.open(out).convert('RGBA')
   self.assertEqual(clean.getpixel((85,2))[3],0)
   self.assertEqual(clean.getpixel((50,50))[3],255)
 def test_stage_edge_clips_without_pixels_on_opposite_side(self):
  from PIL import Image
  from theater.render import composite_clipped
  canvas=Image.new('RGBA',(100,50));sprite=Image.new('RGBA',(30,30),'red')
  composite_clipped(canvas,sprite,-20,5)
  self.assertIsNone(canvas.crop((10,0,100,50)).getbbox())
