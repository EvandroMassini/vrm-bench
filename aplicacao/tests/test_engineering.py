import unittest
from app.engineering import convert
class EngineeringTests(unittest.TestCase):
    def test_frequency(self):
        self.assertIn('303.85 kHz',convert('LOOP_1_SW_PERIOD',158,{})[0])
        self.assertIn('400.06 kHz',convert('LOOP_2_SW_PERIOD',120,{})[0])
    def test_zero_period(self):self.assertIn('Indefinido',convert('LOOP_1_SW_PERIOD',0,{})[0])
    def test_thermal_dependencies(self):
        self.assertIn('115 °C',convert('TEMP_MAX',51,{})[0])
        self.assertIn('130 °C',convert('OTP_THRESH',15,{'32':{'value':0xCC}})[0])
        self.assertIn('ausente',convert('OTP_THRESH',15,{})[0])
    def test_offset_no_assumed_step(self):
        self.assertIn('0 mV',convert('LOOP_1_VID_OFFSET',15,{})[0])
        self.assertIn('sem conversão',convert('LOOP_1_VID_OFFSET',14,{})[0])
    def test_missing(self):self.assertEqual(convert('TEMP_MAX',None,{})[0],'Não lido')
    def test_amd_offset_independent_of_vr125(self):
        self.assertIn('-6.25 mV',convert('LOOP_1_VID_OFFSET',14,{'14':{'value':0x22}})[0])
