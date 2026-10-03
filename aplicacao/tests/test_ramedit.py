import unittest,tempfile
from unittest.mock import patch
from app.ramedit import change
from test_ramtest import Bench
class Editable(Bench):
    version=11
    value=0xFF
    def register_read(self,*_):return dict(value=self.value,raw_hex=f'{self.value:02X}',pec_verified=True)
    def request(self,command):
        self.calls+=1;self.value=int(command.split()[-1],16)
        return f'OK RAMSET 01 00 01 {self.value:02X} 22'
class EditTests(unittest.TestCase):
    def test_apply_restore(self):
        b=Editable([])
        with tempfile.TemporaryDirectory() as d:
            r=change(b,d);self.assertTrue(r['complete']);self.assertEqual(b.value,0xEF)
            r=change(b,d,True);self.assertTrue(r['complete']);self.assertEqual(b.value,0xFF)
        self.assertEqual(b.calls,2)
    def test_no_repeat(self):
        b=Editable([]);b.value=0xEF
        with tempfile.TemporaryDirectory() as d:r=change(b,d)
        self.assertTrue(r['no_change_needed']);self.assertEqual(b.calls,0)
    def test_disk_failure_blocks_apply(self):
        b=Editable([])
        with patch('app.ramedit.save_backup',side_effect=OSError('full')):r=change(b,'unused')
        self.assertFalse(r['command_sent']);self.assertEqual(b.calls,0)
    def test_disk_failure_does_not_block_restore(self):
        b=Editable([]);b.value=0xEF
        with patch('app.ramedit.save_backup',side_effect=OSError('full')):r=change(b,'unused',True)
        self.assertTrue(r['complete']);self.assertEqual(b.value,0xFF);self.assertEqual(r['save_error'],'full')
    def test_unknown_value(self):
        b=Editable([]);b.value=0xEE
        with tempfile.TemporaryDirectory() as d:r=change(b,d)
        self.assertFalse(r['command_sent']);self.assertEqual(b.calls,0)
    def test_lost_response_not_success(self):
        class Lost(Editable):
            def request(self,_):raise TimeoutError('lost')
        with tempfile.TemporaryDirectory() as d:r=change(Lost([]),d)
        self.assertFalse(r['complete']);self.assertIsNone(r['write_attempted'])
    def test_firmware_rollback_not_success(self):
        class Rollback(Editable):
            def request(self,_):return 'OK RAMSET 00 01 01 FF 22'
        with tempfile.TemporaryDirectory() as d:r=change(Rollback([]),d)
        self.assertFalse(r['complete']);self.assertTrue(r['rollback_attempted']);self.assertEqual(r['final_hex'],'FF')
