import unittest
from threading import Event
from app.diagnostics import diagnose,addresses_from_text
from app.transport import Pico,Simulated,TargetRejected,crc8,decode_mfr
from test_transport import FakeSerial

class DiagnosticTests(unittest.TestCase):
    def test_addresses(self):
        self.assertEqual(addresses_from_text('08 70, 0x70'),[8,112])
        for text in ('','0C','00','78','E0','70-77'):
            with self.subTest(text=text), self.assertRaises(ValueError):addresses_from_text(text)
    def test_nack_keeps_usb(self):
        p=Pico.__new__(Pico)
        p.serial=FakeSerial(b'ERR PMBUS_COMMAND\n')
        p.version=4
        with self.assertRaises(TargetRejected):p.pm_read(0x70,0x99)
        self.assertFalse(p.serial.closed)
        self.assertEqual(p.serial.sent,[b'PM 70 99 00 00\n'])
    def test_fatal_closes_usb(self):
        p=Pico.__new__(Pico)
        p.serial=FakeSerial(b'ERR BUS_CONFLICT\n')
        p.version=4
        with self.assertRaises(RuntimeError):p.pm_read(0x70,0x99)
        self.assertTrue(p.serial.closed)
    def test_continue_after_nack(self):
        r=diagnose(Simulated([]),[0x50,0x30],[0x99],100,False,False,Event(),lambda _:None)
        self.assertTrue(r['complete'])
        self.assertEqual([x['status'] for x in r['results']],['rejected','response'])
    def test_cancel_preserves_partial(self):
        cancel=Event()
        r=diagnose(Simulated([]),[0x30,0x50],[0x99],50,False,False,cancel,lambda _:cancel.set())
        self.assertTrue(r['cancelled'])
        self.assertEqual(len(r['results']),1)
    def test_bus_fault_aborts(self):
        class Broken(Simulated):
            def pm_read(self,*_):raise RuntimeError('ERR SCL_TIMEOUT')
        r=diagnose(Broken([]),[0x30,0x50],[0x99],100,False,False,Event(),lambda _:None)
        self.assertEqual(r['error'],'ERR SCL_TIMEOUT')
        self.assertEqual(len(r['results']),1)
        self.assertEqual(r['results'][0]['status'],'fatal')
    def test_byte_pec_has_no_count_byte(self):
        checksum=crc8(bytes.fromhex('E0 98 E1 22'))
        self.assertTrue(decode_mfr(f'OK BLOCK 01 22 {checksum:02X}',0x70,True,0x98)['pec_verified'])
    def test_stop_pec_rejected_before_io(self):
        p=Pico.__new__(Pico)
        p.version=4
        with self.assertRaises(ValueError):p.pm_read(0x70,0x99,True,True)
    def test_observation(self):
        p=Pico.__new__(Pico)
        p.version=4
        p.serial=FakeSerial(b'OK LINES 10000 12 45 87 3\n')
        r=p.observe()
        self.assertEqual(r['changes'],87)
        self.assertTrue(r['last_sda'])
    def test_raw_wire_and_byte_order(self):
        p=Pico.__new__(Pico)
        p.version=4
        p.serial=FakeSerial(b'OK BLOCK 02 1234 --\n')
        r=p.raw_read(0x70,0x24,2,True)
        self.assertEqual(r['raw_hex'],'1234')
        self.assertEqual(p.serial.sent,[b'RAW 70 24 02 01\n'])
    def test_raw_invalid_no_io(self):
        p=Pico.__new__(Pico)
        p.version=4
        with self.assertRaises(ValueError):p.raw_read(0x70,0x24,3)
