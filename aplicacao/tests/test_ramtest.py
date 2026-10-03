import unittest
from app.ramtest import experiment,decode
from app.transport import Simulated

class Bench(Simulated):
    version=9
    calls=0
    def pm_read(self,address,*args):return super().pm_read(0x30,*args)
    def telemetry_read(self,address,command):return super().telemetry_read(0x30,command)
    def register_read(self,address,register):return dict(value=255,raw_hex='FF',pec_verified=True)
    def request(self,cmd):
        self.calls+=1
        assert cmd=='RAMTEST 08 26 FF EF RESTORE'
        return 'OK RAMTEST 01 01 EF 01 01 FF 34'

class RamTests(unittest.TestCase):
    def test_success_one_command(self):
        b=Bench([]);r=experiment(b)
        self.assertEqual(b.calls,1);self.assertTrue(r['change_confirmed']);self.assertTrue(r['restoration_confirmed'])
    def test_no_change_not_success(self):
        r=decode('OK RAMTEST 01 01 FF 01 01 FF 34')
        self.assertFalse(r['change_confirmed']);self.assertTrue(r['restoration_confirmed'])
    def test_failed_restore(self):
        class Broken(Bench):
            def request(self,_):return 'OK RAMTEST 01 01 EF 00 01 EF 34'
        r=experiment(Broken([]));self.assertFalse(r['restoration_confirmed']);self.assertFalse(r['complete'])
    def test_usb_loss_unknown(self):
        class Lost(Bench):
            def request(self,_):raise TimeoutError('USB timeout')
        r=experiment(Lost([]));self.assertIsNone(r['restoration_confirmed']);self.assertIn('Desligue',r['guidance'])
    def test_baseline_rejected_without_write(self):
        class Other(Bench):
            def register_read(self,*_):return dict(value=0,pec_verified=True)
        b=Other([]);r=experiment(b);self.assertEqual(b.calls,0);self.assertFalse(r['command_sent'])
    def test_bus_low_without_write(self):
        class Low(Bench):
            def observe(self):return dict(sda_low_samples=1,scl_low_samples=0,changes=0)
        b=Low([]);r=experiment(b);self.assertEqual(b.calls,0);self.assertIn('BUS_NOT_IDLE',r['error'])
    def test_bad_flags(self):
        with self.assertRaises(ValueError):decode('OK RAMTEST 02 01 EF 01 01 FF 34')
    def test_legacy_firmware_rejected(self):
        b=Bench([]);b.version=6
        with self.assertRaises(ValueError):experiment(b)
    def test_prewrite_rejections(self):
        for error in ('ERR BUS_BUSY','ERR RAMTEST_MODEL','ERR RAMTEST_MODE_READ','ERR RAMTEST_MODE_VALUE 02','ERR RAMTEST_BASELINE'):
            with self.subTest(error=error):
                class Rejected(Bench):
                    def request(self,_):raise RuntimeError(error)
                r=experiment(Rejected([]))
                self.assertFalse(r['write_attempted']);self.assertFalse(r['restoration_required'])
                self.assertNotIn('Desligue',r['guidance'])
                if 'VALUE' in error:self.assertEqual(r['mode_hex'],'02')
    def test_unrecognized_error_remains_unknown(self):
        class Unknown(Bench):
            def request(self,_):raise RuntimeError('ERR OTHER')
        r=experiment(Unknown([]));self.assertIsNone(r['write_attempted']);self.assertIn('Desligue',r['guidance'])
    def test_protocol7_cannot_write(self):
        b=Bench([]);b.version=7
        with self.assertRaises(ValueError):experiment(b)
        self.assertEqual(b.calls,0)
    def test_detailed_precheck(self):
        for stage in ('IDLE_BEFORE','POINTER','READ','STOP'):
            with self.subTest(stage=stage):
                class Failed(Bench):
                    def request(self,_):raise RuntimeError(f'ERR RAMTEST_PRECHECK 14 {stage} -2')
                r=experiment(Failed([]))
                self.assertFalse(r['write_attempted']);self.assertFalse(r['restoration_required'])
                self.assertEqual(r['precheck_failure'],dict(register_hex='14',stage=stage,sdk_code=-2))
                self.assertNotIn('Desligue',r['guidance'])
    def test_protocol8_cannot_write(self):
        b=Bench([]);b.version=8
        with self.assertRaises(ValueError):experiment(b)
        self.assertEqual(b.calls,0)
    def test_hold_requires_new_firmware(self):
        with self.assertRaises(ValueError):experiment(Bench([]),hold=True)
    def test_hold_command_and_restore(self):
        class Held(Bench):
            version=10
            def request(self,cmd):
                self.calls+=1
                self.asserted=cmd
                return 'OK RAMTEST 01 01 EF 01 01 FF 22'
        b=Held([]);r=experiment(b,hold=True)
        self.assertEqual(b.asserted,'RAMHOLD 08 26 FF EF 10000 RESTORE')
        self.assertTrue(r['hold_completed']);self.assertTrue(r['restoration_confirmed']);self.assertEqual(b.calls,1)
