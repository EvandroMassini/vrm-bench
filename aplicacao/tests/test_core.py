import unittest
from pathlib import Path
from app.core import Entry, parse_config, parse_dump_tolerant, compare, read_plan, region
from app.transport import Simulated

class CoreTests(unittest.TestCase):
    def test_sample(self):
        entries = parse_config((Path(__file__).parents[1]/"samples"/"IR35217_MSI_RX5700_7plus1.txt").read_text())
        self.assertEqual(len(entries), 132)
        self.assertEqual(sum(e.mask == 0 for e in entries), 5)
        self.assertEqual(len(read_plan("IR35217", entries)), 129)
        self.assertEqual(Simulated(entries).read(0x30, 0xA0), 0x20)

    def test_mask(self):
        entry = Entry(0xA0, 0x20, 0xFB)
        self.assertEqual(compare(entry, 0x24), "Confere")
        self.assertEqual(compare(entry, 0x21), "Diverge")
        self.assertEqual(compare(Entry(0x17, 0, 0), 255), "Sem verificação")
        self.assertEqual(compare(entry, None), "Não lido")

    def test_bad_files(self):
        for text in ("", "24 GG FF", "24 100 FF", "24 20", "24 20 FF\n24 21 FF"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_config(text)

    def test_tolerant_import_keeps_matching_bytes_and_counts_conflicts(self):
        entries, issues = parse_dump_tolerant("24 10 FF\n24 11 FF\n25 20 00\nGG\n25 20 00\n")
        self.assertEqual([(item.address, item.value) for item in entries], [(0x25, 0x20)])
        self.assertGreaterEqual(len(issues), 3)
        kept = {item.address: item.value for item in entries}
        self.assertNotIn(0x24, kept)

    def test_no_cross_family_assumptions(self):
        self.assertEqual(read_plan("IR3567B", [Entry(0x24,0,255)]), [0x24])
        self.assertEqual(read_plan("IR3567B", [Entry(0x96,0,255)]), [])
        self.assertEqual(region("IR3567B",0x24), "USER")
        self.assertEqual(region("IR3567B",0x70), "MFR")
        self.assertEqual(region("IR3567B",0x0A), "TRIM")
        self.assertEqual(region("IR3567B",0xB7), "B7")
        self.assertEqual(region("IR3567B",0x96), "Fora do TXT curto")

if __name__ == "__main__":
    unittest.main()
