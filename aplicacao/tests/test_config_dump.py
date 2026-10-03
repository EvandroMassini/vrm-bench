import tempfile
import unittest
from pathlib import Path
from app.config_dump import ADDRESSES, MASK_OVERRIDES, capture, format_text, mask_of, plan_against_file
from app.core import parse_config
from test_ramtest import Bench

class DumpTests(unittest.TestCase):
    def test_map_matches_asus_column_three(self):
        entries = parse_config((Path(__file__).parents[1] / 'samples' / 'ASUS_STRIX_RX580_IR3567B_6PH.txt').read_text())
        self.assertEqual([entry.address for entry in entries], list(ADDRESSES))
        self.assertEqual(mask_of(0x70), 0xFF)
        self.assertEqual(mask_of(0x71), 0xFB)
        self.assertEqual(mask_of(0x0A), 0xE1)
        for entry in entries:
            self.assertEqual(entry.mask, mask_of(entry.address))
        self.assertEqual(set(MASK_OVERRIDES), {0x4F, 0x50, 0x71, 0x8C, 0xB7})

    def test_roundtrip_uses_crlf_and_canonical_mask(self):
        values = {address: (address * 3) & 0xFF for address in ADDRESSES}
        text = format_text(values)
        self.assertIn('\r\n', text)
        parsed = parse_config(text)
        self.assertEqual(parsed[0], type(parsed[0])(0x10, values[0x10], 0xFF))
        self.assertEqual(parsed[-1].address, 0xB7)
        self.assertEqual(parsed[-1].mask, 0x00)

    def test_capture_writes_txt_only_when_stable(self):
        class Stable(Bench):
            def register_read(self, address, register):
                return dict(value=register & 0xFF, pec_verified=True)
        with tempfile.TemporaryDirectory() as directory:
            result = capture(Stable([]), directory)
            self.assertTrue(result['complete'])
            self.assertTrue(result['stable'])
            self.assertFalse(result['programming_enabled'])
            self.assertFalse(result['write_attempted'])
            text = Path(result['txt_path']).read_text(encoding='ascii')
            self.assertEqual(parse_config(text)[0].value, 0x10)
            self.assertTrue(result['report_path'])

    def test_unstable_does_not_write_txt(self):
        class Moving(Bench):
            def __init__(self):
                super().__init__([])
                self.seen = 0
            def register_read(self, address, register):
                if register == 0x10:
                    self.seen += 1
                    return dict(value=self.seen, pec_verified=True)
                return dict(value=0, pec_verified=True)
        with tempfile.TemporaryDirectory() as directory:
            result = capture(Moving(), directory)
        self.assertTrue(result['complete'])
        self.assertFalse(result['stable'])
        self.assertIsNone(result['txt_path'])
        self.assertEqual(result['changed_registers'], ['10'])

    def test_plan_does_not_write_and_hides_bit2_of_71(self):
        live = {f'{address:02X}': '00' for address in ADDRESSES}
        live['10'] = '01'
        live['71'] = '04'
        live['88'] = '88'
        text = format_text({address: 0 for address in ADDRESSES})
        plan = plan_against_file(live, text)
        self.assertFalse(plan['write_attempted'])
        self.assertEqual(plan['diverge_count'], 2)
        self.assertEqual([row['register_hex'] for row in plan['actionable_later']], ['10'])
        self.assertEqual([row['register_hex'] for row in plan['blocked_differences']], ['88'])
        row71 = next(row for row in plan['rows'] if row['register_hex'] == '71')
        self.assertEqual(row71['comparison'], 'Confere')

    def test_selected_map_must_match_the_bytes_read(self):
        from app.config_dump import addresses, mismatch_message
        from app.controller_store import select
        own = {address: 0 for address in addresses()}
        self.assertIsNone(mismatch_message(own))
        missing = dict(own)
        missing.pop(next(iter(missing)))
        self.assertIn('não encontrados', mismatch_message(missing))
        extra = dict(own)
        extra[1] = 0
        self.assertIn('não estão no JSON', mismatch_message(extra))
        select('IR35217')
        try:
            self.assertIn('IR35217', mismatch_message(own))
            salem = {address: 0 for address in addresses()}
            self.assertIsNone(mismatch_message(salem))
        finally:
            select('IR3567B')
