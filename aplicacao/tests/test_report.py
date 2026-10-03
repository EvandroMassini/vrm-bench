import unittest
from app.report import analyze,collect,REGISTERS
from app.core import Entry
from test_ramtest import Bench
import tempfile
class ReportTests(unittest.TestCase):
    def test_msb_and_masks(self):
        rows=analyze({'26':{'value':0xEF}},[Entry(0x26,0xFF,0x0F)])
        a=next(r for r in rows if r['field']=='LOOP_1_VID_OFFSET');b=next(r for r in rows if r['field']=='LOOP_2_VID_OFFSET')
        self.assertEqual(a['value'],14);self.assertEqual(a['comparison'],'Sem verificação')
        self.assertEqual(b['value'],15);self.assertEqual(b['comparison'],'Confere')
    def test_missing_not_zero(self):
        rows=analyze({});self.assertTrue(all(r['value'] is None for r in rows))
    def test_one_pass_no_write(self):
        b=Bench([])
        with tempfile.TemporaryDirectory() as d:r=collect(b,d)
        self.assertTrue(r['complete']);self.assertEqual(len(r['values']),len(REGISTERS));self.assertEqual(b.calls,0)
    def test_partial_preserved(self):
        class Failed(Bench):
            def register_read(self,a,r):
                if r==0x14:raise RuntimeError('falha')
                return super().register_read(a,r)
        with tempfile.TemporaryDirectory() as d:r=collect(Failed([]),d)
        self.assertFalse(r['complete']);self.assertEqual(list(r['values']),['0D']);self.assertEqual(r['error'],'falha')
