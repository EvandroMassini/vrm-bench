import unittest
from threading import Event
from app.transport import Simulated,crc8,Pico
from app.registers import parse_registers,decode_register,map_interface,capture
from test_transport import FakeSerial

class RegisterTests(unittest.TestCase):
    def test_parser(self):
        self.assertEqual(parse_registers('24,25 0x24'),[0x24,0x25])
        for value in ('','00-FF','100','GG'):
            with self.assertRaises(ValueError):parse_registers(value)
    def test_d4_crc(self):
        check=crc8(bytes.fromhex('E0 D4 E1 B0'))
        self.assertEqual(decode_register(f'OK BLOCK 01 B0 {check:02X}',0x70)['value'],0xB0)
        with self.assertRaises(ValueError):decode_register('OK BLOCK 01 B0 00',0x70)
    def test_wire(self):
        p=Pico.__new__(Pico);p.version=6
        check=crc8(bytes.fromhex('E0 D4 E1 B0'))
        p.serial=FakeSerial(f'OK BLOCK 01 B0 {check:02X}\n'.encode())
        p.register_read(0x70,0x24)
        self.assertEqual(p.serial.sent,[b'REG 70 24\n'])
    def test_mapping(self):
        r=map_interface(Simulated([]),0x30,100)
        self.assertTrue(r['direct_i2c_enabled'])
        self.assertEqual(r['direct_i2c_address_7bit'],8)
    def test_two_passes(self):
        r=capture(Simulated([]),0x30,100,[0x24,0x25],'simulated',Event(),lambda _:None)
        self.assertTrue(r['all_equal']);self.assertTrue(r['complete'])
    def test_difference_not_hidden(self):
        class Changing(Simulated):
            count=0
            def register_read(self,*_):
                self.count+=1
                return dict(value=self.count,raw_hex=f'{self.count:02X}',pec_verified=True)
        r=capture(Changing([]),0x30,100,[0x24],'simulated',Event(),lambda _:None)
        self.assertTrue(r['complete']);self.assertFalse(r['all_equal'])
    def test_cancellation(self):
        event=Event()
        r=capture(Simulated([]),0x30,100,[0x24,0x25],'simulated',event,lambda _:event.set())
        self.assertTrue(r['cancelled']);self.assertEqual(len(r['passes'][0]),1)
    def test_failure_preserves_row(self):
        class Broken(Simulated):
            def register_read(self,*_):raise ValueError('PEC invalid')
        r=capture(Broken([]),0x30,100,[0x24],'simulated',Event(),lambda _:None)
        self.assertEqual(r['error'],'PEC invalid')
        self.assertEqual(r['passes'][0][0]['status'],'error')
