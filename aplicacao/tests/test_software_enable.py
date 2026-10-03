import tempfile,unittest
from app.software_enable import experiment,decode,describe,decode_user_pins
from test_ramtest import Bench

OK='OK ENSOFT 01 01 01 48 01 48 01 30 01 41 01 01 01 88 01 88 22'

class EnableBench(Bench):
    version=12
    def register_read(self,address,register):
        if register in (0x88,0x89):return dict(value=0x88,raw_hex='88',pec_verified=True)
        return dict(value=0x30,raw_hex='30',pec_verified=True)
    def request(self,cmd):
        self.calls+=1
        self.asserted=cmd
        return OK

class EnableTests(unittest.TestCase):
    def test_legend_and_pins(self):
        self.assertEqual(describe(0x88)['name'],'Enable')
        self.assertEqual(describe(0x48)['code'],1)
        self.assertEqual(describe(0x48)['preserved_low_bits_hex'],'08')
        values={f'{n:02X}':dict(value=0) for n in range(0x10,0x68)}
        values['42']['value']=0x00
        values['4C']['value']=0x80
        pins=decode_user_pins(values)
        self.assertEqual(pins['second_enable_pin_select'],0)
        self.assertEqual(pins['second_enable_from_pin'],0)
    def test_short_success(self):
        b=EnableBench([]);r=experiment(b)
        self.assertEqual(b.asserted,'ENSOFT 08 88 89 88 48 RESTORE')
        self.assertTrue(r['change_confirmed']);self.assertTrue(r['restoration_confirmed']);self.assertTrue(r['complete'])
        self.assertFalse(r['programming_enabled']);self.assertEqual(b.calls,1)
    def test_hold_command(self):
        b=EnableBench([]);r=experiment(b,hold=True)
        self.assertEqual(b.asserted,'ENHOLD 08 88 89 88 48 10000 RESTORE')
        self.assertTrue(r['hold_completed'])
    def test_no_change_still_restored(self):
        response=OK.replace('01 48 01 48','01 88 01 88',1)
        r=decode(response)
        self.assertFalse(r['change_confirmed']);self.assertTrue(r['restoration_confirmed'])
    def test_failed_restore(self):
        class Broken(EnableBench):
            def request(self,cmd):
                self.calls+=1
                return 'OK ENSOFT 01 01 01 48 01 48 01 30 01 41 01 01 01 48 01 48 22'
        r=experiment(Broken([]))
        self.assertFalse(r['restoration_confirmed']);self.assertFalse(r['complete']);self.assertIn('Desligue',r['error'])
    def test_baseline_blocks_command(self):
        class Other(EnableBench):
            def register_read(self,address,register):
                return dict(value=0x08,raw_hex='08',pec_verified=True)
        b=Other([]);r=experiment(b)
        self.assertEqual(b.calls,0);self.assertFalse(r['command_sent'])
    def test_old_firmware_rejected(self):
        b=EnableBench([]);b.version=11
        with self.assertRaises(ValueError):experiment(b)
        self.assertEqual(b.calls,0)
    def test_precheck_before_write(self):
        class Failed(EnableBench):
            def request(self,cmd):
                self.calls+=1
                raise RuntimeError('ERR ENSOFT_PRECHECK 88 READ -2')
        r=experiment(Failed([]))
        self.assertFalse(r['write_attempted']);self.assertFalse(r['restoration_required'])
        self.assertEqual(r['precheck_failure']['register_hex'],'88')
    def test_firmware_baseline_before_write(self):
        class Stale(EnableBench):
            def request(self,cmd):
                self.calls+=1
                raise RuntimeError('ERR ENSOFT_BASELINE 88 48')
        r=experiment(Stale([]))
        self.assertFalse(r['write_attempted']);self.assertNotIn('Desligue',r['guidance'])
    def test_bad_flags(self):
        with self.assertRaises(ValueError):decode(OK.replace('OK ENSOFT 01','OK ENSOFT 02',1))
    def test_backup_required_before_command(self):
        seen=[]
        def before(result):
            seen.append(result['command_sent'])
            result['backup_path']='mem'
        b=EnableBench([]);r=experiment(b,before)
        self.assertEqual(seen,[False]);self.assertEqual(r['backup_path'],'mem')
