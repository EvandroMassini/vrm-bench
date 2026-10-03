import unittest
from app.transport import crc8,decode_mfr,Pico,Simulated

class PMBusTests(unittest.TestCase):
    def test_crc_reference(self):
        self.assertEqual(crc8(b"123456789"),0xF4)
    def test_no_pec(self):
        self.assertEqual(decode_mfr("OK BLOCK 02 4952 --",0x70,False)["text"],"IR")
    def test_invalid_frames(self):
        for frame in ("OK BLOCK 00 00 --","OK BLOCK 21 00 --","OK BLOCK 02 49 --",
                      "OK BLOCK 01 49 00","OK 49","OK BLOCK 01 GG --"):
            with self.subTest(frame=frame),self.assertRaises(ValueError):
                decode_mfr(frame,0x70,False)
    def test_bad_pec(self):
        with self.assertRaises(ValueError):decode_mfr("OK BLOCK 02 4952 00",0x70,True)
    def test_simulated_pec(self):
        self.assertTrue(Simulated([]).read_mfr_id(0x30,True)["pec_verified"])
    def test_old_firmware_no_io(self):
        link=Pico.__new__(Pico)
        link.version=2
        with self.assertRaises(ValueError):link.read_mfr_id(0x70)
