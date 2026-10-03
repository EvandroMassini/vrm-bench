import tempfile,unittest
from app.user_capture import collect,decode_status,STATUS
from test_ramtest import Bench
class CaptureTests(unittest.TestCase):
    def test_two_passes_complete_no_write(self):
        class Read(Bench):
            reads=0
            def register_read(self,*args):self.reads+=1;return super().register_read(*args)
        b=Read([])
        with tempfile.TemporaryDirectory() as d:r=collect(b,d)
        self.assertTrue(r['complete']);self.assertTrue(r['stable_user']);self.assertEqual(len(r['values']),88)
        self.assertEqual(b.reads,190);self.assertEqual(b.calls,0);self.assertFalse(r['programming_enabled'])
    def test_state_bits(self):
        v={f'{x:02X}':dict(value=0) for x in STATUS};v['96']['value']=0x20;v['A9']['value']=0xA3
        r=decode_status(v);self.assertEqual(r['loop1_chip_enable_bit'],1);self.assertEqual(r['loop2_chip_enable_bit'],0)
        self.assertEqual(r['loop1_startup_state_code'],10);self.assertEqual(r['loop2_startup_state_code'],3)
        self.assertEqual(r['loop1_config_enable_name'],'Hard shutdown')
    def test_partial_preserved(self):
        class Bad(Bench):
            def register_read(self,a,r):
                if r==0x11:raise RuntimeError('falha')
                return super().register_read(a,r)
        with tempfile.TemporaryDirectory() as d:r=collect(Bad([]),d)
        self.assertFalse(r['complete']);self.assertIn('10',r['passes'][0]);self.assertNotIn('sha256_user_pass2',r)
    def test_changes_detected(self):
        class Changing(Bench):
            seen=0
            def register_read(self,a,r):
                if r==0x10:self.seen+=1
                return dict(value=self.seen if r==0x10 else 0,pec_verified=True)
        with tempfile.TemporaryDirectory() as d:r=collect(Changing([]),d)
        self.assertFalse(r['stable_user']);self.assertEqual(r['changed_registers'],['10'])
    def test_bad_pec(self):
        class Bad(Bench):
            def register_read(self,*_):return dict(value=0,pec_verified=False)
        with tempfile.TemporaryDirectory() as d:r=collect(Bad([]),d)
        self.assertFalse(r['complete']);self.assertFalse(r['programming_enabled'])
