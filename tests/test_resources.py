"""Real frame publication and bounded renderer storage under static/resize workloads."""
from pathlib import Path
import tempfile
import io
from PIL import Image
import unittest
from unittest.mock import patch
from theater.service import Theater
from theater.render import Renderer
from theater.world import World

class ResourceTests(unittest.TestCase):
    def test_paused_layout_reuses_the_encoded_frame_and_wakes_for_edits(self):
        with tempfile.TemporaryDirectory() as temp:
            clock=[100.]
            with patch('theater.service.time.monotonic',side_effect=lambda:clock[0]):
                t=Theater(temp,seed=9);t.command({'op':'pause'})
                msg={'op':'layout','layout_key':'a','width_px':640,'height_px':160}
                first=t.command(msg);path=Path(first['frame']);mtime=path.stat().st_mtime_ns
                for _ in range(12):
                    clock[0]+=.1
                    self.assertEqual(t.command(msg)['frame_id'],first['frame_id'])
                self.assertEqual(path.stat().st_mtime_ns,mtime)
                self.assertEqual(len(list(Path(temp).glob('frame-*.png'))),1)
                t.command({'op':'cast','ids':['grok']});clock[0]+=.1
                self.assertNotEqual(t.command(msg)['frame_id'],first['frame_id'])

    def test_lossless_png_contains_the_exact_rendered_rgba_pixels(self):
        with tempfile.TemporaryDirectory() as temp:
            t=Theater(temp,seed=9)
            reply=t.command({'op':'layout','layout_key':'a','width_px':640,'height_px':160})
            packet=t.frames.entries[(640,160,False)]
            with Image.open(io.BytesIO(Path(reply['frame']).read_bytes())) as decoded:
                self.assertEqual(decoded.size,(640,160))
                self.assertEqual(decoded.convert('RGBA').tobytes(),packet.pixels)

    def test_many_window_sizes_do_not_accumulate_unbounded_artwork_or_meshes(self):
        r=Renderer();w=World(seed=9)
        for height in range(70,170):
            self.assertIsNotNone(r.frame(w.snapshot(),640,height).getbbox())
        self.assertLessEqual(len(r.cache),128)
        self.assertLessEqual(sum(im.width*im.height*4 for im in r.cache.values()),12*1024*1024)
        self.assertLessEqual(len(r.rig.grids),48)
