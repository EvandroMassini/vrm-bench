import tempfile
import unittest
from app.reload_mtp import BAXTER_CLOCK, COMANCHE_CLOCK, OTP_COMMAND, decode, reload_and_read
from test_ramtest import Bench

OK = 'OK RELOAD 01 01 24 01 20 00 10 26 01 01 20 01 88 88'

class ReloadTests(unittest.TestCase):
    def test_addresses(self):
        self.assertEqual((COMANCHE_CLOCK, BAXTER_CLOCK, OTP_COMMAND), (0x71, 0x99, 0xD0))
        parsed = decode(OK)
        self.assertTrue(parsed['reload_confirmed'])
        self.assertFalse(parsed['crc']['active_error'])

    def test_match_is_not_a_slot_commit(self):
        class Ready(Bench):
            version = 14
            def request(self, cmd):
                self.calls += 1
                self.last = cmd
                return OK
        seen = {}
        def read_map(link, directory):
            seen['called'] = True
            return dict(stable=True, txt_path='x', values={f'{address:02X}': f'{value:02X}'
                        for address, value in __import__('app.param_byte', fromlist=['load_baseline']).load_baseline().items()})
        link = Ready([])
        with tempfile.TemporaryDirectory() as directory:
            result = reload_and_read(link, directory, read_map)
        self.assertTrue(result['complete'])
        self.assertFalse(result['slot_commit'])
        self.assertFalse(result['programming_enabled'])
        self.assertEqual(result['mismatch_count'], 0)
        self.assertTrue(seen['called'])
        self.assertEqual(link.last, 'RELOAD 08 71 20 24 D0 20')

    def test_clock_rejection_sends_nothing_further(self):
        class Rejected(Bench):
            version = 14
            def request(self, cmd):
                self.calls += 1
                raise RuntimeError('ERR RELOAD_CLOCK 24')
        with tempfile.TemporaryDirectory() as directory:
            result = reload_and_read(Rejected([]), directory, lambda *_: (_ for _ in ()).throw(AssertionError('leitura')))
        self.assertEqual(result['write_attempted'], False)
        self.assertFalse(result['slot_commit'])

    def test_unrestored_does_not_read_the_map(self):
        class Open(Bench):
            version = 14
            def request(self, cmd):
                return 'OK RELOAD 01 01 24 01 20 00 10 26 01 01 24 00 48 48'
        with tempfile.TemporaryDirectory() as directory:
            result = reload_and_read(Open([]), directory, lambda *_: (_ for _ in ()).throw(AssertionError('leitura')))
        self.assertIn('desligue', result['guidance'].lower())
        self.assertNotIn('image_matches_board_file', result)
