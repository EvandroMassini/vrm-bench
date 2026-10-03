import tempfile
import unittest
from app.param_byte import load_baseline
from app.slot_commit import COMMAND, commit_user_slot, image_token, user_plan
from test_ramtest import Bench

def ok_line(pointer=0x0F, after=0x00):
    plan = user_plan(pointer)
    after_plan = user_plan(after)
    fields = [1, pointer, plan['left'], plan['index'], plan['opcode'], 1, 1, 1, 0x04,
              1, 1, 0x04, 0x00, after, after_plan['left'], 0xA2, 0xFF, 1, 1, 0x88, 0x88]
    return 'OK COMMIT ' + ' '.join(f'{item:02X}' for item in fields)

class SlotTests(unittest.TestCase):
    def test_pointer_formula(self):
        self.assertEqual(user_plan(0x0F)['opcode'], 0x40)
        self.assertEqual(user_plan(0x00)['opcode'], 0x41)
        self.assertEqual((user_plan(0x07)['left'], user_plan(0x07)['opcode']), (1, 0x48))
        self.assertIsNone(user_plan(0x08)['opcode'])
        self.assertIsNone(user_plan(0x0E)['opcode'])
        self.assertEqual(user_plan(0xF0)['opcode'], 0x41)
        for pointer in range(256):
            plan = user_plan(pointer)
            if plan['opcode'] is not None:
                self.assertTrue(0x40 <= plan['opcode'] <= 0x48)

    def test_one_slot_when_image_matches(self):
        class Ready(Bench):
            version = 15
            def request(self, cmd):
                self.calls += 1
                self.last = cmd
                return ok_line()
        calls = []
        def read_map(link, directory):
            calls.append(directory)
            return dict(stable=True, txt_path='x', user_sha256='h',
                        values={f'{address:02X}': f'{value:02X}' for address, value in load_baseline().items()})
        link = Ready([])
        with tempfile.TemporaryDirectory() as directory:
            result = commit_user_slot(link, directory, read_map)
        self.assertTrue(result['complete'])
        self.assertEqual(link.last, COMMAND)
        self.assertEqual(link.calls, 1)
        self.assertEqual(len(calls), 2)
        self.assertEqual(result['opcode_hex'], '40')
        self.assertEqual(result['slots_consumed'], 1)
        self.assertTrue(result['slot_commit'])
        self.assertFalse(result['programming_enabled'])

    def test_mismatch_sends_nothing(self):
        class Ready(Bench):
            version = 15
            def request(self, cmd):
                raise AssertionError(cmd)
        def read_map(link, directory):
            values = {f'{address:02X}': f'{value:02X}' for address, value in load_baseline().items()}
            values['10'] = '00'
            return dict(stable=True, values=values)
        with tempfile.TemporaryDirectory() as directory:
            result = commit_user_slot(Ready([]), directory, read_map)
        self.assertFalse(result['command_sent'])
        self.assertFalse(result['slot_commit'])
        self.assertIn('não coincide', result['error'])

    def test_empty_mtp_writes_nothing(self):
        class Empty(Bench):
            version = 15
            def request(self, cmd):
                self.calls += 1
                raise RuntimeError('ERR COMMIT_NOSLOT 08 00 07 03')
        def read_map(link, directory):
            return dict(stable=True, values={f'{address:02X}': f'{value:02X}' for address, value in load_baseline().items()})
        link = Empty([])
        with tempfile.TemporaryDirectory() as directory:
            result = commit_user_slot(link, directory, read_map)
        self.assertEqual(link.calls, 1)
        self.assertEqual(result['write_attempted'], False)
        self.assertEqual(result['user_left_before'], 0)
        self.assertFalse(result['slot_commit'])

    def test_changed_image_uses_the_next_slot(self):
        values = {f'{address:02X}': f'{value:02X}' for address, value in load_baseline().items()}
        values['26'] = 'EF'
        class Ready(Bench):
            version = 15
            def request(self, cmd):
                self.calls += 1
                self.last = cmd
                return ok_line(0x02, 0x03)
        def read_map(link, directory):
            return dict(stable=True, txt_path='x', user_sha256='h', values=dict(values))
        link = Ready([])
        with tempfile.TemporaryDirectory() as directory:
            result = commit_user_slot(link, directory, read_map, require='changed', image_token_expected=image_token(values))
        self.assertTrue(result['complete'])
        self.assertEqual(link.calls, 1)
        self.assertEqual(link.last, COMMAND)
        self.assertEqual(result['opcode_hex'], '43')
        self.assertEqual(result['slots_consumed'], 1)
        self.assertEqual(result['difference_count'], 1)

    def test_identical_image_is_not_written_again(self):
        values = {f'{address:02X}': f'{value:02X}' for address, value in load_baseline().items()}
        class Ready(Bench):
            version = 15
            def request(self, cmd):
                raise AssertionError(cmd)
        def read_map(link, directory):
            return dict(stable=True, values=values)
        with tempfile.TemporaryDirectory() as directory:
            result = commit_user_slot(Ready([]), directory, read_map, require='changed', image_token_expected=image_token(values))
        self.assertFalse(result['command_sent'])
        self.assertIn('igual', result['error'])
