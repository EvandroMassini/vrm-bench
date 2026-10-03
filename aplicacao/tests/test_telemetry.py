import unittest
from threading import Event
from app.transport import Simulated,TargetRejected,crc8,Pico
from app.telemetry import collect,decode_fixed,interpret,linear11,vout_pin
from test_transport import FakeSerial

class TelemetryTests(unittest.TestCase):
    def setUp(self):
        from app.controller_store import select
        select('IR3567B')
    def test_signed_linear11(self):
        self.assertEqual(linear11(45),45)
        self.assertEqual(linear11((31<<11)|100),50)
        self.assertEqual(linear11(2048-10),-10)
    def test_vout_gap_follows_the_meter_at_both_adjustments(self):
        low=interpret(0x8B,{'value_raw':2162},0x15,8)['value']
        high=interpret(0x8B,{'value_raw':2255},0x15,15)['value']
        self.assertAlmostEqual(low,1.1056640625)
        self.assertAlmostEqual(vout_pin(1.10107421875,15),1.15732421875)
        self.assertGreater(high-low,0.04)
        self.assertAlmostEqual(high-low,1.15732421875-1.1056640625)
    def test_ir35217_vout_uses_its_own_json_offset(self):
        from app.controller_store import select
        select('IR35217')
        try:
            self.assertAlmostEqual(interpret(0x8B,{'value_raw':2162},0x15,8)['value'],2162/2048)
        finally:
            select('IR3567B')
    def test_vout_read_exponent(self):
        self.assertEqual(interpret(0x8B,{'value_raw':512},0x17)['value'],1)
        self.assertIsNone(interpret(0x8B,{'value_raw':512},None)['value'])
        self.assertIsNone(interpret(0x8B,{'value_raw':512},0x40)['value'])
    def test_word_pec_without_count(self):
        check=crc8(bytes.fromhex('E0 8B E1 00 02'))
        result=decode_fixed(f'OK BLOCK 02 0002 {check:02X}',0x70,0x8B)
        self.assertEqual(result['value_raw'],512)
        with self.assertRaises(ValueError):decode_fixed('OK BLOCK 02 0002 00',0x70,0x8B)
    def test_allowlist_no_io(self):
        p=Pico.__new__(Pico);p.version=16
        with self.assertRaises(ValueError):p.telemetry_read(0x70,0x03)
    def test_wire(self):
        p=Pico.__new__(Pico);p.version=16
        check=crc8(bytes.fromhex('E0 20 E1 17'))
        p.serial=FakeSerial(f'OK BLOCK 01 17 {check:02X}\n'.encode())
        self.assertEqual(p.telemetry_read(0x70,0x20)['value_raw'],23)
        self.assertEqual(p.serial.sent,[b'GPM 70 20 01 01 00\n'])
    def test_collection(self):
        r=collect(Simulated([]),0x30,100,1,Event(),lambda _:None)
        self.assertTrue(r['complete'])
        vout=next(x for x in r['samples'][0]['readings'] if x['command_hex']=='8B')
        self.assertEqual(vout['value'],1)
    def test_wrong_model_stops_before_telemetry(self):
        class Wrong(Simulated):
            def pm_read(self,*_):return dict(raw_hex='45',pec_verified=True)
            def telemetry_read(self,*_):raise AssertionError('Must not read')
        r=collect(Wrong([]),0x30,100,1,Event(),lambda _:None)
        self.assertTrue(r['error']);self.assertFalse(r['samples'])
    def test_cancel_partial(self):
        cancel=Event()
        r=collect(Simulated([]),0x30,100,10,cancel,lambda _:cancel.set(),interval=0)
        self.assertTrue(r['cancelled'])
        self.assertEqual(len(r['samples'][0]['readings']),1)
    def test_unsupported_not_retried(self):
        class Unsupported(Simulated):
            calls=0
            def telemetry_read(self,a,c):
                if c==0x89:
                    self.calls+=1
                    raise TargetRejected('ERR PMBUS_COMMAND')
                return super().telemetry_read(a,c)
        p=Unsupported([])
        r=collect(p,0x30,100,10,Event(),lambda _:None,interval=0)
        self.assertTrue(r['complete']);self.assertEqual(p.calls,1)
    def test_bad_pec_aborts_preserves(self):
        class Broken(Simulated):
            def telemetry_read(self,*_):raise ValueError('PEC inválido')
        r=collect(Broken([]),0x30,100,10,Event(),lambda _:None,interval=0)
        self.assertEqual(r['error'],'PEC inválido')
        self.assertEqual(r['samples'][0]['readings'][0]['status'],'fatal')
