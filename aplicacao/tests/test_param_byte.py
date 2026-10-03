import tempfile
import unittest
from app.param_byte import BLOCKED, change_byte, command, load_baseline, writable
from test_ramtest import Bench

class ParamTests(unittest.TestCase):
    def test_board_file_allows_26_and_blocks_enable(self):
        values = load_baseline()
        allowed = dict(writable(values))
        self.assertEqual(allowed[0x26], 0xFF)
        self.assertNotIn(0x88, allowed)
        self.assertNotIn(0x71, allowed)
        self.assertNotIn(0x4F, allowed)
        self.assertEqual(command(0x26, 0xFF, 0xEF), 'PBYTE 08 26 FF EF')
        for address in BLOCKED:
            with self.subTest(address=address):
                with self.assertRaises(ValueError):
                    command(address, 0, 1)

    def test_apply_one_command_and_leave_it(self):
        class Held(Bench):
            version = 13
            def register_read(self, address, register):
                value = 0xEF if self.calls else 0xFF
                return dict(value=value, pec_verified=True)
            def request(self, cmd):
                self.calls += 1
                self.last = cmd
                return 'OK PBYTE 26 01 00 01 EF 22'
        link = Held([])
        with tempfile.TemporaryDirectory() as directory:
            result = change_byte(link, directory, 0x26, 0xEF, {0x26: 0xFF})
        self.assertTrue(result['complete'])
        self.assertEqual(link.calls, 1)
        self.assertEqual(link.last, 'PBYTE 08 26 FF EF')
        self.assertEqual(result['operation'], 'apply')
        self.assertFalse(result['programming_enabled'])

    def test_stale_live_does_not_send(self):
        class Other(Bench):
            version = 13
            def register_read(self, address, register):
                return dict(value=0x10, pec_verified=True)
            def request(self, cmd):
                raise AssertionError(cmd)
        with tempfile.TemporaryDirectory() as directory:
            result = change_byte(Other([]), directory, 0x26, 0xEF, {0x26: 0xFF})
        self.assertFalse(result['command_sent'])
        self.assertFalse(result['write_attempted'])
        self.assertIn('arquivo', result['error'])

    def test_old_firmware_rejected(self):
        link = Bench([])
        link.version = 12
        with self.assertRaises(ValueError):
            change_byte(link, '.', 0x26, 0xEF, {0x26: 0xFF})
        self.assertEqual(link.calls, 0)
