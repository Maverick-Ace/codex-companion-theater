import hashlib
import unittest
from PIL import Image
from theater.brands import ASSETS, BRANDS, brand_badge, draw_brand_portal
from theater.world import CAST


class BrandPortalTests(unittest.TestCase):
    def test_all_characters_have_attributed_complete_local_assets(self):
        self.assertEqual(set(BRANDS), set(CAST))
        for actor_id, info in BRANDS.items():
            with self.subTest(actor=actor_id):
                path = ASSETS / info['file']
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), info['sha256'])
                with Image.open(path) as image:
                    self.assertGreater(min(image.size), 15)
                    self.assertIsNotNone(image.convert('RGBA').getchannel('A').getbbox())
                self.assertTrue(info['page'].startswith('https://'))
                if actor_id == 'jev':
                    self.assertEqual(info['kind'], 'local_monogram')
                    self.assertIsNone(info['source'])
                else:
                    self.assertEqual(info['kind'], 'official_site_mark')
                    self.assertTrue(info['source'].startswith('https://'))

    def test_badges_keep_neutral_clear_space_and_are_cached(self):
        for actor_id in BRANDS:
            badge = brand_badge(actor_id, 48)
            self.assertEqual(badge.size, (48, 48))
            self.assertIs(badge, brand_badge(actor_id, 48))
            self.assertEqual(badge.getpixel((0, 0))[3], 0)
            self.assertGreater(badge.getchannel('A').getextrema()[1], 240)

    def test_portal_endpoints_are_empty_and_frames_have_elapsed_time_motion(self):
        for actor_id in BRANDS:
            before = Image.new('RGBA', (320, 180))
            for progress in (0, 1, -.1, 1.2):
                draw_brand_portal(before, actor_id, 160, 175, 110, progress)
                self.assertIsNone(before.getbbox())
            first, second = before.copy(), before.copy()
            draw_brand_portal(first, actor_id, 160, 175, 110, .25)
            draw_brand_portal(second, actor_id, 160, 175, 110, .65)
            self.assertIsNotNone(first.getbbox())
            self.assertNotEqual(first.tobytes(), second.tobytes())

    def test_left_edge_portal_cannot_wrap_onto_right_edge(self):
        image = Image.new('RGBA', (320, 180))
        draw_brand_portal(image, 'deepseek', -8, 178, 110, .4)
        self.assertIsNotNone(image.getbbox())
        self.assertIsNone(image.crop((160, 0, 320, 180)).getbbox())
