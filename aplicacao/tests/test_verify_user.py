import tempfile,unittest
from app.verify_user import compare_live,crc_flags,differences,load_image,mask_of
from test_ramtest import Bench

class ImageBench(Bench):
    image=None
    def register_read(self,address,register):
        if register==0xA5:return dict(value=0,pec_verified=True)
        if self.image and register in self.image['values']:return dict(value=self.image['values'][register],pec_verified=True)
        return dict(value=0,pec_verified=True)

class VerifyTests(unittest.TestCase):
    def setUp(self):
        from app.controller_store import select
        select('IR3567B')
        ImageBench.image=load_image()
    def test_known_masks(self):
        self.assertEqual(mask_of(0x10),0xFF)
        self.assertEqual(mask_of(0x4F),0)
        self.assertEqual(mask_of(0x50),0)
        self.assertEqual(mask_of(0x70),0xFB)
        self.assertEqual(len(load_image()['values']),88)
    def test_mask_hides_4f_and_keeps_10(self):
        image=load_image()['values']
        live=dict(image)
        live[0x4F]^=0xFF
        live[0x10]^=0x01
        rows=differences(image,live)
        self.assertEqual([row['register_hex'] for row in rows],['10'])
    def test_crc_low_bits_only(self):
        self.assertFalse(crc_flags(0)['active_error'])
        self.assertFalse(crc_flags(0xF8)['active_error'])
        self.assertTrue(crc_flags(0x04)['active_error'])
        self.assertEqual((crc_flags(0x07)['bit2'],crc_flags(0x07)['bit1'],crc_flags(0x07)['bit0']),(1,1,1))
    def test_live_match_is_not_programming(self):
        with tempfile.TemporaryDirectory() as d:
            result=compare_live(ImageBench([]),d)
        self.assertTrue(result['complete']);self.assertTrue(result['user_masked_equal'])
        self.assertFalse(result['programming_enabled']);self.assertFalse(result['reload_sent'])
        self.assertEqual(result['mismatch_count'],0)
