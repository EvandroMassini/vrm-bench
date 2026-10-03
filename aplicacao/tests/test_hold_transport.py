import unittest
from app.transport import Pico
class TimingTests(unittest.TestCase):
    def test_long_wait_scoped(self):
        class Serial:
            timeout=1
            def write(self,_):pass
            def read_until(self,*_):
                self.observed=self.timeout
                return b'OK RAMTEST 01 01 EF 01 01 FF 22\n'
        p=Pico.__new__(Pico);p.serial=Serial();p.request('RAMHOLD 08 26 FF EF 10000 RESTORE')
        self.assertEqual(p.serial.observed,15);self.assertEqual(p.serial.timeout,1)
    def test_enable_hold_uses_same_window(self):
        class Serial:
            timeout=1
            def write(self,_):pass
            def read_until(self,*_):
                self.observed=self.timeout
                return b'OK ENSOFT 01 01 01 48 01 48 01 30 01 41 01 01 01 88 01 88 22\n'
        p=Pico.__new__(Pico);p.serial=Serial();p.request('ENHOLD 08 88 89 88 48 10000 RESTORE')
        self.assertEqual(p.serial.observed,15);self.assertEqual(p.serial.timeout,1)
    def test_regular_wait_unchanged(self):
        class Serial:
            timeout=1
            def write(self,_):pass
            def read_until(self,*_):
                self.observed=self.timeout
                return b'OK\x20HELLO\n'
        p=Pico.__new__(Pico);p.serial=Serial();p.request('HELLO')
        self.assertEqual(p.serial.observed,1)
