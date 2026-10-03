import unittest,tempfile
from app.mtp_status import decode,inspect,remaining
from test_ramtest import Bench
class MtpTests(unittest.TestCase):
    def test_unused(self):self.assertEqual([x['remaining_indicated'] for x in decode(0x3F,0x0F)],[3,9,3])
    def test_exhausted(self):self.assertEqual([x['remaining_indicated'] for x in decode(0x12,0x08)],[0,0,0])
    def test_reserved(self):self.assertIsNone(remaining(10,9,15));self.assertIsNone(remaining(4,3,7))
    def test_bit_positions(self):
        r=decode(0xC9,0xA2);self.assertEqual([x['pointer'] for x in r],[1,2,1])
    def test_reads_only_two_registers(self):
        class Read(Bench):
            def register_read(self,a,r):
                self.regs=getattr(self,'regs',[])+[r]
                return dict(value=255,pec_verified=True)
        b=Read([])
        with tempfile.TemporaryDirectory() as d:r=inspect(b,d)
        self.assertEqual(b.regs,[0xA6,0xA7]);self.assertEqual(b.calls,0)
        self.assertTrue(r['complete']);self.assertFalse(r['programming_enabled'])
    def test_failed_pec_partial(self):
        class Bad(Bench):
            def register_read(self,*_):return dict(value=255,pec_verified=False)
        with tempfile.TemporaryDirectory() as d:r=inspect(Bad([]),d)
        self.assertFalse(r['complete']);self.assertFalse(r['programming_enabled'])
